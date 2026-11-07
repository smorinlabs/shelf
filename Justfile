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

# Regenerate src/shelf/agent_skills from its master, plugins/shelf/skills (the pre-commit hook does this too)
sync-agent-skills:
    uv run --quiet python scripts/sync_agent_skills.py

# Install the repo's git hooks (lefthook.yml)
install-hooks:
    lefthook install
