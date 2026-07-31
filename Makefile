PYTHON ?= .venv/bin/python
COMPOSE_ENV ?= $(if $(wildcard infra/.env),infra/.env,infra/.env.example)
COMPOSE := docker compose --env-file $(COMPOSE_ENV) -f infra/docker-compose.yml

.PHONY: bootstrap test lint typecheck build verify compose-config compose-build stack-up stack-down stack-logs smoke backup scan

bootstrap:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install --requirement backend/requirements.lock
	cd frontend && npm ci --no-audit

test:
	PYTHONPATH=backend $(PYTHON) -m unittest discover -s backend/tests -v

lint:
	cd frontend && npm run lint

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

compose-config:
	$(COMPOSE) --profile jobs config --quiet

verify: test lint typecheck build compose-config
	$(PYTHON) -m pip check

compose-build:
	$(COMPOSE) build backend frontend

stack-up:
	$(COMPOSE) up -d --wait

stack-down:
	$(COMPOSE) down

stack-logs:
	$(COMPOSE) logs -f --tail 100

smoke:
	$(PYTHON) scripts/smoke_stack.py --authenticated

backup:
	$(COMPOSE) --profile jobs run --rm backup

scan:
	$(COMPOSE) --profile jobs run --rm scanner
