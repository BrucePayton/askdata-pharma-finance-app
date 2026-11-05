#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
docker run --rm --network none --read-only --tmpfs /tmp --entrypoint python \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  -e LANGFUSE_HOST=http://127.0.0.1:39999 -e PGSQL_DB_HOST=127.0.0.1 -e PGSQL_DB_PORT=5432 \
  -e PGSQL_DB_USERNAME=test -e PGSQL_DB_PASSWORD=test -e PGSQL_DB_NAME=test -e DB_SCHEMA=public \
  -e ASKDATA_PRODUCTION_MODE=false -e JWT_ALGORITHM=HS256 -e JWT_SECRET_KEY=test-only \
  -e LLM_DEFAULT_MODE_NAME=qwen-flash \
  -e 'LLM_PARAMS_CONFIG=[{"provider":"openai_api_compatible","model_names":["qwen-flash","qwen3.6-plus","qwen3-vl-flash"],"base_url":"http://127.0.0.1:39999/v1","api_key":"test-only"}]' \
  -e REDIS_HOST=127.0.0.1 -e REDIS_PORT=6379 -e REDIS_DB=0 -e REDIS_PASSWORD= \
  -v "$root:/audit:ro" -v /dev/null:/audit/.env:ro \
  -w /audit "${PHARMA_BACKEND_IMAGE:-askdata-pharma-backend:demo-v1}" \
  -m pytest -p pytest_asyncio.plugin -p no:cacheprovider \
  tests/pharma tests/test_domain_application_contracts.py tests/test_application_runtime_context.py \
  tests/test_domain_application_service.py tests/finance/test_fixed_application_runs.py -q --tb=short
