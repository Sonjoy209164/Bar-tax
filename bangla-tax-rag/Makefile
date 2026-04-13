PYTHON ?= python3
VENV ?= .venv
PIP ?= $(VENV)/bin/pip

.PHONY: install run-api run-api-dense run-ui verify-dense test

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run-api:
	$(VENV)/bin/uvicorn app.main:app --reload

run-api-dense:
	bash ./scripts/run_api_real_dense.sh

run-ui:
	$(VENV)/bin/streamlit run app/ui/streamlit_app.py

verify-dense:
	bash ./scripts/verify_real_dense.sh

test:
	$(VENV)/bin/pytest
