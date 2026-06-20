.PHONY: lint format test dev worker

package ?= app tests

lint:
	uv run ruff check $(package)
	uv run ruff format --check $(package)
	uv run ty check $(package)

format:
	uv run ruff check --fix $(package)
	uv run ruff format $(package)

test:
	uv run pytest

dev:
	docker compose up -d postgres redis
	uv run alembic upgrade head
	uv run uvicorn app.main:app --reload

worker:
	uv run taskiq worker app.tasks.broker:broker app.tasks.confirm
