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

# Copy plugins/shelf/skills into the package after editing a skill (tests fail until they match)
sync-agent-skills:
    rm -rf src/shelf/agent_skills
    cp -R plugins/shelf/skills src/shelf/agent_skills
