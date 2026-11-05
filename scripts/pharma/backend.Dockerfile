# A reviewed existing runtime is required; pass its immutable digest for releases.
ARG BACKEND_BASE=askdata-finance-backend:licensing-candidate-20261014
FROM ${BACKEND_BASE}
COPY core/modules/pharma /app/core/modules/pharma
COPY core/modules/application_center/workflows.py core/modules/application_center/run_worker.py core/modules/application_center/run_models.py core/modules/application_center/finance_runs.py /app/core/modules/application_center/
COPY core/modules/application_center/review_contracts.py /app/core/modules/application_center/review_contracts.py
COPY core/modules/askdata/report_lifecycle_views.py /app/core/modules/askdata/report_lifecycle_views.py
COPY core/modules/workspace/__init__.py /app/core/modules/workspace/__init__.py
COPY assets/pharma /app/assets/pharma
COPY assets/domain-applications/pharma-finance /app/assets/domain-applications/pharma-finance
COPY assets/skills /app/assets/skills
COPY scripts/pharma /app/scripts/pharma
