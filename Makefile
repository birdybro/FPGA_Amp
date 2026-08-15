PYTHON ?= python3
NGSPICE ?= ngspice
VERILATOR ?= verilator
YOSYS ?= yosys
NEXTPNR ?= nextpnr-himbaechel

.PHONY: all reference analysis arithmetic-bounds accuracy-sweeps factorized-study factorized-frequency factorized-frequency-wide factorized-frequency-trapezoidal factorized-domain state-drift state-wide state-wide-audio linear-modes wide-rtl-audio wide-rtl-frequency trapezoidal-rtl-frequency trapezoidal-rtl-recovery wide-rtl-overload terminal-banked-rtl-metrics trapezoidal-terminal-banked-rtl-metrics banked-rtl-overload terminal-banked-rtl-overload banked-accuracy banked-selector banked-threshold banked-slew-selector banked-error-decomposition banked-iterations terminal-bank-study terminal-relaxation-study dual-triode-bank-study grid-current-resolution wide-stream-rtl-frequency trapezoidal-stream-rtl-frequency trapezoidal-terminal-stream-rtl-frequency wide-stream-rtl-alias wav-null-regression audio-regression spice-python-frequency overload-study overload-wide overload-trapezoidal overload-long overload-severe-long overload-seven-second overload-iterations overload-banked trapezoidal-overload precision-study resampler test python-test plots spice spice-all rtl hermite-rtl factorized-rtl factorized-linear-rtl chord-rtl wide-chord-rtl network-rtl wide-network-rtl trapezoidal-network-rtl solver-rtl solver-factorized-rtl wide-solver-rtl wide-linear-solver-rtl trapezoidal-solver-rtl banked-solver-rtl terminal-banked-solver-rtl trapezoidal-terminal-banked-solver-rtl trapezoidal-banked-solver-rtl halfband-rtl stream-rtl stream-factorized-rtl stream-wide-rtl stream-terminal-banked-rtl stream-trapezoidal-rtl stream-trapezoidal-terminal-banked-rtl guarded-stream-rtl mute-rtl audio-clock-rtl async-fifo-rtl cdc-pulse-rtl cdc-snapshot-rtl spi-control-rtl i2s-rtl i2s-bridge-rtl calibration-rtl calibration-control-rtl control-registers-rtl frame-scheduler-rtl mono-adapter-rtl i2s-mono-top-rtl i2s-control-top-rtl i2s-spi-top-rtl formal formal-mute formal-async-fifo formal-calibration-control formal-frame-scheduler formal-cdc-snapshot formal-cdc-pulse formal-audio-clock formal-audio-calibration formal-spi-control lint synth synth-hermite synth-factorized synth-factorized-linear synth-chord synth-wide-chord synth-network synth-wide-network synth-solver synth-solver-factorized synth-wide-solver synth-wide-linear-solver synth-trapezoidal-solver synth-banked-solver synth-terminal-banked-solver synth-trapezoidal-terminal-banked-solver synth-trapezoidal-banked-solver synth-halfband synth-stream synth-stream-factorized synth-stream-wide synth-stream-terminal-banked synth-stream-trapezoidal synth-stream-trapezoidal-terminal-banked synth-stream-guarded synth-mute synth-audio-clock synth-async-fifo synth-cdc-pulse synth-cdc-snapshot synth-spi-control synth-i2s synth-i2s-bridge synth-calibration synth-calibration-control synth-control-registers synth-frame-scheduler synth-mono-adapter synth-i2s-mono-top synth-i2s-control-top synth-i2s-spi-top openxc7-probe openxc7-pnr openxc7-hermite-pnr openxc7-linear-tube-pnr openxc7-linear-solver-pnr openxc7-terminal-current-pnr openxc7-kcl-pnr openxc7-chord-pnr tools-openxc7 clean tools
.PHONY: factorized-linear-study wide-chord-pipelined-rtl wide-chord-early-preview-rtl parallel-solver-rtl trapezoidal-parallel-terminal-banked-solver-rtl trapezoidal-parallel-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-deep-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-max-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-diagnostic-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-shared-capacitor-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-shared-terminal-diagnostic-pipelined-terminal-banked-solver-rtl decoupled-diagnostic-kcl-rtl decoupled-maximum-only-kcl-rtl serial-maximum-kcl-rtl shared-capacitor-decoupled-diagnostic-kcl-rtl terminal-current-half-parallel-rtl openxc7-parallel-solver-pnr openxc7-parallel-pipelined-solver-pnr openxc7-parallel-deep-pipelined-solver-pnr openxc7-parallel-max-pipelined-solver-pnr openxc7-parallel-diagnostic-pipelined-solver-place openxc7-parallel-diagnostic-pipelined-solver-pnr openxc7-parallel-decoupled-diagnostic-pipelined-solver-place openxc7-parallel-shared-capacitor-decoupled-diagnostic-pipelined-solver-place openxc7-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-solver-place openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-place openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-timing-place openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-regions-place openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-soft-kcl-pack openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-soft-kcl-capacitors-pack openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-pnr openxc7-a200t-probe openxc7-a200t-parallel-diagnostic-pipelined-solver-place openxc7-a200t-parallel-diagnostic-pipelined-solver-pnr openxc7-terminal-current-half-parallel-pnr openxc7-terminal-current-half-parallel-timing-pnr openxc7-pipelined-kcl-pnr openxc7-deep-pipelined-kcl-pnr openxc7-max-pipelined-kcl-pnr openxc7-diagnostic-pipelined-kcl-pnr openxc7-decoupled-diagnostic-pipelined-kcl-pnr openxc7-decoupled-diagnostic-pipelined-kcl-timing-place openxc7-shared-capacitor-decoupled-diagnostic-kcl-place openxc7-diagnostic-pipelined-kcl-soft-pack openxc7-diagnostic-pipelined-kcl-soft-capacitors-place openxc7-pipelined-chord-pnr
.PHONY: openxc7-parallel-shared-capacitor-decoupled-diagnostic-pipelined-solver-timing-place openxc7-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-solver-regions-place
.PHONY: internal-rate-study internal-rate-pop-decomposition internal-rate-spice-pop internal-rate-transient-rtl fixed-384-assets
.PHONY: trapezoidal-banked-chord-rtl trapezoidal-384-chord-rtl trapezoidal-384-network-rtl trapezoidal-384-terminal-banked-solver-rtl
.PHONY: synth-trapezoidal-384-terminal-banked-solver
.PHONY: stream-trapezoidal-384-terminal-banked-rtl stream-trapezoidal-384-terminal-banked-half-clock-rtl stream-trapezoidal-384-terminal-banked-half-clock-pipelined-rtl stream-trapezoidal-384-terminal-banked-half-clock-prefetched-rtl stream-trapezoidal-384-terminal-banked-half-clock-retimed-rtl stream-trapezoidal-384-terminal-banked-half-clock-late-select-rtl stream-trapezoidal-384-terminal-banked-half-clock-late-select-retimed-rtl stream-trapezoidal-384-terminal-banked-half-clock-late-select-serial-max-rtl stream-trapezoidal-384-terminal-banked-half-clock-node-prefetch-serial-max-rtl
.PHONY: synth-stream-trapezoidal-384-terminal-banked
.PHONY: openxc7-stream-384-pack openxc7-stream-384-place openxc7-a200t-stream-384-static-place openxc7-a200t-stream-384-half-clock-static-place openxc7-a200t-stream-384-half-clock-node-prefetch-serial-max-pnr openxc7-a200t-stream-384-half-clock-node-prefetch-serial-max-bit
.PHONY: mono-adapter-384-rtl i2s-mono-top-384-rtl i2s-control-top-384-rtl i2s-spi-top-384-rtl synth-mono-adapter-384 synth-i2s-spi-top-384
.PHONY: audio-clock-plan audio-serial-clock-rtl i2c-write-rtl synth-audio-clock-xc7 synth-audio-serial-clock-xc7 synth-i2c-write openxc7-a200t-audio-clock-pnr openxc7-a200t-audio-clock-bit

all: reference test

reference:
	$(PYTHON) scripts/run_reference.py

analysis:
	$(PYTHON) scripts/analyze_frontend.py
	$(PYTHON) scripts/characterize_solver.py
	$(PYTHON) scripts/compare_fixed_float.py

arithmetic-bounds:
	$(PYTHON) scripts/analyze_wide_arithmetic_bounds.py

accuracy-sweeps:
	$(PYTHON) scripts/characterize_fixed_levels.py
	$(PYTHON) scripts/study_low_level_lut.py

factorized-study:
	$(PYTHON) scripts/study_factorized_tube.py

factorized-linear-study:
	$(PYTHON) scripts/characterize_linear_factorized_candidate.py

factorized-domain:
	$(PYTHON) scripts/analyze_factorized_domain.py

factorized-frequency:
	$(PYTHON) scripts/characterize_factorized_frequency.py

factorized-frequency-wide:
	$(PYTHON) scripts/characterize_factorized_frequency.py --wide-candidate

factorized-frequency-trapezoidal:
	$(PYTHON) scripts/characterize_factorized_frequency.py --trapezoidal

state-drift:
	$(PYTHON) scripts/characterize_state_drift.py

state-wide:
	$(PYTHON) scripts/characterize_state_drift.py --wide-candidate

state-wide-audio:
	$(PYTHON) scripts/characterize_wide_state_audio.py

linear-modes:
	$(PYTHON) scripts/analyze_linearized_modes.py

wide-rtl-audio:
	$(PYTHON) scripts/characterize_wide_solver_rtl.py --verilator $(VERILATOR)

wide-rtl-frequency:
	$(PYTHON) scripts/sweep_wide_solver_rtl.py --verilator $(VERILATOR)

trapezoidal-rtl-frequency:
	$(PYTHON) scripts/sweep_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal

trapezoidal-rtl-recovery:
	$(PYTHON) scripts/characterize_trapezoidal_solver_rtl_recovery.py --verilator $(VERILATOR)

wide-rtl-overload:
	$(PYTHON) scripts/characterize_wide_solver_rtl_overload.py --verilator $(VERILATOR)

terminal-banked-rtl-metrics:
	$(PYTHON) scripts/characterize_wide_solver_rtl_overload.py --verilator $(VERILATOR) --banked --terminal-correction

trapezoidal-terminal-banked-rtl-metrics:
	$(PYTHON) scripts/characterize_wide_solver_rtl_overload.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction

banked-rtl-overload:
	$(PYTHON) scripts/verify_banked_solver_rtl_overload.py --verilator $(VERILATOR)

terminal-banked-rtl-overload:
	$(PYTHON) scripts/verify_banked_solver_rtl_overload.py --verilator $(VERILATOR) --terminal-correction

banked-accuracy:
	$(PYTHON) scripts/characterize_banked_solver_accuracy.py

banked-selector:
	$(PYTHON) scripts/study_banked_selector.py

banked-threshold:
	$(PYTHON) scripts/study_banked_shallow_threshold.py

banked-slew-selector:
	$(PYTHON) scripts/study_banked_slew_selector.py

banked-error-decomposition:
	$(PYTHON) scripts/decompose_banked_solver_error.py

banked-iterations:
	$(PYTHON) scripts/study_banked_chord_iterations.py

terminal-bank-study:
	$(PYTHON) scripts/study_terminal_bank_reselection.py

terminal-relaxation-study:
	$(PYTHON) scripts/study_terminal_correction_relaxation.py

dual-triode-bank-study:
	$(PYTHON) scripts/study_dual_triode_chord_banks.py

grid-current-resolution:
	$(PYTHON) scripts/study_grid_current_resolution.py

wide-stream-rtl-frequency:
	$(PYTHON) scripts/sweep_wide_stream_rtl.py --verilator $(VERILATOR)

trapezoidal-stream-rtl-frequency:
	$(PYTHON) scripts/sweep_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal

trapezoidal-terminal-stream-rtl-frequency:
	$(PYTHON) scripts/sweep_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction

wide-stream-rtl-alias:
	$(PYTHON) scripts/characterize_wide_stream_rtl_alias.py --verilator $(VERILATOR)

wav-null-regression:
	$(PYTHON) scripts/run_wav_null_regression.py

audio-regression:
	$(PYTHON) scripts/run_audio_regression.py

spice-python-frequency:
	$(PYTHON) scripts/compare_spice_python_frequency.py --ngspice $(NGSPICE)

internal-rate-study:
	$(PYTHON) scripts/study_internal_sample_rate.py

internal-rate-pop-decomposition:
	$(PYTHON) scripts/study_internal_rate_pop_decomposition.py

internal-rate-spice-pop:
	$(PYTHON) scripts/compare_internal_rate_pop_spice.py --ngspice $(NGSPICE)

internal-rate-transient-rtl: fixed-384-assets
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/verify_internal_rate_transients_rtl.py --verilator $(VERILATOR)

fixed-384-assets:
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py --sample-rate-hz 384000
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal --banked --sample-rate-hz 384000
	$(PYTHON) scripts/generate_wide_solver_vectors.py --trapezoidal --banked --terminal-correction --sample-rate-hz 384000

overload-study:
	$(PYTHON) scripts/characterize_overload_recovery.py

overload-wide:
	$(PYTHON) scripts/characterize_overload_recovery.py --wide-candidate

overload-trapezoidal:
	$(PYTHON) scripts/characterize_overload_recovery.py --trapezoidal

overload-long:
	$(PYTHON) scripts/characterize_long_overload_recovery.py

overload-severe-long:
	$(PYTHON) scripts/measure_severe_overload_recovery.py

overload-seven-second:
	$(PYTHON) scripts/measure_seven_second_recovery.py

overload-iterations:
	$(PYTHON) scripts/study_overload_iterations.py

overload-banked:
	$(PYTHON) scripts/study_banked_chord_overload.py

trapezoidal-overload:
	$(PYTHON) scripts/study_trapezoidal_overload.py

resampler:
	$(PYTHON) scripts/design_resampler.py

precision-study:
	$(PYTHON) scripts/study_chord_precision.py

plots:
	$(PYTHON) scripts/run_reference.py --plots

spice:
	$(PYTHON) scripts/run_spice.py --ngspice $(NGSPICE)

spice-all: spice
	$(PYTHON) scripts/spice_level_sweep.py
	$(PYTHON) scripts/compare_spice_python.py

rtl:
	$(PYTHON) scripts/run_rtl.py --verilator $(VERILATOR)

hermite-rtl:
	$(PYTHON) scripts/run_hermite_rtl.py --verilator $(VERILATOR)

factorized-rtl:
	$(PYTHON) scripts/run_factorized_rtl.py --verilator $(VERILATOR)

factorized-linear-rtl:
	$(PYTHON) scripts/run_factorized_rtl.py --linear --verilator $(VERILATOR)

chord-rtl:
	$(PYTHON) scripts/run_chord_rtl.py --verilator $(VERILATOR)

wide-chord-rtl:
	$(PYTHON) scripts/run_wide_chord_rtl.py --verilator $(VERILATOR)

wide-chord-pipelined-rtl:
	$(PYTHON) scripts/run_wide_chord_rtl.py --verilator $(VERILATOR) --pipelined-apply

wide-chord-early-preview-rtl:
	$(PYTHON) scripts/run_wide_chord_rtl.py --verilator $(VERILATOR) --early-preview

trapezoidal-banked-chord-rtl:
	$(PYTHON) scripts/run_wide_chord_rtl.py --verilator $(VERILATOR) --trapezoidal --banked

trapezoidal-384-chord-rtl:
	$(PYTHON) scripts/run_wide_chord_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --sample-rate-hz 384000

network-rtl:
	$(PYTHON) scripts/run_network_rtl.py --verilator $(VERILATOR)

wide-network-rtl:
	$(PYTHON) scripts/run_wide_network_rtl.py --verilator $(VERILATOR)

trapezoidal-network-rtl:
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR)

decoupled-maximum-only-kcl-rtl:
	$(PYTHON) scripts/run_wide_network_rtl.py --verilator $(VERILATOR) --pipelined-maximum --decoupled-maximum
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000 --pipelined-maximum --decoupled-maximum

serial-maximum-kcl-rtl:
	$(PYTHON) scripts/run_wide_network_rtl.py --verilator $(VERILATOR) --serial-maximum
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000 --serial-maximum

trapezoidal-384-network-rtl:
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000

decoupled-diagnostic-kcl-rtl:
	$(PYTHON) scripts/run_wide_network_rtl.py --verilator $(VERILATOR) --pipelined-finish --pipelined-columns --pipelined-accumulator --pipelined-maximum --decoupled-maximum
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR) --pipelined-finish --pipelined-columns --pipelined-accumulator --pipelined-maximum --decoupled-maximum

shared-capacitor-decoupled-diagnostic-kcl-rtl:
	$(PYTHON) scripts/run_wide_network_rtl.py --verilator $(VERILATOR) --pipelined-finish --pipelined-columns --pipelined-accumulator --pipelined-maximum --decoupled-maximum --shared-capacitor-multiplier
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR) --pipelined-finish --pipelined-columns --pipelined-accumulator --pipelined-maximum --decoupled-maximum --shared-capacitor-multiplier

solver-rtl:
	$(PYTHON) scripts/run_solver_rtl.py --verilator $(VERILATOR)

solver-factorized-rtl:
	$(PYTHON) scripts/run_solver_rtl.py --verilator $(VERILATOR) --factorized

wide-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR)

wide-linear-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --linear-tube --verilator $(VERILATOR)

parallel-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --parallel-tubes --verilator $(VERILATOR)

trapezoidal-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal

banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --banked

terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --banked --terminal-correction

trapezoidal-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction

trapezoidal-384-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000

trapezoidal-parallel-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes

trapezoidal-parallel-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-chord-apply

trapezoidal-parallel-deep-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-chord-apply

trapezoidal-parallel-max-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-kcl-capacitor-current --pipelined-chord-apply

trapezoidal-parallel-diagnostic-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-kcl-maximum --pipelined-chord-apply

trapezoidal-parallel-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-kcl-maximum --decoupled-kcl-maximum --pipelined-chord-apply

trapezoidal-parallel-shared-capacitor-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-kcl-maximum --decoupled-kcl-maximum --shared-kcl-capacitor-multiplier --pipelined-chord-apply

trapezoidal-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-kcl-maximum --decoupled-kcl-maximum --shared-kcl-capacitor-multiplier --pipelined-chord-apply --half-parallel-terminal-current

trapezoidal-parallel-shared-terminal-diagnostic-pipelined-terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --parallel-tubes --pipelined-kcl-finish --pipelined-kcl-columns --pipelined-kcl-accumulator --pipelined-kcl-maximum --pipelined-chord-apply --half-parallel-terminal-current

terminal-current-half-parallel-rtl:
	$(VERILATOR) --binary --timing -Wall -Wno-fatal -sv --top-module terminal_current_update_v1_half_parallel_tb --Mdir build/verilator_terminal_current_half_parallel rtl/circuit/terminal_current_update_v1.sv sim/unit/terminal_current_update_v1_half_parallel_tb.sv
	build/verilator_terminal_current_half_parallel/Vterminal_current_update_v1_half_parallel_tb

trapezoidal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal --banked

halfband-rtl:
	$(PYTHON) scripts/run_halfband_rtl.py --verilator $(VERILATOR)

stream-rtl:
	$(PYTHON) scripts/run_stream_rtl.py --verilator $(VERILATOR)

stream-factorized-rtl:
	$(PYTHON) scripts/run_stream_rtl.py --verilator $(VERILATOR) --factorized

stream-wide-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR)

stream-terminal-banked-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --banked --terminal-correction

stream-trapezoidal-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal

stream-trapezoidal-terminal-banked-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction

stream-trapezoidal-384-terminal-banked-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000

stream-trapezoidal-384-terminal-banked-half-clock-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000

stream-trapezoidal-384-terminal-banked-half-clock-pipelined-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --pipelined-solver-profile

stream-trapezoidal-384-terminal-banked-half-clock-prefetched-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --prefetch-tube-inputs

stream-trapezoidal-384-terminal-banked-half-clock-retimed-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --prefetch-tube-inputs --decoupled-kcl-maximum-only

stream-trapezoidal-384-terminal-banked-half-clock-late-select-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --late-tube-input-select

stream-trapezoidal-384-terminal-banked-half-clock-late-select-retimed-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --late-tube-input-select --decoupled-kcl-maximum-only

stream-trapezoidal-384-terminal-banked-half-clock-late-select-serial-max-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --late-tube-input-select --serial-kcl-maximum-only

stream-trapezoidal-384-terminal-banked-half-clock-node-prefetch-serial-max-rtl:
	$(PYTHON) scripts/run_wide_stream_rtl.py --verilator $(VERILATOR) --trapezoidal --banked --terminal-correction --sample-rate-hz 384000 --fabric-clock-hz 49152000 --prefetch-tube-nodes --serial-kcl-maximum-only

guarded-stream-rtl:
	$(PYTHON) scripts/run_guarded_stream_rtl.py --verilator $(VERILATOR)

mute-rtl:
	$(PYTHON) scripts/run_mute_rtl.py --verilator $(VERILATOR)

formal: formal-mute formal-async-fifo formal-calibration-control formal-frame-scheduler formal-cdc-snapshot formal-cdc-pulse formal-audio-clock formal-audio-calibration formal-spi-control

formal-mute:
	$(PYTHON) scripts/run_mute_formal.py --yosys $(YOSYS)

formal-async-fifo:
	$(PYTHON) scripts/run_async_fifo_formal.py --yosys $(YOSYS)

formal-calibration-control:
	$(PYTHON) scripts/run_calibration_control_formal.py --yosys $(YOSYS)

formal-frame-scheduler:
	$(PYTHON) scripts/run_frame_scheduler_formal.py --yosys $(YOSYS)

formal-cdc-snapshot:
	$(PYTHON) scripts/run_cdc_word_snapshot_formal.py --yosys $(YOSYS)

formal-cdc-pulse:
	$(PYTHON) scripts/run_cdc_toggle_pulse_formal.py --yosys $(YOSYS)

formal-audio-clock:
	$(PYTHON) scripts/run_audio_clock_monitor_formal.py --yosys $(YOSYS)

formal-audio-calibration:
	$(PYTHON) scripts/run_audio_sample_calibration_formal.py --yosys $(YOSYS)

formal-spi-control:
	$(PYTHON) scripts/run_spi_control_formal.py --yosys $(YOSYS)

audio-clock-rtl:
	$(PYTHON) scripts/run_audio_clock_monitor_rtl.py --verilator $(VERILATOR)

audio-serial-clock-rtl:
	$(PYTHON) scripts/run_audio_serial_clock_rtl.py --verilator $(VERILATOR)

i2c-write-rtl:
	$(PYTHON) scripts/run_i2c_write_rtl.py --verilator $(VERILATOR)

async-fifo-rtl:
	$(PYTHON) scripts/run_async_fifo_rtl.py --verilator $(VERILATOR)

cdc-pulse-rtl:
	$(PYTHON) scripts/run_cdc_toggle_pulse_rtl.py --verilator $(VERILATOR)

cdc-snapshot-rtl:
	$(PYTHON) scripts/run_cdc_word_snapshot_rtl.py --verilator $(VERILATOR)

spi-control-rtl:
	$(PYTHON) scripts/run_spi_control_rtl.py --verilator $(VERILATOR)

i2s-rtl:
	$(PYTHON) scripts/run_i2s_rtl.py --verilator $(VERILATOR)

i2s-bridge-rtl:
	$(PYTHON) scripts/run_i2s_bridge_rtl.py --verilator $(VERILATOR)

calibration-rtl:
	$(PYTHON) scripts/run_calibration_rtl.py --verilator $(VERILATOR)

calibration-control-rtl:
	$(PYTHON) scripts/run_calibration_control_rtl.py --verilator $(VERILATOR)

control-registers-rtl:
	$(PYTHON) scripts/run_control_registers_rtl.py --verilator $(VERILATOR)

frame-scheduler-rtl:
	$(PYTHON) scripts/run_frame_scheduler_rtl.py --verilator $(VERILATOR)

mono-adapter-rtl:
	$(PYTHON) scripts/run_mono_adapter_rtl.py --verilator $(VERILATOR)

mono-adapter-384-rtl:
	$(PYTHON) scripts/run_mono_adapter_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000

i2s-mono-top-rtl:
	$(PYTHON) scripts/run_i2s_mono_top_rtl.py --verilator $(VERILATOR)

i2s-mono-top-384-rtl:
	$(PYTHON) scripts/run_i2s_mono_top_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000

i2s-control-top-rtl:
	$(PYTHON) scripts/run_i2s_control_top_rtl.py --verilator $(VERILATOR)

i2s-control-top-384-rtl:
	$(PYTHON) scripts/run_i2s_control_top_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000

i2s-spi-top-rtl:
	$(PYTHON) scripts/run_i2s_spi_top_rtl.py --verilator $(VERILATOR)

i2s-spi-top-384-rtl:
	$(PYTHON) scripts/run_i2s_spi_top_rtl.py --verilator $(VERILATOR) --sample-rate-hz 384000

lint:
	$(PYTHON) scripts/run_rtl.py --verilator $(VERILATOR) --lint-only

synth:
	$(PYTHON) scripts/run_synthesis.py

synth-hermite:
	$(PYTHON) scripts/run_synthesis.py --top hermite_q16_pipeline

synth-factorized-linear:
	$(PYTHON) scripts/generate_factorized_tube.py --linear
	$(PYTHON) scripts/run_synthesis.py --top triode_12ax7_factorized_linear

synth-factorized:
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/run_synthesis.py --top triode_12ax7_factorized

synth-chord:
	$(PYTHON) scripts/generate_chord_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top chord_corrector_v1

synth-wide-chord:
	$(PYTHON) scripts/generate_wide_chord_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top chord_corrector_v1_wide

synth-network:
	$(PYTHON) scripts/generate_network_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top network_rhs_v1
	$(PYTHON) scripts/run_synthesis.py --top network_kcl_v1

synth-wide-network:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top network_rhs_v1_wide
	$(PYTHON) scripts/run_synthesis.py --top network_kcl_v1_wide

synth-solver:
	$(PYTHON) scripts/generate_tube_lut.py
	$(PYTHON) scripts/generate_network_vectors.py
	$(PYTHON) scripts/generate_chord_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono

synth-solver-factorized:
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_network_vectors.py
	$(PYTHON) scripts/generate_chord_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_factorized

synth-wide-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide

synth-wide-linear-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py --linear
	$(PYTHON) scripts/generate_wide_solver_vectors.py --linear-tube
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_linear

synth-trapezoidal-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py --trapezoidal
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_trapezoidal

synth-banked-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_banked

synth-terminal-banked-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_banked_terminal

synth-trapezoidal-banked-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_trapezoidal_banked

synth-trapezoidal-terminal-banked-solver:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py --trapezoidal --banked --terminal-correction
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_trapezoidal_banked_terminal

synth-trapezoidal-384-terminal-banked-solver: fixed-384-assets
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/run_synthesis.py --top v1_solver_mono_wide_trapezoidal_banked_terminal --sample-rate-hz 384000

synth-halfband:
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top interpolator_16x
	$(PYTHON) scripts/run_synthesis.py --top decimator_16x
	$(PYTHON) scripts/run_synthesis.py --top interpolator_8x
	$(PYTHON) scripts/run_synthesis.py --top decimator_8x

synth-stream:
	$(PYTHON) scripts/generate_tube_lut.py
	$(PYTHON) scripts/generate_network_vectors.py
	$(PYTHON) scripts/generate_chord_vectors.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono

synth-stream-factorized:
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_network_vectors.py
	$(PYTHON) scripts/generate_chord_vectors.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_factorized

synth-stream-wide:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/generate_stream_vectors.py --wide
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide

synth-stream-terminal-banked:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py --banked --terminal-correction
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/generate_stream_vectors.py --wide --banked --terminal-correction
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide_banked_terminal

synth-stream-trapezoidal:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py --trapezoidal
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/generate_stream_vectors.py --wide --trapezoidal
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide_trapezoidal

synth-stream-trapezoidal-terminal-banked:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py --trapezoidal --banked --terminal-correction
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/generate_stream_vectors.py --wide --trapezoidal --banked --terminal-correction
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide_trapezoidal_banked_terminal

synth-stream-trapezoidal-384-terminal-banked: fixed-384-assets
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/generate_stream_vectors.py --wide --trapezoidal --banked --terminal-correction --sample-rate-hz 384000
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide_trapezoidal_384khz_banked_terminal

synth-stream-guarded:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide_guarded

synth-mute:
	$(PYTHON) scripts/run_synthesis.py --top output_mute_ramp

synth-audio-clock:
	$(PYTHON) scripts/run_synthesis.py --top audio_clock_rate_monitor

synth-async-fifo:
	$(PYTHON) scripts/run_synthesis.py --top async_fifo

synth-cdc-pulse:
	$(PYTHON) scripts/run_synthesis.py --top cdc_toggle_pulse

synth-cdc-snapshot:
	$(PYTHON) scripts/run_synthesis.py --top cdc_word_snapshot

synth-spi-control:
	$(PYTHON) scripts/run_synthesis.py --top spi_control_transport

synth-i2s:
	$(PYTHON) scripts/run_synthesis.py --top i2s_receiver
	$(PYTHON) scripts/run_synthesis.py --top i2s_transmitter

synth-i2s-bridge:
	$(PYTHON) scripts/run_synthesis.py --top i2s_async_bridge

synth-calibration:
	$(PYTHON) scripts/run_synthesis.py --top pcm24_to_q8_24
	$(PYTHON) scripts/run_synthesis.py --top q8_24_to_pcm24

synth-calibration-control:
	$(PYTHON) scripts/run_synthesis.py --top calibration_commit_guard

synth-control-registers:
	$(PYTHON) scripts/run_synthesis.py --top phono_control_registers

synth-frame-scheduler:
	$(PYTHON) scripts/run_synthesis.py --top audio_frame_scheduler

synth-mono-adapter:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_trapezoidal_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py --trapezoidal --banked
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_wide_solver_vectors.py --trapezoidal --banked --terminal-correction
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top phono_fabric_mono_adapter

synth-i2s-mono-top: synth-mono-adapter
	$(PYTHON) scripts/run_synthesis.py --top phono_i2s_mono_top

synth-i2s-control-top: synth-mono-adapter
	$(PYTHON) scripts/run_synthesis.py --top phono_i2s_control_top

synth-i2s-spi-top: synth-mono-adapter
	$(PYTHON) scripts/run_synthesis.py --top phono_i2s_spi_top

synth-mono-adapter-384: fixed-384-assets
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top phono_fabric_mono_adapter --sample-rate-hz 384000

synth-i2s-spi-top-384: synth-mono-adapter-384
	$(PYTHON) scripts/run_synthesis.py --top phono_i2s_spi_top --sample-rate-hz 384000

synth-audio-clock-xc7:
	$(PYTHON) scripts/run_synthesis.py --top audio_clock_synth_xc7_pnr_harness

synth-audio-serial-clock-xc7:
	$(PYTHON) scripts/run_synthesis.py --top audio_serial_clock_master_xc7

synth-i2c-write:
	$(PYTHON) scripts/run_synthesis.py --top i2c_write_master

audio-clock-plan:
	$(PYTHON) scripts/verify_audio_clock_plan.py

python-test:
	$(PYTHON) -m unittest discover -s model/tests -v

test: python-test arithmetic-bounds rtl hermite-rtl factorized-rtl factorized-linear-rtl chord-rtl wide-chord-rtl wide-chord-pipelined-rtl wide-chord-early-preview-rtl trapezoidal-banked-chord-rtl trapezoidal-384-chord-rtl network-rtl wide-network-rtl trapezoidal-network-rtl trapezoidal-384-network-rtl decoupled-diagnostic-kcl-rtl decoupled-maximum-only-kcl-rtl serial-maximum-kcl-rtl shared-capacitor-decoupled-diagnostic-kcl-rtl solver-rtl solver-factorized-rtl wide-solver-rtl wide-linear-solver-rtl parallel-solver-rtl trapezoidal-solver-rtl banked-solver-rtl terminal-banked-solver-rtl trapezoidal-banked-solver-rtl trapezoidal-terminal-banked-solver-rtl trapezoidal-384-terminal-banked-solver-rtl trapezoidal-parallel-terminal-banked-solver-rtl trapezoidal-parallel-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-shared-capacitor-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl trapezoidal-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-terminal-banked-solver-rtl terminal-current-half-parallel-rtl trapezoidal-parallel-shared-terminal-diagnostic-pipelined-terminal-banked-solver-rtl halfband-rtl stream-rtl stream-factorized-rtl stream-wide-rtl stream-terminal-banked-rtl stream-trapezoidal-rtl stream-trapezoidal-terminal-banked-rtl stream-trapezoidal-384-terminal-banked-rtl stream-trapezoidal-384-terminal-banked-half-clock-rtl stream-trapezoidal-384-terminal-banked-half-clock-pipelined-rtl stream-trapezoidal-384-terminal-banked-half-clock-retimed-rtl stream-trapezoidal-384-terminal-banked-half-clock-late-select-rtl stream-trapezoidal-384-terminal-banked-half-clock-late-select-retimed-rtl stream-trapezoidal-384-terminal-banked-half-clock-late-select-serial-max-rtl stream-trapezoidal-384-terminal-banked-half-clock-node-prefetch-serial-max-rtl guarded-stream-rtl mute-rtl audio-clock-rtl async-fifo-rtl cdc-pulse-rtl cdc-snapshot-rtl spi-control-rtl i2s-rtl i2s-bridge-rtl calibration-rtl calibration-control-rtl control-registers-rtl frame-scheduler-rtl mono-adapter-rtl i2s-mono-top-rtl i2s-control-top-rtl i2s-spi-top-rtl

openxc7-probe:
	$(PYTHON) scripts/run_openxc7.py --probe --nextpnr $(NEXTPNR)

openxc7-a200t-probe:
	$(PYTHON) scripts/run_openxc7.py --device xc7a200tsbg484-1 --probe --nextpnr $(NEXTPNR)

openxc7-pnr:
	$(PYTHON) scripts/run_openxc7.py --nextpnr $(NEXTPNR)

openxc7-stream-384-pack: fixed-384-assets
	$(PYTHON) scripts/run_openxc7.py --top stream_384khz_pnr_harness --nextpnr $(NEXTPNR) --pack-only

openxc7-stream-384-place: fixed-384-assets
	$(PYTHON) scripts/run_openxc7.py --top stream_384khz_pnr_harness --nextpnr $(NEXTPNR) --place-only

openxc7-a200t-stream-384-static-place: fixed-384-assets
	$(PYTHON) scripts/run_openxc7.py --top stream_384khz_pnr_harness --device xc7a200tsbg484-1 --xdc fpga/nexys_video/solver_pnr_harness.xdc --nextpnr $(NEXTPNR) --placer static --run-tag static --place-only

openxc7-a200t-stream-384-half-clock-static-place: fixed-384-assets
	$(PYTHON) scripts/run_openxc7.py --top stream_384khz_49mhz_pnr_harness --device xc7a200tsbg484-1 --frequency-mhz 49.152 --xdc fpga/nexys_video/solver_pnr_harness.xdc --nextpnr $(NEXTPNR) --placer static --run-tag static --place-only

openxc7-a200t-stream-384-half-clock-node-prefetch-serial-max-pnr: fixed-384-assets
	$(PYTHON) scripts/run_openxc7.py --top stream_384khz_49mhz_node_prefetch_serial_max_pnr_harness --device xc7a200tsbg484-1 --frequency-mhz 49.152 --xdc fpga/nexys_video/solver_pnr_harness.xdc --nextpnr $(NEXTPNR) --placer static --run-tag routed

openxc7-a200t-stream-384-half-clock-node-prefetch-serial-max-bit:
	$(PYTHON) scripts/generate_openxc7_bitstream.py --part xc7a200tsbg484-1 --fasm build/openxc7/xc7a200tsbg484-1/stream_384khz_49mhz_node_prefetch_serial_max_pnr_harness/routed/stream_384khz_49mhz_node_prefetch_serial_max_pnr_harness.fasm

openxc7-a200t-audio-clock-pnr:
	$(PYTHON) scripts/run_openxc7.py --top audio_clock_synth_xc7_pnr_harness --device xc7a200tsbg484-1 --frequency-mhz 100 --xdc fpga/nexys_video/audio_clock_synth_xc7.xdc --nextpnr $(NEXTPNR) --run-tag routed

openxc7-a200t-audio-clock-bit:
	$(PYTHON) scripts/generate_openxc7_bitstream.py --part xc7a200tsbg484-1 --fasm build/openxc7/xc7a200tsbg484-1/audio_clock_synth_xc7_pnr_harness/routed/audio_clock_synth_xc7_pnr_harness.fasm

openxc7-hermite-pnr:
	$(PYTHON) scripts/run_openxc7.py --top hermite_pnr_harness --nextpnr $(NEXTPNR)

openxc7-linear-tube-pnr:
	$(PYTHON) scripts/run_openxc7.py --top linear_tube_pnr_harness --nextpnr $(NEXTPNR)

openxc7-linear-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top linear_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-parallel-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-parallel-pipelined-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-parallel-deep-pipelined-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_deep_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-parallel-max-pipelined-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_max_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-parallel-diagnostic-pipelined-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-parallel-diagnostic-pipelined-solver-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --place-only
	$(PYTHON) scripts/analyze_openxc7_placement.py build/openxc7/parallel_diagnostic_pipelined_solver_pnr_harness/parallel_diagnostic_pipelined_solver_pnr_harness_placed.json --output reference/results/openxc7_parallel_diagnostic_pipelined_solver_placement_regions.json

openxc7-parallel-decoupled-diagnostic-pipelined-solver-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_decoupled_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --place-only

openxc7-parallel-shared-capacitor-decoupled-diagnostic-pipelined-solver-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_capacitor_decoupled_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --place-only

openxc7-parallel-shared-capacitor-decoupled-diagnostic-pipelined-solver-timing-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_capacitor_decoupled_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --run-tag timingweight20 --place-only

openxc7-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-solver-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_capacitor_terminal_decoupled_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --place-only

openxc7-parallel-shared-capacitor-terminal-decoupled-diagnostic-pipelined-solver-regions-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_capacitor_terminal_decoupled_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --pre-place-script fpga/openxc7/solver_hierarchy_regions_v2.py --run-tag regions_v2_weight20 --place-only

openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --place-only
	$(PYTHON) scripts/analyze_openxc7_placement.py build/openxc7/parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness/parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness_placed.json --output reference/results/openxc7_parallel_shared_terminal_diagnostic_pipelined_solver_placement_regions.json

openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-timing-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --run-tag timingweight20 --place-only
	$(PYTHON) scripts/analyze_openxc7_placement.py build/openxc7/parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness/timingweight20/parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness_placed.json --output reference/results/openxc7_parallel_shared_terminal_diagnostic_pipelined_solver_timingweight20_placement_regions.json

openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-regions-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --pre-place-script fpga/openxc7/solver_hierarchy_regions_v2.py --run-tag regions_v2_weight20 --place-only
	$(PYTHON) scripts/analyze_openxc7_placement.py build/openxc7/parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness/regions_v2_weight20/parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness_placed.json --output reference/results/openxc7_parallel_shared_terminal_diagnostic_pipelined_solver_regions_v2_weight20_placement_regions.json

openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-soft-kcl-pack:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --soft-kcl-multipliers --run-tag soft_kcl --pack-only

openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-soft-kcl-capacitors-pack:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR) --soft-kcl-capacitor-multipliers --run-tag soft_kcl_capacitors --pack-only

openxc7-parallel-shared-terminal-diagnostic-pipelined-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness --nextpnr $(NEXTPNR)

openxc7-a200t-parallel-diagnostic-pipelined-solver-place:
	$(PYTHON) scripts/run_openxc7.py --top parallel_diagnostic_pipelined_solver_pnr_harness --device xc7a200tsbg484-1 --xdc fpga/nexys_video/solver_pnr_harness.xdc --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --place-only
	$(PYTHON) scripts/analyze_openxc7_placement.py build/openxc7/xc7a200tsbg484-1/parallel_diagnostic_pipelined_solver_pnr_harness/parallel_diagnostic_pipelined_solver_pnr_harness_placed.json --output reference/results/openxc7_xc7a200tsbg484-1_parallel_diagnostic_pipelined_solver_placement_regions.json

openxc7-a200t-parallel-diagnostic-pipelined-solver-pnr:
	$(PYTHON) scripts/run_openxc7.py --top parallel_diagnostic_pipelined_solver_pnr_harness --device xc7a200tsbg484-1 --xdc fpga/nexys_video/solver_pnr_harness.xdc --nextpnr $(NEXTPNR) --placer-heap-timingweight 20

openxc7-terminal-current-pnr:
	$(PYTHON) scripts/run_openxc7.py --top terminal_current_pnr_harness --nextpnr $(NEXTPNR)

openxc7-terminal-current-half-parallel-pnr:
	$(PYTHON) scripts/run_openxc7.py --top half_parallel_terminal_current_pnr_harness --nextpnr $(NEXTPNR)

openxc7-terminal-current-half-parallel-timing-pnr:
	$(PYTHON) scripts/run_openxc7.py --top half_parallel_terminal_current_pnr_harness --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --run-tag timingweight20

openxc7-kcl-pnr:
	$(PYTHON) scripts/run_openxc7.py --top kcl_pnr_harness --nextpnr $(NEXTPNR)

openxc7-pipelined-kcl-pnr:
	$(PYTHON) scripts/run_openxc7.py --top pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR)

openxc7-deep-pipelined-kcl-pnr:
	$(PYTHON) scripts/run_openxc7.py --top deep_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR)

openxc7-max-pipelined-kcl-pnr:
	$(PYTHON) scripts/run_openxc7.py --top max_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR)

openxc7-diagnostic-pipelined-kcl-pnr:
	$(PYTHON) scripts/run_openxc7.py --top diagnostic_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR)

openxc7-decoupled-diagnostic-pipelined-kcl-pnr:
	$(PYTHON) scripts/run_openxc7.py --top decoupled_diagnostic_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR)

openxc7-decoupled-diagnostic-pipelined-kcl-timing-place:
	$(PYTHON) scripts/run_openxc7.py --top decoupled_diagnostic_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR) --placer-heap-timingweight 20 --run-tag timingweight20 --place-only

openxc7-shared-capacitor-decoupled-diagnostic-kcl-place:
	$(PYTHON) scripts/run_openxc7.py --top shared_capacitor_decoupled_diagnostic_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR) --place-only

openxc7-diagnostic-pipelined-kcl-soft-pack:
	$(PYTHON) scripts/run_openxc7.py --top diagnostic_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR) --soft-kcl-multipliers --run-tag soft_kcl --pack-only

openxc7-diagnostic-pipelined-kcl-soft-capacitors-place:
	$(PYTHON) scripts/run_openxc7.py --top diagnostic_pipelined_kcl_pnr_harness --nextpnr $(NEXTPNR) --soft-kcl-capacitor-multipliers --seed 2 --run-tag soft_kcl_capacitors_seed2 --place-only

openxc7-chord-pnr:
	$(PYTHON) scripts/run_openxc7.py --top chord_pnr_harness --nextpnr $(NEXTPNR)

openxc7-pipelined-chord-pnr:
	$(PYTHON) scripts/run_openxc7.py --top pipelined_chord_pnr_harness --nextpnr $(NEXTPNR)

tools:
	bash scripts/bootstrap_tools.sh

tools-openxc7: tools
	bash scripts/bootstrap_openxc7.sh

clean:
	rm -rf build obj_dir
