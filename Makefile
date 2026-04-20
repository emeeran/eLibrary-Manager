# Dawnstar eBook Manager - Makefile
# Provides convenient commands for development and deployment

.PHONY: help dev test lint format clean docker-build docker-up docker-down docker-logs

help:
	@echo "Dawnstar eBook Manager - Available commands:"
	@echo "  make dev         - Run development server"
	@echo "  make test        - Run tests"
	@echo "  make lint        - Run linters"
	@echo "  make format      - Format code"
	@echo "  make clean       - Clean generated files"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up     - Start Docker containers"
	@echo "  make docker-down   - Stop Docker containers"
	@echo "  make docker-logs   - View Docker logs"

dev:
	PYTHONPATH=backend uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	PYTHONPATH=backend uv run pytest tests/ -v --cov=app --cov-report=html

lint:
	uv run ruff check backend/app/
	uv run mypy backend/app/

format:
	uv run black backend/app/
	uv run ruff check --fix backend/app/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.py[cod]' -delete
	find . -type f -name '*.pyo' -delete
	rm -rf .pytest_cache htmlcov .coverage

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f dawnstar

docker-restart:
	docker-compose restart

.PHONY: install
install:
	uv sync
	pre-commit install

.PHONY: check
check: lint test

.PHONY: run
run: dev
