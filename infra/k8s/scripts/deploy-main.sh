#!/bin/bash
# =============================================================================
# Deploy ML Portal Main Cluster
# =============================================================================

set -e

ENVIRONMENT=${1:-prod}
NAMESPACE="ml-portal-main"
CHART_DIR="$(dirname "$0")/../clusters/main"

echo "🚀 Deploying ML Portal Main Cluster to ${ENVIRONMENT}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
  echo "❌ Invalid environment: ${ENVIRONMENT}"
  echo "Usage: $0 [dev|staging|prod]"
  exit 1
fi

# Check prerequisites
echo "📋 Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }

# Check cluster connection
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Cannot connect to cluster"; exit 1; }

# Create namespace if not exists
echo "📦 Creating namespace ${NAMESPACE}..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Label namespace for network policies
kubectl label namespace ${NAMESPACE} name=${NAMESPACE} --overwrite

# Install/upgrade Helm chart
echo "📊 Deploying Helm chart..."
helm upgrade --install ml-portal-main ${CHART_DIR} \
  --namespace ${NAMESPACE} \
  --values ${CHART_DIR}/values.yaml \
  --values ${CHART_DIR}/values-${ENVIRONMENT}.yaml \
  --wait \
  --timeout 10m \
  --create-namespace

# Wait for rollout
echo "⏳ Waiting for rollout to complete..."
kubectl rollout status deployment/ml-portal-main-api -n ${NAMESPACE} --timeout=5m
kubectl rollout status deployment/ml-portal-main-frontend -n ${NAMESPACE} --timeout=5m
kubectl rollout status deployment/ml-portal-main-workers -n ${NAMESPACE} --timeout=5m
kubectl rollout status deployment/ml-portal-main-embedding -n ${NAMESPACE} --timeout=5m

# Check pod status
echo "🔍 Checking pod status..."
kubectl get pods -n ${NAMESPACE}

# Run smoke tests
echo "🧪 Running smoke tests..."
API_URL=$(kubectl get ingress ml-portal-main -n ${NAMESPACE} -o jsonpath='{.spec.rules[0].host}')
if [ -n "$API_URL" ]; then
  echo "Testing API health endpoint..."
  curl -f "https://${API_URL}/api/v1/healthz" || echo "⚠️  Health check failed"
fi

echo "✅ Deployment complete!"
echo "📍 Application URL: https://${API_URL}"
