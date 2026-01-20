# MinIO / S3 Configuration

## Deployment Options

### Option 1: AWS S3

```bash
# Create S3 buckets
aws s3 mb s3://ml-portal-rag-prod
aws s3 mb s3://ml-portal-artifacts-prod
aws s3 mb s3://ml-portal-loki-logs-prod

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket ml-portal-rag-prod \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket ml-portal-rag-prod \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Lifecycle policy (delete old files after 90 days)
aws s3api put-bucket-lifecycle-configuration \
  --bucket ml-portal-rag-prod \
  --lifecycle-configuration file://lifecycle.json
```

**lifecycle.json:**
```json
{
  "Rules": [
    {
      "Id": "DeleteOldFiles",
      "Status": "Enabled",
      "Expiration": {
        "Days": 90
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      }
    }
  ]
}
```

### Option 2: Self-Hosted MinIO Cluster

```yaml
# minio-cluster.yaml
apiVersion: v1
kind: Service
metadata:
  name: minio
  namespace: external
spec:
  clusterIP: None
  ports:
  - port: 9000
    name: api
  - port: 9001
    name: console
  selector:
    app: minio
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: minio
  namespace: external
spec:
  serviceName: minio
  replicas: 4  # Minimum for erasure coding
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
      - name: minio
        image: minio/minio:latest
        args:
        - server
        - http://minio-{0...3}.minio.external.svc.cluster.local/data
        - --console-address
        - ":9001"
        env:
        - name: MINIO_ROOT_USER
          valueFrom:
            secretKeyRef:
              name: minio-credentials
              key: root-user
        - name: MINIO_ROOT_PASSWORD
          valueFrom:
            secretKeyRef:
              name: minio-credentials
              key: root-password
        ports:
        - containerPort: 9000
          name: api
        - containerPort: 9001
          name: console
        volumeMounts:
        - name: data
          mountPath: /data
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 500Gi
---
apiVersion: v1
kind: Service
metadata:
  name: minio-api
  namespace: external
spec:
  type: ClusterIP
  ports:
  - port: 9000
    targetPort: 9000
    name: api
  selector:
    app: minio
```

## Configuration

### Create Buckets

```bash
# Using mc (MinIO Client)
mc alias set myminio http://minio.example.com:9000 ACCESS_KEY SECRET_KEY

# Create buckets
mc mb myminio/rag
mc mb myminio/artifacts
mc mb myminio/loki-logs

# Enable versioning
mc version enable myminio/rag

# Set lifecycle policy
mc ilm add myminio/rag --expiry-days 90
```

### Access Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": ["arn:aws:iam::ACCOUNT:user/ml-portal-api"]
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::ml-portal-rag-prod",
        "arn:aws:s3:::ml-portal-rag-prod/*"
      ]
    }
  ]
}
```

## Kubernetes Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: s3-credentials
  namespace: ml-portal-main
type: Opaque
stringData:
  S3_ENDPOINT: "https://s3.example.com"
  S3_PUBLIC_ENDPOINT: "https://files.example.com"
  S3_ACCESS_KEY: "<ACCESS_KEY>"
  S3_SECRET_KEY: "<SECRET_KEY>"
  S3_BUCKET_RAG: "rag"
  S3_BUCKET_ARTIFACTS: "artifacts"
```

## Monitoring

### MinIO Metrics

```yaml
apiVersion: v1
kind: Service
metadata:
  name: minio-metrics
  namespace: external
  labels:
    app: minio
spec:
  ports:
  - port: 9000
    name: metrics
  selector:
    app: minio
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: minio
  namespace: external
spec:
  selector:
    matchLabels:
      app: minio
  endpoints:
  - port: metrics
    path: /minio/v2/metrics/cluster
    interval: 30s
```

### Key Metrics

- **Disk usage**: < 80%
- **Request rate**: requests/sec
- **Error rate**: < 0.1%
- **Latency**: p95 < 100ms
- **Throughput**: MB/s

## Backup & Recovery

### Bucket Replication

```bash
# Enable replication to another region
mc replicate add myminio/rag \
  --remote-bucket arn:aws:s3:::ml-portal-rag-backup \
  --priority 1
```

### Disaster Recovery

```bash
# Sync to backup location
mc mirror myminio/rag s3backup/rag

# Restore from backup
mc mirror s3backup/rag myminio/rag
```

## Performance Tuning

### Caching

```bash
# Enable disk cache
export MINIO_CACHE="on"
export MINIO_CACHE_DRIVES="/mnt/cache1,/mnt/cache2"
export MINIO_CACHE_EXCLUDE="*.tmp"
export MINIO_CACHE_QUOTA=80
export MINIO_CACHE_AFTER=3
export MINIO_CACHE_WATERMARK_LOW=70
export MINIO_CACHE_WATERMARK_HIGH=90
```

### Compression

```bash
# Enable compression for specific extensions
mc admin config set myminio compression \
  enable="on" \
  extensions=".txt,.log,.csv,.json,.tar" \
  mime_types="text/*,application/json,application/xml"
```

## Security

### Encryption

```bash
# Enable encryption at rest
mc admin config set myminio/ kms_kes \
  endpoint=https://kes.example.com:7373 \
  key_name=minio-default-key
```

### Access Logs

```bash
# Enable audit logging
mc admin config set myminio audit_webhook:1 \
  endpoint="http://audit-service:8080/minio" \
  auth_token="Bearer TOKEN"
```

## Troubleshooting

### Check Cluster Health

```bash
# MinIO admin info
mc admin info myminio

# Check disk usage
mc admin prometheus metrics myminio
```

### Heal Corrupted Data

```bash
# Start healing
mc admin heal myminio
```
