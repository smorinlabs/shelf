default: all

all: format lint typecheck test

format:
    uv run ruff format .

lint:
    uv run ruff check .

typecheck:
    uv run ty check

test:
    uv run pytest -q
