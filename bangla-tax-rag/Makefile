PYTHON ?= python3
VENV ?= .venv
PIP ?= $(VENV)/bin/pip

.PHONY: install run-api run-ui test

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run-api:
	$(VENV)/bin/uvicorn app.main:app --reload

run-ui:
	$(VENV)/bin/streamlit run app/ui/streamlit_app.py

test:
	$(VENV)/bin/pytest
