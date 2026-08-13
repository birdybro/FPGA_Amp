PYTHON ?= python3
NGSPICE ?= ngspice
VERILATOR ?= verilator

.PHONY: all reference analysis precision-study resampler test python-test plots spice spice-all rtl chord-rtl lint synth synth-chord clean tools

all: reference test

reference:
	$(PYTHON) scripts/run_reference.py

analysis:
	$(PYTHON) scripts/analyze_frontend.py
	$(PYTHON) scripts/characterize_solver.py
	$(PYTHON) scripts/compare_fixed_float.py

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

chord-rtl:
	$(PYTHON) scripts/run_chord_rtl.py --verilator $(VERILATOR)

lint:
	$(PYTHON) scripts/run_rtl.py --verilator $(VERILATOR) --lint-only

synth:
	$(PYTHON) scripts/run_synthesis.py

synth-chord:
	$(PYTHON) scripts/generate_chord_vectors.py
	$(PYTHON) scripts/run_synthesis.py --top chord_corrector_v1

python-test:
	$(PYTHON) -m unittest discover -s model/tests -v

test: python-test rtl chord-rtl

tools:
	bash scripts/bootstrap_tools.sh

clean:
	rm -rf build obj_dir
