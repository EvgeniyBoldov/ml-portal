# Qdrant Configuration

## Deployment Options

### Option 1: Qdrant Cloud (Managed)

```bash
# Sign up at https://cloud.qdrant.io
# Create cluster via UI
# Get connection details:
# - URL: https://xxxxx.qdrant.io
# - API Key: <API_KEY>
```

### Option 2: Self-Hosted Cluster

```yaml
# qdrant-cluster.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
  namespace: external
spec:
  serviceName: qdrant
  replicas: 3
  selector:
    matchLabels:
      app: qdrant
  template:
    metadata:
      labels:
        app: qdrant
    spec:
      containers:
      - name: qdrant
        image: qdrant/qdrant:v1.7.0
        ports:
        - containerPort: 6333
          name: http
        - containerPort: 6334
          name: grpc
        env:
        - name: QDRANT__SERVICE__HTTP_PORT
          value: "6333"
        - name: QDRANT__SERVICE__GRPC_PORT
          value: "6334"
        - name: QDRANT__CLUSTER__ENABLED
          value: "true"
        - name: QDRANT__CLUSTER__P2P__PORT
          value: "6335"
        volumeMounts:
        - name: qdrant-storage
          mountPath: /qdrant/storage
        resources:
          requests:
            cpu: 2000m
            memory: 8Gi
          limits:
            cpu: 4000m
            memory: 16Gi
  volumeClaimTemplates:
  - metadata:
      name: qdrant-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 100Gi
---
apiVersion: v1
kind: Service
metadata:
  name: qdrant
  namespace: external
spec:
  clusterIP: None
  ports:
  - port: 6333
    name: http
  - port: 6334
    name: grpc
  selector:
    app: qdrant
---
apiVersion: v1
kind: Service
metadata:
  name: qdrant-http
  namespace: external
spec:
  type: ClusterIP
  ports:
  - port: 6333
    targetPort: 6333
    name: http
  selector:
    app: qdrant
```

## Configuration

### Collection Setup

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url="http://qdrant.example.com:6333", api_key="<API_KEY>")

# Create collection for RAG documents
client.create_collection(
    collection_name="rag_documents",
    vectors_config=VectorParams(
        size=384,  # all-MiniLM-L6-v2 dimension
        distance=Distance.COSINE
    ),
    replication_factor=2,
    write_consistency_factor=1,
    on_disk_payload=True,
    optimizers_config={
        "indexing_threshold": 20000,
        "memmap_threshold": 50000
    }
)
```

### Replication

```yaml
# Enable replication in config
cluster:
  enabled: true
  p2p:
    port: 6335
  consensus:
    tick_period_ms: 100
```

## Kubernetes Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: qdrant-credentials
  namespace: ml-portal-main
type: Opaque
stringData:
  QDRANT_URL: "http://qdrant.external.svc:6333"
  QDRANT_API_KEY: "<API_KEY>"
```

## Monitoring

### Metrics Endpoint

Qdrant exposes Prometheus metrics at `/metrics`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: qdrant-metrics
  namespace: external
  labels:
    app: qdrant
spec:
  ports:
  - port: 6333
    name: metrics
  selector:
    app: qdrant
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: qdrant
  namespace: external
spec:
  selector:
    matchLabels:
      app: qdrant
  endpoints:
  - port: metrics
    path: /metrics
    interval: 30s
```

### Key Metrics

- **Collection size**: number of vectors
- **Index build time**: should be reasonable
- **Search latency**: p95 < 100ms
- **Memory usage**: < 80%
- **Disk usage**: < 80%

## Backup & Recovery

### Snapshot Creation

```bash
# Create snapshot via API
curl -X POST "http://qdrant.example.com:6333/collections/rag_documents/snapshots"

# Download snapshot
curl "http://qdrant.example.com:6333/collections/rag_documents/snapshots/snapshot-2024-01-20.snapshot" \
  -o snapshot.tar
```

### Automated Backups

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: qdrant-backup
  namespace: external
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: curlimages/curl:latest
            command:
            - sh
            - -c
            - |
              curl -X POST "http://qdrant:6333/collections/rag_documents/snapshots"
              # Upload to S3 or other storage
          restartPolicy: OnFailure
```

## Performance Tuning

### Indexing

```python
# Optimize for search speed
client.update_collection(
    collection_name="rag_documents",
    optimizer_config={
        "indexing_threshold": 10000,
        "memmap_threshold": 20000,
        "max_segment_size": 200000
    }
)
```

### Search Optimization

```python
# Use filters to reduce search space
results = client.search(
    collection_name="rag_documents",
    query_vector=embedding,
    limit=10,
    query_filter={
        "must": [
            {"key": "tenant_id", "match": {"value": "tenant-123"}}
        ]
    }
)
```

## Troubleshooting

### Check Cluster Status

```bash
# Get cluster info
curl "http://qdrant.example.com:6333/cluster"

# Check collection info
curl "http://qdrant.example.com:6333/collections/rag_documents"
```

### Reindex Collection

```python
# If index is corrupted or slow
client.update_collection(
    collection_name="rag_documents",
    optimizer_config={"indexing_threshold": 0}
)
```
