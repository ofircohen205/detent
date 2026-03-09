# ─── Makefile ─────────────────────────────────────────────────────────────────
# Usage: make <target>
# Requires: uv (https://docs.astral.sh/uv/), docker, docker compose

.DEFAULT_GOAL := help
.PHONY: help install dev lint format typecheck test test-unit test-integration \
        clean docker-build docker-run docker-stop docker-logs compose-up \
        compose-down compose-logs

PYTHON     = uv run python
PYTEST     = uv run pytest
RUFF       = uv run ruff
MYPY       = uv run mypy

IMAGE_NAME = detent
IMAGE_TAG  ?= latest
CONTAINER  = detent-proxy
PORT       ?= 7070


# ─── Help ─────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\nTargets:\n"} \
	     /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)


# ─── Development ──────────────────────────────────────────────────────────────

install: ## Install all dependencies (including dev extras) and setup pre-commit
	uv sync --all-extras --dev
	uv run pre-commit install

dev: install ## Alias for install (sets up dev environment)

repl: ## Drop into a Python REPL with detent on the path
	$(PYTHON) -c "import detent; import IPython; IPython.start_ipython()"


# ─── Lint & Format ────────────────────────────────────────────────────────────

lint: ## Run Ruff linter
	$(RUFF) check .

format: ## Auto-format code with Ruff
	$(RUFF) format .

format-check: ## Check formatting without writing (used in CI)
	$(RUFF) format --check .

typecheck: ## Run mypy type checker
	$(MYPY) detent/

check: lint format-check typecheck ## Run all static checks (lint + format + typecheck)


# ─── Testing ──────────────────────────────────────────────────────────────────

test: ## Run the full test suite
	$(PYTEST) tests/ -v

test-unit: ## Run unit tests only (fast, no external tool deps)
	$(PYTEST) tests/unit/ -v

test-integration: ## Run integration tests (requires ruff, mypy, etc. installed)
	$(PYTEST) tests/integration/ -v

test-cov: ## Run tests with coverage report
	$(PYTEST) tests/ --cov=detent --cov-report=term-missing --cov-report=html

test-watch: ## Re-run tests on file change (requires pytest-watch)
	uv run ptw tests/ -- -v


# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts, caches, and coverage reports
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete


# ─── Docker (single container) ────────────────────────────────────────────────

docker-build: ## Build the detent Docker image
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

docker-run: ## Run detent proxy in foreground (port $(PORT))
	docker run --rm --name $(CONTAINER) \
	  -p $(PORT):7070 \
	  -v $(PWD)/detent.yaml:/app/detent.yaml:ro \
	  $(IMAGE_NAME):$(IMAGE_TAG)

docker-run-bg: ## Run detent proxy in background
	docker run -d --name $(CONTAINER) \
	  -p $(PORT):7070 \
	  -v $(PWD)/detent.yaml:/app/detent.yaml:ro \
	  $(IMAGE_NAME):$(IMAGE_TAG)

docker-stop: ## Stop and remove the background container
	docker stop $(CONTAINER) && docker rm $(CONTAINER)

docker-logs: ## Tail logs from the running container
	docker logs -f $(CONTAINER)

docker-shell: ## Open a shell inside the running container
	docker exec -it $(CONTAINER) /bin/bash


# ─── Docker Compose (full local stack) ────────────────────────────────────────

compose-up: ## Start all services (proxy + optional tooling sidecar)
	docker compose up --build

compose-up-bg: ## Start all services in background
	docker compose up --build -d

compose-down: ## Stop and remove all compose services
	docker compose down

compose-logs: ## Tail logs for all compose services
	docker compose logs -f

compose-shell: ## Open a shell inside the proxy compose service
	docker compose exec proxy /bin/bash
