# Redis Configuration

## Managed Service Setup

### AWS ElastiCache

```bash
# Create ElastiCache Redis cluster
aws elasticache create-replication-group \
  --replication-group-id ml-portal-prod \
  --replication-group-description "ML Portal Redis" \
  --engine redis \
  --engine-version 7.0 \
  --cache-node-type cache.r6g.large \
  --num-cache-clusters 2 \
  --automatic-failover-enabled \
  --at-rest-encryption-enabled \
  --transit-encryption-enabled \
  --auth-token <STRONG_TOKEN> \
  --cache-subnet-group-name ml-portal-subnet-group \
  --security-group-ids sg-xxxxx \
  --snapshot-retention-limit 7 \
  --snapshot-window "03:00-05:00"
```

### Yandex Managed Redis

```bash
# Create Yandex Managed Redis cluster
yc managed-redis cluster create \
  --name ml-portal-prod \
  --environment production \
  --network-name ml-portal-network \
  --resource-preset hm2.medium \
  --disk-size 16 \
  --redis-version 7.0 \
  --password <STRONG_PASSWORD> \
  --backup-window-start hours=3,minutes=0
```

## Configuration

### Database Allocation

- **DB 0**: Celery broker, SSE events, idempotency keys
- **DB 1**: Celery results
- **DB 2**: Application cache (optional)
- **DB 3**: Session storage (optional)

### Persistence

```conf
# Enable AOF persistence
appendonly yes
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# RDB snapshots
save 900 1
save 300 10
save 60 10000
```

### Memory Management

```conf
# Max memory policy
maxmemory 13gb
maxmemory-policy allkeys-lru

# Eviction samples
maxmemory-samples 5
```

## Kubernetes Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: redis-credentials
  namespace: ml-portal-main
type: Opaque
stringData:
  REDIS_URL: "redis://:PASSWORD@redis.example.com:6379/0"
  CELERY_BROKER_URL: "redis://:PASSWORD@redis.example.com:6379/0"
  CELERY_RESULT_BACKEND: "redis://:PASSWORD@redis.example.com:6379/1"
```

## Monitoring

### Redis Exporter

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-exporter
  namespace: external
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis-exporter
  template:
    metadata:
      labels:
        app: redis-exporter
    spec:
      containers:
      - name: redis-exporter
        image: oliver006/redis_exporter:latest
        env:
        - name: REDIS_ADDR
          value: "redis.example.com:6379"
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-credentials
              key: REDIS_PASSWORD
        ports:
        - containerPort: 9121
          name: metrics
---
apiVersion: v1
kind: Service
metadata:
  name: redis-exporter
  namespace: external
spec:
  ports:
  - port: 9121
    targetPort: 9121
    name: metrics
  selector:
    app: redis-exporter
```

## Key Metrics

- **Memory usage**: < 80%
- **Hit rate**: > 90%
- **Connected clients**: < max_clients
- **Evicted keys**: minimal
- **Replication lag**: < 1s

## Troubleshooting

### Connection Issues

```bash
# Test connection
redis-cli -h redis.example.com -a PASSWORD ping

# Check info
redis-cli -h redis.example.com -a PASSWORD info

# Monitor commands
redis-cli -h redis.example.com -a PASSWORD monitor
```

### Memory Issues

```bash
# Check memory usage
redis-cli -h redis.example.com -a PASSWORD info memory

# Find large keys
redis-cli -h redis.example.com -a PASSWORD --bigkeys

# Clear specific database
redis-cli -h redis.example.com -a PASSWORD -n 0 FLUSHDB
```
