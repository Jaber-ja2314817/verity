VENV := .venv
PY := $(abspath $(VENV))/bin/python
HAS_FRONTEND := $(wildcard frontend/package.json)

.PHONY: install dev test build docker eval

install:
	python3.12 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements-dev.txt
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm ci
endif

dev:
ifneq ($(HAS_FRONTEND),)
	(cd frontend && npm run dev) & \
	cd backend && $(PY) -m uvicorn app.main:app --reload --env-file ../.env
else
	cd backend && $(PY) -m uvicorn app.main:app --reload --env-file ../.env
endif

test:
	cd backend && $(PY) -m pytest
	cd backend && $(PY) -m ruff check . ../scripts
ifneq ($(HAS_FRONTEND),)
	cd frontend && npx tsc --noEmit
endif

build:
	cd frontend && npm run build

docker:
	docker build -t verity:local .

eval:
	$(PY) scripts/run_eval.py
