# Infrastructure Specification

## Overview

This document specifies the complete infrastructure setup for Curious Now, including Docker containers, Kubernetes deployments, and secrets management.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   CloudFlare                                     │
│                           (CDN, DDoS Protection, WAF)                           │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Kubernetes Cluster                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                            Ingress Controller                            │   │
│  │                              (nginx-ingress)                             │   │
│  └─────────────────────────────────┬───────────────────────────────────────┘   │
│                                    │                                            │
│         ┌──────────────────────────┼──────────────────────────┐                │
│         │                          │                          │                │
│         ▼                          ▼                          ▼                │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐          │
│  │  Frontend   │           │   Backend   │           │   Worker    │          │
│  │  (Next.js)  │           │  (FastAPI)  │           │  (Celery)   │          │
│  │  3 replicas │           │  3 replicas │           │  2 replicas │          │
│  └─────────────┘           └──────┬──────┘           └──────┬──────┘          │
│                                   │                          │                 │
│                    ┌──────────────┴──────────────┐          │                 │
│                    │                             │          │                 │
│                    ▼                             ▼          ▼                 │
│             ┌─────────────┐              ┌─────────────┐                      │
│             │ PostgreSQL  │              │    Redis    │                      │
│             │  (Primary)  │              │  (Cluster)  │                      │
│             └──────┬──────┘              └─────────────┘                      │
│                    │                                                          │
│                    ▼                                                          │
│             ┌─────────────┐                                                   │
│             │ PostgreSQL  │                                                   │
│             │  (Replica)  │                                                   │
│             └─────────────┘                                                   │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        External Secrets Operator                         │ │
│  │                    (Syncs from AWS Secrets Manager)                      │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Docker Configuration

### Backend Dockerfile

`Dockerfile`

```dockerfile
# ─────────────────────────────────────────────────────────────────
# Stage 1: Builder
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────
# Stage 2: Runtime
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim as runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -s /bin/false appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend Dockerfile

`frontend/Dockerfile`

```dockerfile
# ─────────────────────────────────────────────────────────────────
# Stage 1: Dependencies
# ─────────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@8 --activate

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# ─────────────────────────────────────────────────────────────────
# Stage 2: Builder
# ─────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@8 --activate

# Copy dependencies
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build arguments for environment variables
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SENTRY_DSN

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN
ENV NEXT_TELEMETRY_DISABLED=1

# Build application
RUN pnpm build

# ─────────────────────────────────────────────────────────────────
# Stage 3: Runner
# ─────────────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

# Set environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built assets
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/api/health || exit 1

# Run application
CMD ["node", "server.js"]
```

### Worker Dockerfile

`Dockerfile.worker`

```dockerfile
# ─────────────────────────────────────────────────────────────────
# Stage 1: Builder (same as backend)
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────
# Stage 2: Runtime
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim as runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -s /bin/false appuser

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER appuser

# Run Celery worker
CMD ["celery", "-A", "src.worker.celery_app", "worker", "--loglevel=info", "--concurrency=4"]
```

---

## Docker Compose (Development)

`docker-compose.yml`

```yaml
version: '3.8'

services:
  # ─────────────────────────────────────────────────────────────────
  # Backend API
  # ─────────────────────────────────────────────────────────────────
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://curious:curious@postgres:5432/curious
      - REDIS_URL=redis://redis:6379
      - ENVIRONMENT=development
      - DEBUG=true
      - SECRET_KEY=dev-secret-key-change-in-production
      - CORS_ORIGINS=http://localhost:3000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./src:/app/src:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ─────────────────────────────────────────────────────────────────
  # Frontend
  # ─────────────────────────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - NEXT_PUBLIC_API_URL=http://localhost:8000
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=development
    depends_on:
      - backend

  # ─────────────────────────────────────────────────────────────────
  # Worker (Background Jobs)
  # ─────────────────────────────────────────────────────────────────
  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql://curious:curious@postgres:5432/curious
      - REDIS_URL=redis://redis:6379
      - ENVIRONMENT=development
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./src:/app/src:ro

  # ─────────────────────────────────────────────────────────────────
  # Celery Beat (Scheduler)
  # ─────────────────────────────────────────────────────────────────
  scheduler:
    build:
      context: .
      dockerfile: Dockerfile.worker
    command: celery -A src.worker.celery_app beat --loglevel=info
    environment:
      - DATABASE_URL=postgresql://curious:curious@postgres:5432/curious
      - REDIS_URL=redis://redis:6379
      - ENVIRONMENT=development
    depends_on:
      - worker

  # ─────────────────────────────────────────────────────────────────
  # PostgreSQL
  # ─────────────────────────────────────────────────────────────────
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=curious
      - POSTGRES_PASSWORD=curious
      - POSTGRES_DB=curious
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U curious -d curious"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ─────────────────────────────────────────────────────────────────
  # Redis
  # ─────────────────────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    command: redis-server --appendonly yes

  # ─────────────────────────────────────────────────────────────────
  # Mailhog (Email Testing)
  # ─────────────────────────────────────────────────────────────────
  mailhog:
    image: mailhog/mailhog
    ports:
      - "1025:1025"  # SMTP
      - "8025:8025"  # Web UI

volumes:
  postgres_data:
  redis_data:
```

### Development Override

`docker-compose.override.yml`

```yaml
version: '3.8'

services:
  backend:
    build:
      target: runtime
    volumes:
      - ./src:/app/src
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      target: deps
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    command: pnpm dev
    environment:
      - WATCHPACK_POLLING=true
```

---

## Kubernetes Configuration

### Namespace Configuration

`k8s/base/namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: curious-now
  labels:
    app.kubernetes.io/name: curious-now
    app.kubernetes.io/managed-by: kubectl
```

### Backend Deployment

`k8s/base/backend-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: curious-backend
  namespace: curious-now
  labels:
    app: curious-backend
    app.kubernetes.io/name: curious-backend
    app.kubernetes.io/component: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: curious-backend
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: curious-backend
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: curious-backend
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: backend
          image: ghcr.io/curious-now/backend:latest
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
          env:
            - name: ENVIRONMENT
              value: "production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: redis-url
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: secret-key
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: openai-api-key
            - name: SENDGRID_API_KEY
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: sendgrid-api-key
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app
                      operator: In
                      values:
                        - curious-backend
                topologyKey: kubernetes.io/hostname
---
apiVersion: v1
kind: Service
metadata:
  name: curious-backend
  namespace: curious-now
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
      name: http
  selector:
    app: curious-backend
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: curious-backend-hpa
  namespace: curious-now
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: curious-backend
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

### Frontend Deployment

`k8s/base/frontend-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: curious-frontend
  namespace: curious-now
  labels:
    app: curious-frontend
    app.kubernetes.io/name: curious-frontend
    app.kubernetes.io/component: web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: curious-frontend
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: curious-frontend
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1001
        fsGroup: 1001
      containers:
        - name: frontend
          image: ghcr.io/curious-now/frontend:latest
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: 3000
              protocol: TCP
          env:
            - name: NODE_ENV
              value: "production"
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /api/health
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /api/health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 5
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
---
apiVersion: v1
kind: Service
metadata:
  name: curious-frontend
  namespace: curious-now
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 3000
      protocol: TCP
      name: http
  selector:
    app: curious-frontend
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: curious-frontend-hpa
  namespace: curious-now
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: curious-frontend
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### Worker Deployment

`k8s/base/worker-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: curious-worker
  namespace: curious-now
  labels:
    app: curious-worker
    app.kubernetes.io/name: curious-worker
    app.kubernetes.io/component: worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: curious-worker
  template:
    metadata:
      labels:
        app: curious-worker
    spec:
      serviceAccountName: curious-worker
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: worker
          image: ghcr.io/curious-now/worker:latest
          imagePullPolicy: Always
          env:
            - name: ENVIRONMENT
              value: "production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: redis-url
            - name: SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: secret-key
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: openai-api-key
            - name: SENDGRID_API_KEY
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: sendgrid-api-key
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: curious-scheduler
  namespace: curious-now
  labels:
    app: curious-scheduler
spec:
  replicas: 1
  selector:
    matchLabels:
      app: curious-scheduler
  template:
    metadata:
      labels:
        app: curious-scheduler
    spec:
      serviceAccountName: curious-worker
      containers:
        - name: scheduler
          image: ghcr.io/curious-now/worker:latest
          imagePullPolicy: Always
          command: ["celery", "-A", "src.worker.celery_app", "beat", "--loglevel=info"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: curious-secrets
                  key: redis-url
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
```

### Ingress Configuration

`k8s/base/ingress.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: curious-ingress
  namespace: curious-now
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    # Security headers
    nginx.ingress.kubernetes.io/configuration-snippet: |
      add_header X-Frame-Options "SAMEORIGIN" always;
      add_header X-Content-Type-Options "nosniff" always;
      add_header X-XSS-Protection "1; mode=block" always;
      add_header Referrer-Policy "strict-origin-when-cross-origin" always;
      add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
spec:
  tls:
    - hosts:
        - curious.now
        - www.curious.now
      secretName: curious-tls
  rules:
    - host: curious.now
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: curious-backend
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: curious-frontend
                port:
                  number: 80
    - host: www.curious.now
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: curious-frontend
                port:
                  number: 80
```

### Network Policies

`k8s/base/network-policies.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: curious-now
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend
  namespace: curious-now
spec:
  podSelector:
    matchLabels:
      app: curious-frontend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 3000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: curious-backend
      ports:
        - protocol: TCP
          port: 8000
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-backend
  namespace: curious-now
spec:
  podSelector:
    matchLabels:
      app: curious-backend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: curious-frontend
      ports:
        - protocol: TCP
          port: 8000
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
  egress:
    # PostgreSQL
    - to:
        - namespaceSelector:
            matchLabels:
              name: databases
      ports:
        - protocol: TCP
          port: 5432
    # Redis
    - to:
        - namespaceSelector:
            matchLabels:
              name: databases
      ports:
        - protocol: TCP
          port: 6379
    # External APIs (OpenAI, SendGrid, etc.)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - protocol: TCP
          port: 443
    # DNS
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
```

### Pod Disruption Budget

`k8s/base/pdb.yaml`

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: curious-backend-pdb
  namespace: curious-now
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: curious-backend
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: curious-frontend-pdb
  namespace: curious-now
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: curious-frontend
```

---

## Secrets Management

### External Secrets Operator Configuration

`k8s/base/external-secrets.yaml`

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
  namespace: curious-now
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: curious-external-secrets
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: curious-secrets
  namespace: curious-now
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: curious-secrets
    creationPolicy: Owner
  data:
    - secretKey: database-url
      remoteRef:
        key: curious-now/production
        property: DATABASE_URL
    - secretKey: redis-url
      remoteRef:
        key: curious-now/production
        property: REDIS_URL
    - secretKey: secret-key
      remoteRef:
        key: curious-now/production
        property: SECRET_KEY
    - secretKey: openai-api-key
      remoteRef:
        key: curious-now/production
        property: OPENAI_API_KEY
    - secretKey: sendgrid-api-key
      remoteRef:
        key: curious-now/production
        property: SENDGRID_API_KEY
    - secretKey: sentry-dsn
      remoteRef:
        key: curious-now/production
        property: SENTRY_DSN
```

### AWS Secrets Manager Structure

```json
// Secret: curious-now/production
{
  "DATABASE_URL": "postgresql://user:password@host:5432/curious",
  "REDIS_URL": "redis://:password@host:6379",
  "SECRET_KEY": "super-secret-key-for-jwt-signing",
  "OPENAI_API_KEY": "sk-...",
  "SENDGRID_API_KEY": "SG...",
  "SENTRY_DSN": "https://...@sentry.io/..."
}

// Secret: curious-now/staging
{
  "DATABASE_URL": "postgresql://user:password@staging-host:5432/curious_staging",
  "REDIS_URL": "redis://:password@staging-host:6379",
  "SECRET_KEY": "staging-secret-key",
  "OPENAI_API_KEY": "sk-...",
  "SENDGRID_API_KEY": "SG...",
  "SENTRY_DSN": "https://...@sentry.io/..."
}
```

### Secret Rotation

```yaml
# AWS Secrets Manager rotation configuration
apiVersion: secretsmanager.aws.amazon.com/v1alpha1
kind: SecretRotation
metadata:
  name: curious-secrets-rotation
spec:
  secretId: curious-now/production
  rotationLambdaARN: arn:aws:lambda:us-east-1:123456789:function:SecretsRotation
  rotationRules:
    automaticallyAfterDays: 30
```

---

## Environment-Specific Configurations

### Kustomize Structure

```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── backend-deployment.yaml
│   ├── frontend-deployment.yaml
│   ├── worker-deployment.yaml
│   ├── ingress.yaml
│   ├── network-policies.yaml
│   ├── pdb.yaml
│   └── external-secrets.yaml
├── staging/
│   ├── kustomization.yaml
│   ├── patches/
│   │   ├── backend-patch.yaml
│   │   └── frontend-patch.yaml
│   └── ingress-patch.yaml
└── production/
    ├── kustomization.yaml
    ├── patches/
    │   ├── backend-patch.yaml
    │   └── frontend-patch.yaml
    └── ingress-patch.yaml
```

### Base Kustomization

`k8s/base/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: curious-now

resources:
  - namespace.yaml
  - backend-deployment.yaml
  - frontend-deployment.yaml
  - worker-deployment.yaml
  - ingress.yaml
  - network-policies.yaml
  - pdb.yaml
  - external-secrets.yaml

commonLabels:
  app.kubernetes.io/part-of: curious-now

configMapGenerator:
  - name: curious-config
    literals:
      - LOG_LEVEL=INFO
      - CORS_ORIGINS=https://curious.now
```

### Production Kustomization

`k8s/production/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: production

resources:
  - ../base

namePrefix: prod-

patches:
  - path: patches/backend-patch.yaml
  - path: patches/frontend-patch.yaml
  - path: ingress-patch.yaml

images:
  - name: ghcr.io/curious-now/backend
    newTag: ${VERSION}
  - name: ghcr.io/curious-now/frontend
    newTag: ${VERSION}
  - name: ghcr.io/curious-now/worker
    newTag: ${VERSION}

replicas:
  - name: curious-backend
    count: 5
  - name: curious-frontend
    count: 5
  - name: curious-worker
    count: 3
```

`k8s/production/patches/backend-patch.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: curious-backend
spec:
  template:
    spec:
      containers:
        - name: backend
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
```

---

## Database Configuration

### PostgreSQL with CloudNativePG

`k8s/database/postgresql.yaml`

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: curious-postgres
  namespace: databases
spec:
  instances: 3

  postgresql:
    parameters:
      max_connections: "200"
      shared_buffers: "256MB"
      effective_cache_size: "768MB"
      maintenance_work_mem: "64MB"
      checkpoint_completion_target: "0.9"
      wal_buffers: "7864kB"
      default_statistics_target: "100"
      random_page_cost: "1.1"
      effective_io_concurrency: "200"
      work_mem: "1310kB"
      min_wal_size: "1GB"
      max_wal_size: "4GB"

  storage:
    size: 100Gi
    storageClass: gp3

  backup:
    barmanObjectStore:
      destinationPath: s3://curious-now-backups/postgres
      s3Credentials:
        accessKeyId:
          name: aws-credentials
          key: ACCESS_KEY_ID
        secretAccessKey:
          name: aws-credentials
          key: SECRET_ACCESS_KEY
      wal:
        compression: gzip
      data:
        compression: gzip
    retentionPolicy: "30d"

  monitoring:
    enablePodMonitor: true

  affinity:
    enablePodAntiAffinity: true
    topologyKey: kubernetes.io/hostname
```

### Redis Cluster

`k8s/database/redis.yaml`

```yaml
apiVersion: redis.redis.opstreelabs.in/v1beta2
kind: RedisCluster
metadata:
  name: curious-redis
  namespace: databases
spec:
  clusterSize: 3
  kubernetesConfig:
    image: redis:7-alpine
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        cpu: "500m"
        memory: "512Mi"
  storage:
    volumeClaimTemplate:
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 10Gi
        storageClassName: gp3
  redisConfig:
    additionalRedisConfig: |
      maxmemory 400mb
      maxmemory-policy allkeys-lru
```

---

## Monitoring Stack

`k8s/monitoring/prometheus-servicemonitor.yaml`

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: curious-backend
  namespace: curious-now
  labels:
    app: curious-backend
spec:
  selector:
    matchLabels:
      app: curious-backend
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: curious-frontend
  namespace: curious-now
spec:
  selector:
    matchLabels:
      app: curious-frontend
  endpoints:
    - port: http
      path: /api/metrics
      interval: 30s
```

---

## Resource Quotas

`k8s/base/resource-quota.yaml`

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: curious-quota
  namespace: curious-now
spec:
  hard:
    requests.cpu: "20"
    requests.memory: "40Gi"
    limits.cpu: "40"
    limits.memory: "80Gi"
    pods: "50"
    services: "20"
    secrets: "50"
    configmaps: "50"
    persistentvolumeclaims: "10"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: curious-limits
  namespace: curious-now
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "256Mi"
      max:
        cpu: "4"
        memory: "8Gi"
      min:
        cpu: "50m"
        memory: "64Mi"
```

---

## Deployment Commands

### Initial Setup

```bash
# Create namespaces
kubectl apply -f k8s/base/namespace.yaml
kubectl create namespace databases
kubectl create namespace monitoring

# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace

# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Install ingress-nginx
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace

# Deploy databases
kubectl apply -f k8s/database/

# Deploy application
kubectl apply -k k8s/production/
```

### Rollback

```bash
# Rollback deployment
kubectl rollout undo deployment/curious-backend -n production
kubectl rollout undo deployment/curious-frontend -n production

# Rollback to specific revision
kubectl rollout undo deployment/curious-backend -n production --to-revision=2
```

### Scaling

```bash
# Manual scaling
kubectl scale deployment curious-backend -n production --replicas=10

# Update HPA limits
kubectl patch hpa curious-backend-hpa -n production -p '{"spec":{"maxReplicas":20}}'
```
