#include "volume_servo.h"

#include <assert.h>
#include <stdio.h>


static volume_servo_config_t test_config(void) {
    const volume_servo_config_t config = {
        .hard_min_position = 500u,
        .soft_min_position = 1000u,
        .soft_max_position = 60000u,
        .hard_max_position = 62000u,
        .deadband_counts = 100u,
        .approach_span_counts = 5000u,
        .manual_takeover_counts = 500u,
        .minimum_duty_per_mille = 200u,
        .maximum_duty_per_mille = 800u,
        .current_limit_ma = 150u,
        .stall_tick_limit = 3u,
        .motion_timeout_ticks = 20u,
        .reverse_dead_ticks = 2u,
    };
    return config;
}


static volume_servo_input_t input_at(uint16_t position) {
    const volume_servo_input_t input = {
        .measured_position = position,
    };
    return input;
}


static void test_configuration_and_endpoint_clamp(void) {
    volume_servo_state_t state;
    volume_servo_config_t config = test_config();
    assert(volume_servo_init(&state, &config, 10000u));

    volume_servo_input_t input = input_at(10000u);
    input.target_valid = true;
    input.target_position = UINT16_MAX;
    volume_servo_output_t output = volume_servo_step(&state, &input);
    assert(output.target_changed);
    assert(output.target_position == config.soft_max_position);
    assert(output.drive == VOLUME_DRIVE_INCREASE);
    assert(output.duty_per_mille == config.maximum_duty_per_mille);

    config.minimum_duty_per_mille = 900u;
    config.maximum_duty_per_mille = 800u;
    assert(!volume_servo_init(&state, &config, 10000u));
    assert(state.latched_faults == VOLUME_FAULT_CONFIG);
}


static void test_remote_motion_and_soft_landing(void) {
    volume_servo_state_t state;
    const volume_servo_config_t config = test_config();
    assert(volume_servo_init(&state, &config, 10000u));

    volume_servo_input_t input = input_at(10000u);
    input.target_valid = true;
    input.target_position = 20000u;
    volume_servo_output_t output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_INCREASE);
    assert(output.duty_per_mille == 800u);
    assert(output.accumulated_motor_ticks == 1u);

    input = input_at(19000u);
    output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_INCREASE);
    assert(output.duty_per_mille > config.minimum_duty_per_mille);
    assert(output.duty_per_mille < config.maximum_duty_per_mille);

    input = input_at(19950u);
    output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_COAST);
    assert(output.duty_per_mille == 0u);
    assert(!output.moving);
}


static void test_reversal_dead_time(void) {
    volume_servo_state_t state;
    const volume_servo_config_t config = test_config();
    assert(volume_servo_init(&state, &config, 10000u));

    volume_servo_input_t input = input_at(10000u);
    input.target_valid = true;
    input.target_position = 30000u;
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_INCREASE);

    input.target_position = 2000u;
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_COAST);
    input.target_valid = false;
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_COAST);
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_COAST);
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_DECREASE);
}


static void test_manual_override_and_idle_takeover(void) {
    volume_servo_state_t state;
    const volume_servo_config_t config = test_config();
    assert(volume_servo_init(&state, &config, 10000u));

    volume_servo_input_t input = input_at(10000u);
    input.target_valid = true;
    input.target_position = 30000u;
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_INCREASE);

    input = input_at(12000u);
    input.manual_override = true;
    volume_servo_output_t output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_COAST);
    assert(output.target_position == 12000u);
    assert(output.target_changed);

    input = input_at(13000u);
    output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_COAST);
    assert(output.target_position == 13000u);
    assert(output.target_changed);
}


static void test_stall_latches_and_requires_safe_clear(void) {
    volume_servo_state_t state;
    const volume_servo_config_t config = test_config();
    assert(volume_servo_init(&state, &config, 10000u));

    volume_servo_input_t input = input_at(10000u);
    input.target_valid = true;
    input.target_position = 30000u;
    input.measured_current_ma = 151u;
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_INCREASE);
    input.target_valid = false;
    assert(volume_servo_step(&state, &input).drive == VOLUME_DRIVE_INCREASE);
    volume_servo_output_t output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_COAST);
    assert((output.latched_faults & VOLUME_FAULT_STALL) != 0u);

    input.clear_faults = true;
    output = volume_servo_step(&state, &input);
    assert((output.latched_faults & VOLUME_FAULT_STALL) != 0u);

    input.measured_current_ma = 0u;
    output = volume_servo_step(&state, &input);
    assert(output.latched_faults == 0u);
    assert(output.target_position == input.measured_position);
    assert(output.drive == VOLUME_DRIVE_COAST);

    input.clear_faults = false;
    output = volume_servo_step(&state, &input);
    assert(output.drive == VOLUME_DRIVE_COAST);
}


static void test_driver_sensor_and_timeout_faults(void) {
    volume_servo_state_t state;
    volume_servo_config_t config = test_config();
    config.motion_timeout_ticks = 4u;
    assert(volume_servo_init(&state, &config, 10000u));

    volume_servo_input_t input = input_at(10000u);
    input.target_valid = true;
    input.target_position = 30000u;
    assert(volume_servo_step(&state, &input).moving);
    input.target_valid = false;
    assert(volume_servo_step(&state, &input).moving);
    assert(volume_servo_step(&state, &input).moving);
    volume_servo_output_t output = volume_servo_step(&state, &input);
    assert((output.latched_faults & VOLUME_FAULT_TIMEOUT) != 0u);
    assert(!output.moving);

    assert(volume_servo_init(&state, &config, 10000u));
    input = input_at(10000u);
    input.driver_fault = true;
    output = volume_servo_step(&state, &input);
    assert((output.latched_faults & VOLUME_FAULT_DRIVER) != 0u);
    assert(!output.moving);

    assert(volume_servo_init(&state, &config, 10000u));
    input = input_at(100u);
    output = volume_servo_step(&state, &input);
    assert((output.latched_faults & VOLUME_FAULT_SENSOR) != 0u);
    assert(!output.moving);
}


int main(void) {
    test_configuration_and_endpoint_clamp();
    test_remote_motion_and_soft_landing();
    test_reversal_dead_time();
    test_manual_override_and_idle_takeover();
    test_stall_latches_and_requires_safe_clear();
    test_driver_sensor_and_timeout_faults();
    puts("volume_servo_test: PASS");
    return 0;
}
