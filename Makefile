.PHONY: check lint typecheck test format demo-repo

DEMO ?= /tmp/devagent-demo

check: lint typecheck test  ## run everything CI runs

lint:
	.venv/bin/ruff check devagent tests bench/run.py
	.venv/bin/ruff format --check devagent tests bench/run.py

typecheck:
	.venv/bin/mypy devagent bench/run.py

test:
	.venv/bin/pytest -q

format:
	.venv/bin/ruff check devagent tests bench/run.py --fix
	.venv/bin/ruff format devagent tests bench/run.py

demo-repo:  ## copy the sample project into its own git repo to try devagent on
	rm -rf $(DEMO) && cp -R examples/sample_repo $(DEMO)
	cd $(DEMO) && git init -q -b main && git add -A && git -c user.name=demo -c user.email=demo@example.com commit -qm "sample project"
	@echo "Demo repo ready: $(DEMO)"
