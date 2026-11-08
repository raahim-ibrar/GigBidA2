PYTHON ?= python
COMPOSE = docker compose --project-directory . -f infra/docker-compose.yml

.PHONY: dev test eval seed demo lint api schema graphs
dev:
	$(COMPOSE) up --build
test:
	$(PYTHON) -m pytest
eval:
	$(PYTHON) -m evals.runners.suite $(EVAL_ARGS)
seed:
	$(PYTHON) scripts/seed.py
demo:
	$(PYTHON) scripts/demo.py
lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) scripts/check_structure.py
api:
	$(PYTHON) -m uvicorn apps.api.main:app --reload
schema:
	$(PYTHON) scripts/export_openapi.py
	cd apps/web && npm run generate:api
graphs:
	$(PYTHON) scripts/render_graphs.py
