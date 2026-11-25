.PHONY: help preflight up doctor urls lab-list lab-status lab-start lab-verify lab-reset diagnostics down validate test lint lab-suite

PYTHON ?= python3
LAB ?=

help:
	@printf '%s\n' 'K3s DevOps Lab targets: help preflight up doctor urls lab-list lab-status lab-start LAB=NN lab-verify LAB=NN lab-reset diagnostics down CONFIRM=yes validate lint test lab-suite'

preflight:
	@$(PYTHON) scripts/lab.py preflight
up:
	@$(PYTHON) scripts/lab.py up
doctor:
	@$(PYTHON) scripts/lab.py doctor
urls:
	@$(PYTHON) scripts/lab.py urls
lab-list:
	@$(PYTHON) scripts/lab.py lab-list
lab-status:
	@$(PYTHON) scripts/lab.py lab-status
lab-start:
	@$(PYTHON) scripts/lab.py lab-start $(LAB)
lab-verify:
	@$(PYTHON) scripts/lab.py lab-verify $(LAB)
lab-reset:
	@$(PYTHON) scripts/lab.py lab-reset
diagnostics:
	@$(PYTHON) scripts/lab.py diagnostics
down:
ifeq ($(CONFIRM),yes)
	@$(PYTHON) scripts/lab.py down --yes
else
	@printf '%s\n' 'Refusing teardown. Review README and run make down CONFIRM=yes to delete the dedicated cluster and its data.'; exit 2
endif

validate:
	@$(PYTHON) scripts/static_validate.py
test:
	@$(PYTHON) -m unittest discover -s tests -v
lint:
	@$(PYTHON) -m ruff check --select F app scripts tests
	@$(PYTHON) -m compileall -q app scripts tests
lab-suite:
	@$(PYTHON) scripts/lab_suite.py
