#ifndef FPGA_AMP_VOLUME_SERVO_H
#define FPGA_AMP_VOLUME_SERVO_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    VOLUME_DRIVE_COAST = 0,
    VOLUME_DRIVE_INCREASE = 1,
    VOLUME_DRIVE_DECREASE = 2,
} volume_drive_t;

enum {
    VOLUME_FAULT_CONFIG = 1u << 0,
    VOLUME_FAULT_SENSOR = 1u << 1,
    VOLUME_FAULT_DRIVER = 1u << 2,
    VOLUME_FAULT_STALL = 1u << 3,
    VOLUME_FAULT_TIMEOUT = 1u << 4,
};

typedef struct {
    uint16_t hard_min_position;
    uint16_t soft_min_position;
    uint16_t soft_max_position;
    uint16_t hard_max_position;
    uint16_t deadband_counts;
    uint16_t approach_span_counts;
    uint16_t manual_takeover_counts;
    uint16_t minimum_duty_per_mille;
    uint16_t maximum_duty_per_mille;
    uint16_t current_limit_ma;
    uint16_t stall_tick_limit;
    uint16_t motion_timeout_ticks;
    uint16_t reverse_dead_ticks;
} volume_servo_config_t;

typedef struct {
    uint16_t measured_position;
    uint16_t measured_current_ma;
    bool driver_fault;
    bool manual_override;
    bool clear_faults;
    bool target_valid;
    uint16_t target_position;
} volume_servo_input_t;

typedef struct {
    volume_drive_t drive;
    uint16_t duty_per_mille;
    uint16_t target_position;
    uint32_t latched_faults;
    uint32_t accumulated_motor_ticks;
    bool moving;
    bool target_changed;
} volume_servo_output_t;

typedef struct {
    volume_servo_config_t config;
    uint16_t target_position;
    uint16_t last_position;
    uint16_t overcurrent_ticks;
    uint16_t motion_ticks;
    uint16_t reverse_dead_remaining;
    uint32_t accumulated_motor_ticks;
    uint32_t latched_faults;
    volume_drive_t drive;
    bool configured;
    bool target_pending;
} volume_servo_state_t;

/*
 * The caller invokes volume_servo_step() at one fixed control period. All
 * time fields are counts of that period. Position is a ratiometric ADC or
 * absolute-angle code and never carries audio. The motor driver must enforce
 * an independent hardware current limit; this state machine adds retained
 * stall, timeout, sensor, and driver-fault policy.
 */
bool volume_servo_init(
    volume_servo_state_t *state,
    const volume_servo_config_t *config,
    uint16_t initial_position
);

volume_servo_output_t volume_servo_step(
    volume_servo_state_t *state,
    const volume_servo_input_t *input
);

#ifdef __cplusplus
}
#endif

#endif
