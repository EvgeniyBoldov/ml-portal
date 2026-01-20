#!/bin/bash
# =============================================================================
# Deploy ML Portal Observability Cluster
# =============================================================================

set -e

NAMESPACE="ml-portal-observability"
CHART_DIR="$(dirname "$0")/../clusters/observability"

echo "🚀 Deploying ML Portal Observability Stack"

# Check prerequisites
echo "📋 Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl not found"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }

# Add Helm repositories
echo "📚 Adding Helm repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Create namespace if not exists
echo "📦 Creating namespace ${NAMESPACE}..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Install/upgrade Helm chart
echo "📊 Deploying Observability stack..."
helm upgrade --install ml-portal-observability ${CHART_DIR} \
  --namespace ${NAMESPACE} \
  --values ${CHART_DIR}/values.yaml \
  --wait \
  --timeout 15m \
  --create-namespace

# Wait for Prometheus
echo "⏳ Waiting for Prometheus..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=prometheus -n ${NAMESPACE} --timeout=5m

# Wait for Grafana
echo "⏳ Waiting for Grafana..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n ${NAMESPACE} --timeout=5m

# Get Grafana admin password
echo "🔑 Grafana admin credentials:"
GRAFANA_PASSWORD=$(kubectl get secret -n ${NAMESPACE} ml-portal-observability-grafana -o jsonpath="{.data.admin-password}" | base64 --decode)
echo "  Username: admin"
echo "  Password: ${GRAFANA_PASSWORD}"

# Get service URLs
echo "📍 Service URLs:"
GRAFANA_URL=$(kubectl get ingress -n ${NAMESPACE} -o jsonpath='{.items[?(@.metadata.name=="ml-portal-observability-grafana")].spec.rules[0].host}')
if [ -n "$GRAFANA_URL" ]; then
  echo "  Grafana: https://${GRAFANA_URL}"
fi

echo "✅ Observability stack deployment complete!"
