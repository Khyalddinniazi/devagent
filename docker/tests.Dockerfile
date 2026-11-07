# Image devagent uses to run a project's tests in a sandbox on machines without macOS sandbox-exec.
#   make docker-image                          (builds devagent-tests:latest)
# The container runs with no network, a read-only filesystem except the repo (/work) and /tmp,
# no Linux capabilities and none of the host's environment: see wrap_in_docker() in devagent/security.py.
# For other languages, point `test_image` in .devagent.toml at your own image (for example node:22).
FROM python:3.12-slim

RUN pip install --no-cache-dir pytest pytest-asyncio

WORKDIR /work
CMD ["python", "-m", "pytest", "-q"]
