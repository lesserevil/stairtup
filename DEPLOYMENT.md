# Deployment Guide

This guide provides production deployment instructions for the StairtUp. It covers deployment options, configuration, monitoring, and scaling.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Options](#deployment-options)
3. [Docker Deployment](#docker-deployment)
4. [Cloud Deployment](#cloud-deployment)
5. [Production Configuration](#production-configuration)
6. [Monitoring & Logging](#monitoring--logging)
7. [Scaling & High Availability](#scaling--high-availability)
8. [Security Considerations](#security-considerations)
9. [Backup & Recovery](#backup--recovery)
10. [Post-Deployment Checklist](#post-deployment-checklist)

---

## Prerequisites

### System Requirements

- **Minimum**: 2 vCPUs, 4GB RAM, 20GB storage
- **Recommended**: 4 vCPUs, 8GB RAM, 50GB storage
- **Python**: 3.12+
- **Docker**: 20.10+ with Docker Compose 2.0+
- **OpenAI API Key** (for LLM-based JD generation)

### Network Requirements

- HTTP/HTTPS access on port 9754 (or configured port)
- Internal messaging between agents (no external dependencies)
- Access to `bd` CLI for bead management
- Access to OpenAI API (if using LLM)

### Security Prerequisites

- Strong passwords/credentials
- HTTPS/TLS enabled
- Firewall rules configured
- SSH access to server
- Monitoring enabled

---

## Deployment Options

### Option 1: Docker Compose (Recommended)

Best for: Most deployments, easy management, fast setup

**Pros:**
- Simple deployment
- Isolated environment
- Easy updates
- Good for development and small production

**Cons:**
- Single-node limitation
- No auto-scaling
- Database in container

```bash
# Production mode
docker-compose --profile full up --build -d

# View logs
docker-compose logs -f web
docker-compose logs -f recruiter
docker-compose logs -f spawner
```

### Option 2: Kubernetes (Advanced)

Best for: Large deployments, high availability, auto-scaling

**Pros:**
- High availability
- Auto-scaling
- Resource management
- Service discovery

**Cons:**
- Complex setup
- Higher operational overhead

```bash
# Deploy with Helm (example)
helm install agent-swarm ./helm/chart

# Scale web service
kubectl scale deployment agent-swarm-web --replicas=3

# View pods
kubectl get pods -l app=agent-swarm
```

### Option 3: Bare Metal

Best for: Complete control, custom infrastructure, regulatory compliance

**Pros:**
- Full control
- No container overhead
- Custom configuration

**Cons:**
- More operational work
- Manual updates
- Higher complexity

```bash
# Install dependencies
pip install -r requirements.txt
pip install gunicorn uvicorn[standard]

# Start with systemd
sudo systemctl start agent-swarm
```

---

## Docker Deployment

### Create Production Dockerfile

```dockerfile
# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy dependencies
COPY --from=builder /root/.local /root/.local

# Copy application
COPY app/ ./app/

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 9754

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9754/health || exit 1

# Run with gunicorn
CMD ["gunicorn", "app.main:app", "--workers", "4", "--bind", "0.0.0.0:9754"]
```

### Docker Compose Production Setup

Create or update `docker-compose.yml`:

```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "9754:9754"
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
      - WEB_CONCURRENCY=4
    volumes:
      - ./employees.jsonl:/app/employees.jsonl
      - ./slaick.jsonl:/app/slaick.jsonl
      - ./spawn_requests.jsonl:/app/spawn_requests.jsonl
    networks:
      - agent-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9754/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

  recruiter:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
      - FAST_POLL_INTERVAL=5.0
      - SLOW_POLL_INTERVAL=30.0
      - HEARTBEAT_INTERVAL=10
      - HEARTBEAT_TTL=30
    volumes:
      - ./employees.jsonl:/app/employees.jsonl
      - ./slaick.jsonl:/app/slaick.jsonl
    networks:
      - agent-network
    depends_on:
      - web

  spawner:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
      - HEARTBEAT_INTERVAL=10
      - HEARTBEAT_TTL=30
    volumes:
      - ./employees.jsonl:/app/employees.jsonl
      - ./slaick.jsonl:/app/slaick.jsonl
    networks:
      - agent-network
    depends_on:
      - web

networks:
  agent-network:
    driver: bridge

volumes:
  data:
```

### Deploy Docker Containers

```bash
# Pull latest changes
git pull origin main

# Build and start
docker-compose --profile full up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f web recruiter spawner
```

---

## Cloud Deployment

### AWS EC2

#### Step 1: Launch Instance

```bash
# Launch t3.large (2 vCPUs, 8GB RAM) in us-east-1
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --count 1 \
  --instance-type t3.large \
  --key-name my-key-pair \
  --security-group-ids sg-0abcdef1234567890 \
  --subnet-id subnet-0abcdef1234567890
```

#### Step 2: Configure Instance

```bash
# SSH into instance
ssh -i /path/to/key.pem ubuntu@ec2-xx-xx-xx-xx.compute-1.amazonaws.com

# Install Docker
sudo apt-get update
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get install docker-compose-plugin

# Clone repository
git clone https://github.com/lesserevil/stairtup.git
cd stairtup
```

#### Step 3: Deploy

```bash
# Set environment variables
export OPENAI_API_KEY=your_key_here
export DEBUG=false

# Deploy
docker-compose --profile full up -d --build

# Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 9754/tcp
sudo ufw enable
```

### Google Cloud Compute Engine

#### Step 1: Create Instance

```bash
gcloud compute instances create agent-swarm \
  --zone=us-central1-a \
  --machine-type=n1-standard-4 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --maintenance-policy=TERMINATE \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

#### Step 2: SSH and Deploy

```bash
# SSH into instance
gcloud compute ssh agent-swarm --zone=us-central1-a

# Install and deploy (same as AWS)
# ...
```

### Azure VM

#### Step 1: Create VM

```bash
# Create Standard_D4s_v3 (4 vCPUs, 16GB RAM)
az vm create \
  --resource-group MyResourceGroup \
  --name agent-swarm \
  --image Ubuntu2204 \
  --size Standard_D4s_v3 \
  --admin-username azureuser \
  --admin-password StrongP@ssw0rd \
  --public-ip-sku Standard
```

#### Step 2: SSH and Deploy

```bash
# SSH into instance
ssh azureuser@<public-ip>

# Install and deploy (same as AWS)
# ...
```

---

## Production Configuration

### Environment Variables

Create `.env.production` file:

```bash
# Application
DEBUG=false
LOG_LEVEL=INFO
APP_NAME=stairtup
APP_VERSION=0.1.0

# OpenAI API (for LLM-based JD generation)
OPENAI_API_KEY=sk-proj-your-api-key-here
OPENAI_MODEL=gpt-4o-mini

# Swarm Settings
FAST_POLL_INTERVAL=5.0
SLOW_POLL_INTERVAL=30.0
HEARTBEAT_INTERVAL=10
HEARTBEAT_TTL=30

# Budget Management
BUDGET_ENABLED=true
ANNUAL_BUDGET=1000.0
MONTHLY_BUDGET=100.0
DAILY_BUDGET=10.0

# Monitoring
ENABLE_METRICS=true
METRICS_ENDPOINT=http://localhost:9090
SENTRY_DSN=https://xxx@sentry.io/xxx

# Security
SECRET_KEY=change-this-to-a-random-secret
ALLOWED_HOSTS=*

# Database (if needed)
DATABASE_URL=sqlite:///./swarm.db
```

### Nginx Reverse Proxy

Install Nginx for HTTPS:

```nginx
# /etc/nginx/sites-available/agent-swarm

upstream stairtup {
    server localhost:9754;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://stairtup;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /static/ {
        alias /app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/agent-swarm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Certbot SSL

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renew
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## Monitoring & Logging

### Logging Setup

#### Structured Logging

Enable structured logging in `docker-compose.yml`:

```yaml
environment:
  - LOG_FORMAT=json  # JSON format for parsing
  - LOG_LEVEL=INFO
  - SENTRY_DSN=your-sentry-dsn
```

#### Log Aggregation

**Option 1: Docker Logs**

```bash
# Export logs to files
docker-compose logs -f > logs/$(date +%Y%m%d-%H%M%S).log

# Stream all logs
docker-compose logs --tail=1000 -f
```

**Option 2: ELK Stack**

```yaml
# Add to docker-compose.yml
services:
  elk:
    image: elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"

  filebeat:
    image: elastic/filebeat:8.11.0
    volumes:
      - ./log:/logs
      - ./filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
    command: filebeat -e

  kibana:
    image: kibana:8.11.0
    ports:
      - "5601:5601"
    depends_on:
      - elk
```

**Option 3: Cloud Watch**

```yaml
# Add Amazon CloudWatch Logs
services:
  web:
    image: agent-swarm:latest
    logging:
      driver: "awslogs"
      options:
        awslogs-group: /ecs/agent-swarm
        awslogs-region: us-east-1
        awslogs-stream-prefix: web
```

### Metrics & Monitoring

#### Prometheus + Grafana

```yaml
# docker-compose.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

volumes:
  prometheus_data:
  grafana_data:
```

Create `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'agent-swarm'
    static_configs:
      - targets: ['web:9754']
```

### Health Checks

Implement health endpoints:

```python
# app/main.py
from fastapi import Request
from fastapi.responses import JSONResponse

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "stairtup",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat(),
        "check": {
            "database": check_database(),
            "workers": check_workers(),
            "disk_space": check_disk(),
        }
    }

def check_database():
    try:
        # Check database connectivity
        return "OK"
    except Exception:
        return "FAIL"

def check_workers():
    # Check if processes are running
    return "OK"

def check_disk():
    # Check disk space
    import shutil
    total, used, free = shutil.disk_usage("/")
    return f"{free // (2**30)}GB free"
```

---

## Scaling & High Availability

### Horizontal Scaling

#### Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml agent-swarm

# Scale services
docker service scale agent-swarm_web=3
docker service scale agent-swarm_recruiter=2
```

#### Kubernetes

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-swarm-web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent-swarm-web
  template:
    metadata:
      labels:
        app: agent-swarm-web
    spec:
      containers:
      - name: web
        image: agent-swarm:latest
        ports:
        - containerPort: 9754
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 9754
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 9754
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-swarm-web-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-swarm-web
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Vertical Scaling

Adjust resource limits in `docker-compose.yml`:

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G
        reservations:
          cpus: '2'
          memory: 2G
```

### Load Balancing

For horizontal scaling, add a load balancer:

**Nginx:**

```nginx
upstream stairtup_cluster {
    least_conn;
    server 10.0.0.1:9754;
    server 10.0.0.2:9754;
    server 10.0.0.3:9754;
}

server {
    listen 9754;
    server_name your-domain.com;

    location / {
        proxy_pass http://stairtup_cluster;
        # ... proxy settings
    }
}
```

---

## Security Considerations

### Network Security

```yaml
# docker-compose.yml
services:
  web:
    networks:
      - internal
    expose:
      - "9754"

networks:
  internal:
    internal: true
```

### Authentication

Add API authentication:

```python
# app/main.py
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key

@app.get("/api/data", dependencies=[Depends(verify_api_key)])
async def protected_data():
    return {"status": "success"}
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

@app.get("/api/tasks")
@limiter.limit("10/minute")
async def list_tasks(request: Request):
    return {"tasks": [...]}

def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )
```

### Secrets Management

Use environment variables or secrets managers:

**Option 1: Environment Variables (simple)**

```bash
# .env.production
OPENAI_API_KEY=sk-proj-xxx
SECRET_KEY=super-secret-key
```

**Option 2: Docker Secrets**

```bash
# Create secret
echo "sk-proj-xxx" | docker secret create openai_api_key -

# Use in service
services:
  web:
    secrets:
      - openai_api_key
    environment:
      - OPENAI_API_KEY_FILE=/run/secrets/openai_api_key

secrets:
  openai_api_key:
    external: true
```

**Option 3: AWS Secrets Manager**

```python
import boto3

def get_secret():
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId='agent-swarm/openai-api-key')
    return response['SecretString']

app = FastAPI()
@app.on_event("startup")
async def startup():
    app.state.OPENAI_API_KEY = get_secret()
```

---

## Backup & Recovery

### Database Backup

```bash
# Backup JSONL files
tar -czf backup-$(date +%Y%m%d-%H%M%S).tar.gz employees.jsonl slaick.jsonl

# Copy to S3
aws s3 cp backup-*.tar.gz s3://agent-swarm-backups/

# Restore
tar -xzf backup-20260223-120000.tar.gz
```

### Automated Backups

Create `backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="/logs/backup-$DATE.log"

echo "Starting backup at $(date)" | tee -a $LOG_FILE

# Backup files
tar -czf $BACKUP_DIR/backup-$DATE.tar.gz employees.jsonl slaick.jsonl spawn_requests.jsonl >> $LOG_FILE 2>&1

# Encrypt backup
gpg --symmetric --cipher-algo AES256 $BACKUP_DIR/backup-$DATE.tar.gz >> $LOG_FILE 2>&1

# Cleanup old backups (keep last 30)
find $BACKUP_DIR -name "backup-*.tar.gz.gpg" -mtime +30 -delete >> $LOG_FILE 2>&1

echo "Backup completed at $(date)" | tee -a $LOG_FILE
```

Add to crontab:

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/backup.sh >> /var/log/backup.log 2>&1
```

### Disaster Recovery

```bash
# Recovery checklist
# 1. Stop services
docker-compose stop

# 2. Restore data
tar -xzf backup-20260223-120000.tar.gz

# 3. Start services
docker-compose start

# 4. Verify health
curl http://localhost:9754/health
```

---

## Post-Deployment Checklist

### Before Going Live

- [ ] HTTPS/TLS configured
- [ ] Environment variables set
- [ ] Security hardening done
- [ ] Firewall rules configured
- [ ] Monitoring and logging enabled
- [ ] Backup strategy in place
- [ ] Error tracking configured
- [ ] Load testing completed
- [ ] Documentation updated
- [ ] Team notified

### Daily Operations

- [ ] Health checks passing
- [ ] Log review completed
- [ ] Backup verified
- [ ] Performance monitoring
- [ ] Security updates reviewed
- [ ] Service restarts documented

### Monthly Operations

- [ ] Review security vulnerabilities
- [ ] Update dependencies
- [ ] Review costs and optimization
- [ ] Test disaster recovery
- [ ] Update documentation
- [ ] Capacity planning

### Quarterly Operations

- [ ] Full system review
- [ ] Security audit
- [ ] Load testing
- [ ] Plan upgrades

---

## Additional Resources

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [FastAPI Production Guide](https://fastapi.tiangolo.com/deployment/)
- [Cloud NAT Gateway Guide](https://cloud.google.com/vpc/docs/nat-gateway)
- [AWS Security Best Practices](https://docs.aws.amazon.com/security/best-practices/)
- [Sentry Documentation](https://docs.sentry.io/)

---

**Questions?** Create a GitHub [Issue](https://github.com/lesserevil/stairtup/issues) or join the [Discussion](https://github.com/lesserevil/stairtup/discussions).
