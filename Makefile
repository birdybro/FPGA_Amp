PYTHON ?= python3
NGSPICE ?= ngspice
VERILATOR ?= verilator

.PHONY: all reference analysis test python-test plots spice spice-all rtl lint synth clean tools

all: reference test

reference:
	$(PYTHON) scripts/run_reference.py

analysis:
	$(PYTHON) scripts/analyze_frontend.py
	$(PYTHON) scripts/characterize_solver.py
	$(PYTHON) scripts/compare_fixed_float.py

plots:
	$(PYTHON) scripts/run_reference.py --plots

spice:
	$(PYTHON) scripts/run_spice.py --ngspice $(NGSPICE)

spice-all: spice
	$(PYTHON) scripts/spice_level_sweep.py
	$(PYTHON) scripts/compare_spice_python.py

rtl:
	$(PYTHON) scripts/run_rtl.py --verilator $(VERILATOR)

lint:
	$(PYTHON) scripts/run_rtl.py --verilator $(VERILATOR) --lint-only

synth:
	$(PYTHON) scripts/run_synthesis.py

python-test:
	$(PYTHON) -m unittest discover -s model/tests -v

test: python-test rtl

tools:
	bash scripts/bootstrap_tools.sh

clean:
	rm -rf build obj_dir
