#!/bin/bash
# =============================================================================
# Create Kubernetes Secrets for ML Portal
# =============================================================================

set -e

ENVIRONMENT=${1:-prod}
NAMESPACE="ml-portal-main"

echo "🔐 Creating secrets for ${ENVIRONMENT} environment"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
  echo "❌ Invalid environment: ${ENVIRONMENT}"
  echo "Usage: $0 [dev|staging|prod]"
  exit 1
fi

# Function to generate random password
generate_password() {
  openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
}

# Function to prompt for secret value
prompt_secret() {
  local var_name=$1
  local default_value=$2
  local prompt_text=$3
  
  if [ -n "$default_value" ]; then
    read -p "${prompt_text} [${default_value}]: " value
    echo "${value:-$default_value}"
  else
    read -p "${prompt_text}: " value
    echo "${value}"
  fi
}

echo "📝 Please provide the following values:"
echo ""

# Database
DATABASE_URL=$(prompt_secret "DATABASE_URL" "" "PostgreSQL connection URL (postgresql://user:pass@host:5432/db)")
POSTGRES_PASSWORD=$(prompt_secret "POSTGRES_PASSWORD" "$(generate_password)" "PostgreSQL password")

# Redis
REDIS_URL=$(prompt_secret "REDIS_URL" "" "Redis URL (redis://:password@host:6379/0)")
CELERY_BROKER_URL=$(prompt_secret "CELERY_BROKER_URL" "${REDIS_URL}" "Celery broker URL")
CELERY_RESULT_BACKEND=$(prompt_secret "CELERY_RESULT_BACKEND" "" "Celery result backend URL (redis://:password@host:6379/1)")

# S3/MinIO
S3_ACCESS_KEY=$(prompt_secret "S3_ACCESS_KEY" "" "S3 access key")
S3_SECRET_KEY=$(prompt_secret "S3_SECRET_KEY" "$(generate_password)" "S3 secret key")

# JWT
JWT_SECRET=$(prompt_secret "JWT_SECRET" "$(generate_password)" "JWT secret (min 256 bits)")

# LLM
LLM_API_KEY=$(prompt_secret "LLM_API_KEY" "" "LLM API key (Groq/OpenAI/etc)")

# Qdrant
QDRANT_API_KEY=$(prompt_secret "QDRANT_API_KEY" "" "Qdrant API key (optional)")

echo ""
echo "📦 Creating Kubernetes secret..."

# Create secret
kubectl create secret generic app-secrets \
  --namespace=${NAMESPACE} \
  --from-literal=DATABASE_URL="${DATABASE_URL}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --from-literal=REDIS_URL="${REDIS_URL}" \
  --from-literal=CELERY_BROKER_URL="${CELERY_BROKER_URL}" \
  --from-literal=CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND}" \
  --from-literal=S3_ACCESS_KEY="${S3_ACCESS_KEY}" \
  --from-literal=S3_SECRET_KEY="${S3_SECRET_KEY}" \
  --from-literal=JWT_SECRET="${JWT_SECRET}" \
  --from-literal=LLM_API_KEY="${LLM_API_KEY}" \
  --from-literal=QDRANT_API_KEY="${QDRANT_API_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Secrets created successfully!"
echo ""
echo "⚠️  IMPORTANT: Store these credentials securely!"
echo "Consider using external-secrets-operator or sealed-secrets for production."
