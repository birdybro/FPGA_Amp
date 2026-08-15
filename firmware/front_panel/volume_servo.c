#include "volume_servo.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>


static uint16_t clamp_position(const volume_servo_config_t *config, uint16_t position) {
    if (position < config->soft_min_position) {
        return config->soft_min_position;
    }
    if (position > config->soft_max_position) {
        return config->soft_max_position;
    }
    return position;
}


static uint16_t absolute_difference(uint16_t left, uint16_t right) {
    return left >= right ? (uint16_t)(left - right) : (uint16_t)(right - left);
}


static bool sensor_position_valid(
    const volume_servo_config_t *config,
    uint16_t position
) {
    return position >= config->hard_min_position && position <= config->hard_max_position;
}


static bool config_valid(const volume_servo_config_t *config) {
    return config != NULL
        && config->hard_min_position < config->soft_min_position
        && config->soft_min_position < config->soft_max_position
        && config->soft_max_position < config->hard_max_position
        && config->deadband_counts > 0u
        && config->approach_span_counts > config->deadband_counts
        && config->manual_takeover_counts > config->deadband_counts
        && config->minimum_duty_per_mille > 0u
        && config->minimum_duty_per_mille <= config->maximum_duty_per_mille
        && config->maximum_duty_per_mille <= 1000u
        && config->current_limit_ma > 0u
        && config->stall_tick_limit > 0u
        && config->motion_timeout_ticks > config->stall_tick_limit;
}


static void saturating_increment_u16(uint16_t *value) {
    if (*value != UINT16_MAX) {
        *value = (uint16_t)(*value + 1u);
    }
}


static void saturating_increment_u32(uint32_t *value) {
    if (*value != UINT32_MAX) {
        *value += 1u;
    }
}


static uint16_t requested_duty(
    const volume_servo_config_t *config,
    uint16_t error_counts
) {
    if (error_counts >= config->approach_span_counts) {
        return config->maximum_duty_per_mille;
    }
    const uint32_t duty_span =
        (uint32_t)config->maximum_duty_per_mille - config->minimum_duty_per_mille;
    const uint32_t scaled = duty_span * error_counts;
    return (uint16_t)(
        config->minimum_duty_per_mille + scaled / config->approach_span_counts
    );
}


static volume_servo_output_t make_output(
    const volume_servo_state_t *state,
    bool target_changed,
    uint16_t duty
) {
    volume_servo_output_t output = {
        .drive = state->drive,
        .duty_per_mille = state->drive == VOLUME_DRIVE_COAST ? 0u : duty,
        .target_position = state->target_position,
        .latched_faults = state->latched_faults,
        .accumulated_motor_ticks = state->accumulated_motor_ticks,
        .moving = state->drive != VOLUME_DRIVE_COAST,
        .target_changed = target_changed,
    };
    return output;
}


bool volume_servo_init(
    volume_servo_state_t *state,
    const volume_servo_config_t *config,
    uint16_t initial_position
) {
    if (state == NULL) {
        return false;
    }
    memset(state, 0, sizeof(*state));
    state->drive = VOLUME_DRIVE_COAST;
    if (!config_valid(config)) {
        state->latched_faults = VOLUME_FAULT_CONFIG;
        return false;
    }
    state->config = *config;
    if (!sensor_position_valid(config, initial_position)) {
        state->latched_faults = VOLUME_FAULT_SENSOR;
        return false;
    }
    state->target_position = clamp_position(config, initial_position);
    state->last_position = initial_position;
    state->configured = true;
    return true;
}


volume_servo_output_t volume_servo_step(
    volume_servo_state_t *state,
    const volume_servo_input_t *input
) {
    if (state == NULL || input == NULL) {
        volume_servo_output_t invalid = {0};
        invalid.latched_faults = VOLUME_FAULT_CONFIG;
        return invalid;
    }
    if (!state->configured) {
        state->drive = VOLUME_DRIVE_COAST;
        state->latched_faults |= VOLUME_FAULT_CONFIG;
        return make_output(state, false, 0u);
    }

    const volume_servo_config_t *config = &state->config;
    bool target_changed = false;
    const bool position_valid = sensor_position_valid(config, input->measured_position);

    if (!position_valid) {
        state->latched_faults |= VOLUME_FAULT_SENSOR;
    }
    if (input->driver_fault) {
        state->latched_faults |= VOLUME_FAULT_DRIVER;
    }

    if (input->clear_faults) {
        const bool safe_to_clear = position_valid
            && !input->driver_fault
            && input->measured_current_ma <= config->current_limit_ma
            && !input->manual_override;
        state->drive = VOLUME_DRIVE_COAST;
        state->motion_ticks = 0u;
        state->overcurrent_ticks = 0u;
        state->reverse_dead_remaining = 0u;
        if (safe_to_clear) {
            state->latched_faults = 0u;
            const uint16_t held_position = clamp_position(config, input->measured_position);
            target_changed = held_position != state->target_position;
            state->target_position = held_position;
            state->target_pending = false;
        }
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }

    if (state->latched_faults != 0u) {
        state->drive = VOLUME_DRIVE_COAST;
        state->motion_ticks = 0u;
        state->reverse_dead_remaining = 0u;
        state->last_position = input->measured_position;
        return make_output(state, false, 0u);
    }

    if (input->manual_override) {
        const uint16_t manual_position = clamp_position(config, input->measured_position);
        target_changed = manual_position != state->target_position;
        state->target_position = manual_position;
        state->target_pending = false;
        state->drive = VOLUME_DRIVE_COAST;
        state->motion_ticks = 0u;
        state->overcurrent_ticks = 0u;
        state->reverse_dead_remaining = 0u;
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }

    if (input->target_valid) {
        const uint16_t commanded = clamp_position(config, input->target_position);
        target_changed = commanded != state->target_position;
        state->target_position = commanded;
        state->target_pending = true;
    } else if (
        state->drive == VOLUME_DRIVE_COAST
        && state->reverse_dead_remaining == 0u
        && !state->target_pending
        && absolute_difference(input->measured_position, state->target_position)
            >= config->manual_takeover_counts
    ) {
        /* A manually back-driven idle dial becomes the new authoritative target. */
        const uint16_t manual_position = clamp_position(config, input->measured_position);
        target_changed = manual_position != state->target_position;
        state->target_position = manual_position;
        state->target_pending = false;
    }

    const uint16_t error = absolute_difference(input->measured_position, state->target_position);
    if (error <= config->deadband_counts) {
        state->drive = VOLUME_DRIVE_COAST;
        state->motion_ticks = 0u;
        state->overcurrent_ticks = 0u;
        state->reverse_dead_remaining = 0u;
        state->target_pending = false;
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }

    const volume_drive_t desired_drive =
        state->target_position > input->measured_position
            ? VOLUME_DRIVE_INCREASE
            : VOLUME_DRIVE_DECREASE;

    if (state->reverse_dead_remaining > 0u) {
        state->reverse_dead_remaining = (uint16_t)(state->reverse_dead_remaining - 1u);
        state->drive = VOLUME_DRIVE_COAST;
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }
    if (state->drive != VOLUME_DRIVE_COAST && state->drive != desired_drive) {
        state->drive = VOLUME_DRIVE_COAST;
        state->reverse_dead_remaining = config->reverse_dead_ticks;
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }

    if (input->measured_current_ma > config->current_limit_ma) {
        saturating_increment_u16(&state->overcurrent_ticks);
    } else {
        state->overcurrent_ticks = 0u;
    }
    if (state->overcurrent_ticks >= config->stall_tick_limit) {
        state->latched_faults |= VOLUME_FAULT_STALL;
        state->drive = VOLUME_DRIVE_COAST;
        state->motion_ticks = 0u;
        state->reverse_dead_remaining = 0u;
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }

    saturating_increment_u16(&state->motion_ticks);
    if (state->motion_ticks >= config->motion_timeout_ticks) {
        state->latched_faults |= VOLUME_FAULT_TIMEOUT;
        state->drive = VOLUME_DRIVE_COAST;
        state->reverse_dead_remaining = 0u;
        state->last_position = input->measured_position;
        return make_output(state, target_changed, 0u);
    }

    state->drive = desired_drive;
    saturating_increment_u32(&state->accumulated_motor_ticks);
    state->last_position = input->measured_position;
    return make_output(state, target_changed, requested_duty(config, error));
}
