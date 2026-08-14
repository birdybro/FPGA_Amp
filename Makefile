PYTHON ?= python3
NGSPICE ?= ngspice
VERILATOR ?= verilator

.PHONY: all reference analysis arithmetic-bounds accuracy-sweeps factorized-study factorized-frequency factorized-frequency-wide factorized-frequency-trapezoidal factorized-domain state-drift state-wide state-wide-audio linear-modes wide-rtl-audio wide-rtl-frequency trapezoidal-rtl-frequency trapezoidal-rtl-recovery wide-rtl-overload terminal-banked-rtl-metrics trapezoidal-terminal-banked-rtl-metrics banked-rtl-overload terminal-banked-rtl-overload banked-accuracy banked-selector banked-threshold banked-slew-selector banked-error-decomposition banked-iterations grid-current-resolution wide-stream-rtl-frequency trapezoidal-stream-rtl-frequency trapezoidal-terminal-stream-rtl-frequency wide-stream-rtl-alias wav-null-regression audio-regression spice-python-frequency overload-study overload-wide overload-trapezoidal overload-long overload-severe-long overload-seven-second overload-iterations overload-banked trapezoidal-overload precision-study resampler test python-test plots spice spice-all rtl factorized-rtl chord-rtl wide-chord-rtl network-rtl wide-network-rtl trapezoidal-network-rtl solver-rtl solver-factorized-rtl wide-solver-rtl trapezoidal-solver-rtl banked-solver-rtl terminal-banked-solver-rtl trapezoidal-terminal-banked-solver-rtl trapezoidal-banked-solver-rtl halfband-rtl stream-rtl stream-factorized-rtl stream-wide-rtl stream-terminal-banked-rtl stream-trapezoidal-rtl stream-trapezoidal-terminal-banked-rtl guarded-stream-rtl mute-rtl async-fifo-rtl i2s-rtl i2s-bridge-rtl calibration-rtl frame-scheduler-rtl mono-adapter-rtl i2s-mono-top-rtl lint synth synth-factorized synth-chord synth-wide-chord synth-network synth-wide-network synth-solver synth-solver-factorized synth-wide-solver synth-trapezoidal-solver synth-banked-solver synth-terminal-banked-solver synth-trapezoidal-terminal-banked-solver synth-trapezoidal-banked-solver synth-halfband synth-stream synth-stream-factorized synth-stream-wide synth-stream-terminal-banked synth-stream-trapezoidal synth-stream-trapezoidal-terminal-banked synth-stream-guarded synth-mute synth-async-fifo synth-i2s synth-i2s-bridge synth-calibration synth-frame-scheduler synth-mono-adapter synth-i2s-mono-top clean tools

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

factorized-rtl:
	$(PYTHON) scripts/run_factorized_rtl.py --verilator $(VERILATOR)

chord-rtl:
	$(PYTHON) scripts/run_chord_rtl.py --verilator $(VERILATOR)

wide-chord-rtl:
	$(PYTHON) scripts/run_wide_chord_rtl.py --verilator $(VERILATOR)

network-rtl:
	$(PYTHON) scripts/run_network_rtl.py --verilator $(VERILATOR)

wide-network-rtl:
	$(PYTHON) scripts/run_wide_network_rtl.py --verilator $(VERILATOR)

trapezoidal-network-rtl:
	$(PYTHON) scripts/run_trapezoidal_network_rtl.py --verilator $(VERILATOR)

solver-rtl:
	$(PYTHON) scripts/run_solver_rtl.py --verilator $(VERILATOR)

solver-factorized-rtl:
	$(PYTHON) scripts/run_solver_rtl.py --verilator $(VERILATOR) --factorized

wide-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR)

trapezoidal-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --trapezoidal

banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --banked

terminal-banked-solver-rtl:
	$(PYTHON) scripts/run_wide_solver_rtl.py --verilator $(VERILATOR) --banked --terminal-correction

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

guarded-stream-rtl:
	$(PYTHON) scripts/run_guarded_stream_rtl.py --verilator $(VERILATOR)

mute-rtl:
	$(PYTHON) scripts/run_mute_rtl.py --verilator $(VERILATOR)

async-fifo-rtl:
	$(PYTHON) scripts/run_async_fifo_rtl.py --verilator $(VERILATOR)

i2s-rtl:
	$(PYTHON) scripts/run_i2s_rtl.py --verilator $(VERILATOR)

i2s-bridge-rtl:
	$(PYTHON) scripts/run_i2s_bridge_rtl.py --verilator $(VERILATOR)

calibration-rtl:
	$(PYTHON) scripts/run_calibration_rtl.py --verilator $(VERILATOR)

frame-scheduler-rtl:
	$(PYTHON) scripts/run_frame_scheduler_rtl.py --verilator $(VERILATOR)

mono-adapter-rtl:
	$(PYTHON) scripts/run_mono_adapter_rtl.py --verilator $(VERILATOR)

i2s-mono-top-rtl:
	$(PYTHON) scripts/run_i2s_mono_top_rtl.py --verilator $(VERILATOR)

lint:
	$(PYTHON) scripts/run_rtl.py --verilator $(VERILATOR) --lint-only

synth:
	$(PYTHON) scripts/run_synthesis.py

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

synth-halfband:
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top interpolator_16x
	$(PYTHON) scripts/run_synthesis.py --top decimator_16x

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

synth-stream-guarded:
	$(PYTHON) scripts/generate_wide_network_vectors.py
	$(PYTHON) scripts/generate_wide_chord_vectors.py
	$(PYTHON) scripts/generate_factorized_tube.py
	$(PYTHON) scripts/generate_halfband_rtl_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top phono_stream_mono_wide_guarded

synth-mute:
	$(PYTHON) scripts/run_synthesis.py --top output_mute_ramp

synth-async-fifo:
	$(PYTHON) scripts/run_synthesis.py --top async_fifo

synth-i2s:
	$(PYTHON) scripts/run_synthesis.py --top i2s_receiver
	$(PYTHON) scripts/run_synthesis.py --top i2s_transmitter

synth-i2s-bridge:
	$(PYTHON) scripts/run_synthesis.py --top i2s_async_bridge

synth-calibration:
	$(PYTHON) scripts/run_synthesis.py --top pcm24_to_q8_24
	$(PYTHON) scripts/run_synthesis.py --top q8_24_to_pcm24

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

python-test:
	$(PYTHON) -m unittest discover -s model/tests -v

test: python-test arithmetic-bounds rtl factorized-rtl chord-rtl wide-chord-rtl network-rtl wide-network-rtl trapezoidal-network-rtl solver-rtl solver-factorized-rtl wide-solver-rtl trapezoidal-solver-rtl banked-solver-rtl terminal-banked-solver-rtl trapezoidal-banked-solver-rtl trapezoidal-terminal-banked-solver-rtl halfband-rtl stream-rtl stream-factorized-rtl stream-wide-rtl stream-terminal-banked-rtl stream-trapezoidal-rtl stream-trapezoidal-terminal-banked-rtl guarded-stream-rtl mute-rtl async-fifo-rtl i2s-rtl i2s-bridge-rtl calibration-rtl frame-scheduler-rtl mono-adapter-rtl i2s-mono-top-rtl

tools:
	bash scripts/bootstrap_tools.sh

clean:
	rm -rf build obj_dir
