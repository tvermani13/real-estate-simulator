PYTHON ?= .venv/bin/python
COMPOSE_ENV ?= $(if $(wildcard infra/.env),infra/.env,infra/.env.example)
COMPOSE := docker compose --env-file $(COMPOSE_ENV) -f infra/docker-compose.yml

.PHONY: smoke-platform upgrade-rehearsal bootstrap test lint typecheck build audit verify compose-config compose-build stack-up stack-down stack-logs smoke backup scan scan-str

bootstrap:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	python3 backend/vendor/verify_vendored.py
	cd backend && ../$(PYTHON) -m pip install --requirement requirements.lock
	cd frontend && npm ci --no-audit

test:
	PYTHONPATH=backend $(PYTHON) -m unittest discover -s backend/tests -v

smoke-platform:
	$(PYTHON) scripts/smoke_platform.py

upgrade-rehearsal:
	@test -n "$(SOURCE)" || (echo 'usage: make upgrade-rehearsal SOURCE=/path/to/copy-of-live.db' && exit 2)
	cd backend && PYTHONPATH=. ../$(PYTHON) -m app.jobs.upgrade_rehearsal --source $(SOURCE)

lint:
	cd frontend && npm run lint

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

audit:
	cd frontend && npm audit --audit-level=high

compose-config:
	$(COMPOSE) --profile jobs config --quiet

verify: test smoke-platform lint typecheck build audit compose-config
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

scan-str:
	$(COMPOSE) --profile jobs run --rm scanner python -m app.jobs.scan_str_acquisitions
