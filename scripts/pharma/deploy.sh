#!/usr/bin/env bash
# Run after the existing finance foundation stack has passed its readiness checks.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
base=${PHARMA_BACKEND_BASE:-askdata-finance-backend:licensing-candidate-20261014}
tag=${PHARMA_IMAGE_TAG:-demo-v1}
export PHARMA_IMAGE_TAG="$tag" PHARMA_BACKEND_IMAGE="askdata-pharma-backend:$tag"
# A clean machine can build the dependency/runtime baseline from the repository.
if ! docker image inspect "$base" >/dev/null 2>&1; then docker build -t "$base" .; fi
docker build -f scripts/pharma/backend.Dockerfile --build-arg "BACKEND_BASE=$base" -t "$PHARMA_BACKEND_IMAGE" .
docker build -f deployments/deployment_finance/finance-web.Dockerfile --build-arg FINANCE_WEB_BASE=/pharma-finance/ -t "askdata-pharma-web:$tag" .
bash scripts/pharma/check.sh
python3 scripts/pharma/local_resources.py database
python3 scripts/pharma/local_resources.py identity
compose=(docker compose --env-file deployments/deployment_finance/.env -f deployments/deployment_finance/compose.yaml -f deployments/deployment_finance/compose.pharma.yaml)
"${compose[@]}" up -d --no-deps --no-build --pull never askdata_backend finance-application-worker pharma-web pharma-share
for attempt in {1..40}; do
  if curl -fsS http://127.0.0.1:18080/api/system/ready >/dev/null; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:18080/api/system/ready >/dev/null
python3 scripts/pharma/local_resources.py platform
python3 scripts/pharma/local_resources.py access
python3 scripts/pharma/verify_live.py
printf '%s\n' 'Local demo: http://localhost:18190/pharma-finance/' 'To share: python3 scripts/pharma/share.py'
