.PHONY: check
check:
	@command -v uv >/dev/null || { echo "missing: uv"; exit 1; }
	@command -v just >/dev/null || { echo "missing: just"; exit 1; }
	@command -v git >/dev/null || { echo "missing: git"; exit 1; }
	@uv run python -c 'import sys; assert sys.version_info >= (3, 12), "need python >= 3.12"'
	@echo "check: ok"
