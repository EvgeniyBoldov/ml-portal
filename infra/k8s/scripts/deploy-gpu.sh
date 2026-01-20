#!/bin/bash
# =============================================================================
# Deploy ML Portal GPU Cluster
# =============================================================================

set -e

ENVIRONMENT=${1:-prod}
NAMESPACE="ml-portal-gpu"
CHART_DIR="$(dirname "$0")/../clusters/gpu"

echo "🚀 Deploying ML Portal GPU Cluster to ${ENVIRONMENT}"

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

# Check GPU nodes
echo "🔍 Checking GPU nodes..."
GPU_NODES=$(kubectl get nodes -l gpu=true --no-headers 2>/dev/null | wc -l)
if [ "$GPU_NODES" -eq 0 ]; then
  echo "⚠️  Warning: No GPU nodes found. Make sure GPU nodes are labeled with 'gpu=true'"
fi

# Create namespace if not exists
echo "📦 Creating namespace ${NAMESPACE}..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Label namespace
kubectl label namespace ${NAMESPACE} name=${NAMESPACE} --overwrite

# Install/upgrade Helm chart
echo "📊 Deploying Helm chart..."
helm upgrade --install ml-portal-gpu ${CHART_DIR} \
  --namespace ${NAMESPACE} \
  --values ${CHART_DIR}/values.yaml \
  --wait \
  --timeout 15m \
  --create-namespace

# Wait for rollout
echo "⏳ Waiting for rollout to complete..."
kubectl rollout status deployment/llm-service -n ${NAMESPACE} --timeout=10m || echo "⚠️  LLM service rollout timeout (model loading can take time)"
kubectl rollout status deployment/rerank-service -n ${NAMESPACE} --timeout=5m

# Check pod status
echo "🔍 Checking pod status..."
kubectl get pods -n ${NAMESPACE}

# Check GPU allocation
echo "🎮 Checking GPU allocation..."
kubectl describe nodes -l gpu=true | grep -A 5 "Allocated resources"

echo "✅ GPU Cluster deployment complete!"
