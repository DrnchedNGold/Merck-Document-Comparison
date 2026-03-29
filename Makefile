PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
DOCKER_IMAGE ?= python:3.12-slim

.PHONY: test test-local setup-test clean-venv desktop

setup-test:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt

test-local: setup-test
	$(VENV_PYTHON) -m pytest

test:
	docker run --rm -v "$(CURDIR):/workspace" -w /workspace $(DOCKER_IMAGE) \
		sh -lc "python -m pip install --upgrade pip && python -m pip install -r requirements-dev.txt && python -m pytest"

clean-venv:
	rm -rf $(VENV)

# GUI: requires Tcl/Tk (macOS Homebrew: `brew install python-tk@3.13`).
desktop:
	@./scripts/run_desktop.sh
