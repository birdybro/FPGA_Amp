PYTHON ?= python3
NGSPICE ?= ngspice
VERILATOR ?= verilator

.PHONY: all reference analysis accuracy-sweeps factorized-study factorized-frequency overload-study overload-iterations precision-study resampler test python-test plots spice spice-all rtl factorized-rtl chord-rtl network-rtl solver-rtl solver-factorized-rtl halfband-rtl stream-rtl stream-factorized-rtl lint synth synth-factorized synth-chord synth-network synth-solver synth-solver-factorized synth-halfband synth-stream synth-stream-factorized clean tools

all: reference test

reference:
	$(PYTHON) scripts/run_reference.py

analysis:
	$(PYTHON) scripts/analyze_frontend.py
	$(PYTHON) scripts/characterize_solver.py
	$(PYTHON) scripts/compare_fixed_float.py

accuracy-sweeps:
	$(PYTHON) scripts/characterize_fixed_levels.py
	$(PYTHON) scripts/study_low_level_lut.py

factorized-study:
	$(PYTHON) scripts/study_factorized_tube.py

factorized-frequency:
	$(PYTHON) scripts/characterize_factorized_frequency.py

overload-study:
	$(PYTHON) scripts/characterize_overload_recovery.py

overload-iterations:
	$(PYTHON) scripts/study_overload_iterations.py

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

network-rtl:
	$(PYTHON) scripts/run_network_rtl.py --verilator $(VERILATOR)

solver-rtl:
	$(PYTHON) scripts/run_solver_rtl.py --verilator $(VERILATOR)

solver-factorized-rtl:
	$(PYTHON) scripts/run_solver_rtl.py --verilator $(VERILATOR) --factorized

halfband-rtl:
	$(PYTHON) scripts/run_halfband_rtl.py --verilator $(VERILATOR)

stream-rtl:
	$(PYTHON) scripts/run_stream_rtl.py --verilator $(VERILATOR)

stream-factorized-rtl:
	$(PYTHON) scripts/run_stream_rtl.py --verilator $(VERILATOR) --factorized

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

synth-network:
	$(PYTHON) scripts/generate_network_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top network_rhs_v1
	$(PYTHON) scripts/run_synthesis.py --top network_kcl_v1

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

python-test:
	$(PYTHON) -m unittest discover -s model/tests -v

test: python-test rtl factorized-rtl chord-rtl network-rtl solver-rtl solver-factorized-rtl halfband-rtl stream-rtl stream-factorized-rtl

tools:
	bash scripts/bootstrap_tools.sh

clean:
	rm -rf build obj_dir
