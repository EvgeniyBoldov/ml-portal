# PostgreSQL Configuration

## Managed Service Setup

### AWS RDS

```bash
# Create RDS PostgreSQL instance
aws rds create-db-instance \
  --db-instance-identifier ml-portal-prod \
  --db-instance-class db.r6g.xlarge \
  --engine postgres \
  --engine-version 15.4 \
  --master-username ml_portal \
  --master-user-password <STRONG_PASSWORD> \
  --allocated-storage 100 \
  --storage-type gp3 \
  --storage-encrypted \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --preferred-maintenance-window "sun:04:00-sun:05:00" \
  --multi-az \
  --publicly-accessible false \
  --vpc-security-group-ids sg-xxxxx \
  --db-subnet-group-name ml-portal-subnet-group
```

### Yandex Managed PostgreSQL

```bash
# Create Yandex Managed PostgreSQL cluster
yc managed-postgresql cluster create \
  --name ml-portal-prod \
  --environment production \
  --network-name ml-portal-network \
  --resource-preset s2.medium \
  --disk-type network-ssd \
  --disk-size 100 \
  --postgresql-version 15 \
  --user name=ml_portal,password=<STRONG_PASSWORD> \
  --database name=ml_portal,owner=ml_portal \
  --backup-window-start hours=3,minutes=0 \
  --backup-retain-period-days=7
```

## Configuration

### Required Settings

```sql
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create database and user
CREATE DATABASE ml_portal;
CREATE USER ml_portal WITH PASSWORD '<STRONG_PASSWORD>';
GRANT ALL PRIVILEGES ON DATABASE ml_portal TO ml_portal;

-- Performance tuning
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET work_mem = '10MB';
ALTER SYSTEM SET min_wal_size = '1GB';
ALTER SYSTEM SET max_wal_size = '4GB';
ALTER SYSTEM SET max_worker_processes = 4;
ALTER SYSTEM SET max_parallel_workers_per_gather = 2;
ALTER SYSTEM SET max_parallel_workers = 4;
```

### Connection Pooling (PgBouncer)

```ini
[databases]
ml_portal = host=postgres.example.com port=5432 dbname=ml_portal

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
reserve_pool_timeout = 3
server_lifetime = 3600
server_idle_timeout = 600
log_connections = 1
log_disconnections = 1
```

## Kubernetes Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-credentials
  namespace: ml-portal-main
type: Opaque
stringData:
  DATABASE_URL: "postgresql://ml_portal:<PASSWORD>@postgres.example.com:5432/ml_portal"
  POSTGRES_PASSWORD: "<PASSWORD>"
```

## Monitoring

### Postgres Exporter

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-exporter
  namespace: external
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres-exporter
  template:
    metadata:
      labels:
        app: postgres-exporter
    spec:
      containers:
      - name: postgres-exporter
        image: prometheuscommunity/postgres-exporter:latest
        env:
        - name: DATA_SOURCE_NAME
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: DATABASE_URL
        ports:
        - containerPort: 9187
          name: metrics
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-exporter
  namespace: external
  labels:
    app: postgres-exporter
spec:
  ports:
  - port: 9187
    targetPort: 9187
    name: metrics
  selector:
    app: postgres-exporter
```

## Backup & Recovery

### Automated Backups

- **Frequency**: Daily at 03:00 UTC
- **Retention**: 7 days
- **Type**: Full backup + WAL archiving

### Manual Backup

```bash
# Create manual backup
pg_dump -h postgres.example.com -U ml_portal -d ml_portal -F c -f ml_portal_backup_$(date +%Y%m%d).dump

# Restore from backup
pg_restore -h postgres.example.com -U ml_portal -d ml_portal -c ml_portal_backup_20240120.dump
```

### Point-in-Time Recovery (PITR)

```bash
# Restore to specific timestamp
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier ml-portal-prod \
  --target-db-instance-identifier ml-portal-restored \
  --restore-time 2024-01-20T10:00:00Z
```

## Performance Monitoring

### Key Metrics

- **Connection pool usage**: < 80%
- **Query latency**: p95 < 100ms
- **Replication lag**: < 1s
- **Disk usage**: < 80%
- **Cache hit ratio**: > 95%

### Queries to Monitor

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query 
FROM pg_stat_activity 
WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 minutes';

-- Cache hit ratio
SELECT 
  sum(heap_blks_read) as heap_read,
  sum(heap_blks_hit)  as heap_hit,
  sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)) as ratio
FROM pg_statio_user_tables;

-- Database size
SELECT pg_size_pretty(pg_database_size('ml_portal'));
```

## Security

### SSL/TLS

```bash
# Enable SSL connections
ALTER SYSTEM SET ssl = on;
ALTER SYSTEM SET ssl_cert_file = '/path/to/server.crt';
ALTER SYSTEM SET ssl_key_file = '/path/to/server.key';
```

### Network Security

- **VPC**: Private subnet only
- **Security Group**: Allow port 5432 from K8s cluster CIDR only
- **Encryption**: At rest (KMS) and in transit (SSL/TLS)

### Access Control

```sql
-- Revoke public access
REVOKE ALL ON DATABASE ml_portal FROM PUBLIC;

-- Grant specific permissions
GRANT CONNECT ON DATABASE ml_portal TO ml_portal;
GRANT USAGE ON SCHEMA public TO ml_portal;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ml_portal;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ml_portal;
```

## Troubleshooting

### Connection Issues

```bash
# Test connection
psql -h postgres.example.com -U ml_portal -d ml_portal

# Check connection limits
SELECT * FROM pg_settings WHERE name = 'max_connections';

# Kill idle connections
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'idle' AND state_change < now() - interval '10 minutes';
```

### Performance Issues

```bash
# Analyze query performance
EXPLAIN ANALYZE SELECT ...;

# Update statistics
ANALYZE;

# Reindex
REINDEX DATABASE ml_portal;
```
