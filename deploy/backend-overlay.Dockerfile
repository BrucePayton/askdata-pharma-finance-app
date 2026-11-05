# The platform supplies authentication, workspace authorization, run persistence and review APIs.
ARG PLATFORM_IMAGE
FROM ${PLATFORM_IMAGE}
WORKDIR /app
COPY core/modules/pharma /app/core/modules/pharma
COPY assets/pharma /app/assets/pharma
COPY assets/skills /app/assets/skills
COPY assets/domain-applications/pharma-finance /app/assets/domain-applications/pharma-finance
COPY scripts/pharma /app/scripts/pharma
