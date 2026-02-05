# Security & Operations Specification

## Overview

This document specifies security measures, monitoring, alerting, rate limiting, and disaster recovery procedures for Curious Now.

---

## Security Architecture

### Defense in Depth

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Layer 1: Edge                                  │
│                    CloudFlare (DDoS, WAF, Bot Protection)               │
├─────────────────────────────────────────────────────────────────────────┤
│                        Layer 2: Network                                  │
│              VPC, Security Groups, Network Policies                      │
├─────────────────────────────────────────────────────────────────────────┤
│                       Layer 3: Application                               │
│         Rate Limiting, Input Validation, CORS, CSP                       │
├─────────────────────────────────────────────────────────────────────────┤
│                          Layer 4: Data                                   │
│          Encryption at Rest, Encryption in Transit, Access Control      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Security Headers

### HTTP Security Headers

Configure via nginx ingress or middleware:

```python
# src/middleware/security.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS Protection (legacy, but doesn't hurt)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (disable unused browser features)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # HSTS (only in production)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response
```

### Content Security Policy

```typescript
// next.config.js
const ContentSecurityPolicy = `
  default-src 'self';
  script-src 'self' 'unsafe-eval' 'unsafe-inline' https://www.googletagmanager.com;
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data: https: blob:;
  connect-src 'self' https://api.curious.now https://www.google-analytics.com;
  frame-ancestors 'none';
  form-action 'self';
  base-uri 'self';
  upgrade-insecure-requests;
`;

const securityHeaders = [
  {
    key: 'Content-Security-Policy',
    value: ContentSecurityPolicy.replace(/\s{2,}/g, ' ').trim(),
  },
  {
    key: 'X-Frame-Options',
    value: 'DENY',
  },
  {
    key: 'X-Content-Type-Options',
    value: 'nosniff',
  },
  {
    key: 'Referrer-Policy',
    value: 'strict-origin-when-cross-origin',
  },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=()',
  },
];

module.exports = {
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders,
      },
    ];
  },
};
```

---

## Rate Limiting

### API Rate Limits

| Endpoint Category | Authenticated | Anonymous | Window |
|------------------|---------------|-----------|--------|
| Auth (login/magic-link) | 10/hour | 5/hour | Per IP |
| Feed/Search | 100/minute | 30/minute | Per IP/User |
| Story Detail | 200/minute | 60/minute | Per IP/User |
| Save/Unsave | 60/minute | N/A | Per User |
| Settings | 30/minute | N/A | Per User |
| General API | 1000/hour | 200/hour | Per IP/User |

### Implementation

```python
# src/middleware/rate_limit.py
from fastapi import Request, HTTPException
from redis.asyncio import Redis
import time

class RateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> tuple[bool, dict]:
        """
        Returns (allowed, headers) tuple.
        Uses sliding window algorithm.
        """
        now = time.time()
        window_start = now - window_seconds

        pipe = self.redis.pipeline()

        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)

        # Add current request
        pipe.zadd(key, {str(now): now})

        # Count requests in window
        pipe.zcard(key)

        # Set expiry
        pipe.expire(key, window_seconds)

        results = await pipe.execute()
        current_count = results[2]

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current_count)),
            "X-RateLimit-Reset": str(int(now + window_seconds)),
        }

        if current_count > limit:
            headers["Retry-After"] = str(window_seconds)
            return False, headers

        return True, headers


# Rate limit decorator
def rate_limit(limit: int, window_seconds: int, key_func=None):
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            limiter = request.app.state.rate_limiter

            # Build key
            if key_func:
                key = key_func(request)
            elif request.state.user:
                key = f"ratelimit:user:{request.state.user.id}:{request.url.path}"
            else:
                key = f"ratelimit:ip:{request.client.host}:{request.url.path}"

            allowed, headers = await limiter.check_rate_limit(
                key, limit, window_seconds
            )

            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please slow down.",
                    headers=headers
                )

            response = await func(request, *args, **kwargs)

            # Add rate limit headers to response
            for header, value in headers.items():
                response.headers[header] = value

            return response
        return wrapper
    return decorator


# Usage
@router.post("/auth/magic-link")
@rate_limit(limit=5, window_seconds=3600)  # 5 per hour
async def request_magic_link(request: Request, email: str):
    ...

@router.get("/feed")
@rate_limit(limit=100, window_seconds=60)  # 100 per minute
async def get_feed(request: Request):
    ...
```

### Rate Limit Response

```json
{
  "detail": "Too many requests. Please slow down.",
  "retry_after": 60
}
```

With headers:
```
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1706745600
Retry-After: 60
```

---

## Authentication Security

### Magic Link Security

```python
# src/services/auth.py
import secrets
from datetime import datetime, timedelta
from hashlib import sha256

class AuthService:
    TOKEN_EXPIRY_MINUTES = 15
    TOKEN_BYTES = 32

    def generate_magic_link_token(self, email: str) -> tuple[str, str]:
        """
        Generate a secure magic link token.
        Returns (token_for_url, token_hash_for_db).
        """
        # Generate cryptographically secure token
        token = secrets.token_urlsafe(self.TOKEN_BYTES)

        # Store hash in DB, not the actual token
        token_hash = sha256(token.encode()).hexdigest()

        return token, token_hash

    async def create_magic_link(self, email: str) -> str:
        """Create and store a magic link."""
        token, token_hash = self.generate_magic_link_token(email)

        # Store in database
        await self.db.magic_links.create(
            email=email,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(minutes=self.TOKEN_EXPIRY_MINUTES),
            used=False,
        )

        # Build URL
        return f"https://curious.now/auth/verify?token={token}"

    async def verify_magic_link(self, token: str) -> str | None:
        """
        Verify a magic link token.
        Returns email if valid, None if invalid.
        """
        token_hash = sha256(token.encode()).hexdigest()

        # Find and validate token
        magic_link = await self.db.magic_links.find_one(
            token_hash=token_hash,
            used=False,
            expires_at__gt=datetime.utcnow(),
        )

        if not magic_link:
            return None

        # Mark as used (one-time use)
        await self.db.magic_links.update(
            id=magic_link.id,
            used=True,
            used_at=datetime.utcnow(),
        )

        return magic_link.email
```

### Session Management

```python
# src/services/session.py
import secrets
from datetime import datetime, timedelta

class SessionService:
    SESSION_DURATION_DAYS = 30
    SESSION_ID_BYTES = 32

    async def create_session(self, user_id: str, request: Request) -> str:
        """Create a new session."""
        session_id = secrets.token_urlsafe(self.SESSION_ID_BYTES)

        await self.db.sessions.create(
            id=session_id,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(days=self.SESSION_DURATION_DAYS),
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent", ""),
            created_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
        )

        return session_id

    async def validate_session(self, session_id: str) -> str | None:
        """Validate session and return user_id if valid."""
        session = await self.db.sessions.find_one(
            id=session_id,
            expires_at__gt=datetime.utcnow(),
        )

        if not session:
            return None

        # Update last active
        await self.db.sessions.update(
            id=session_id,
            last_active_at=datetime.utcnow(),
        )

        return session.user_id

    async def revoke_session(self, session_id: str):
        """Revoke a session."""
        await self.db.sessions.delete(id=session_id)

    async def revoke_all_sessions(self, user_id: str, except_session: str = None):
        """Revoke all sessions for a user."""
        query = {"user_id": user_id}
        if except_session:
            query["id__ne"] = except_session
        await self.db.sessions.delete_many(query)
```

### Cookie Configuration

```python
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Cookie settings
    SESSION_COOKIE_NAME: str = "curious_session"
    SESSION_COOKIE_SECURE: bool = True  # HTTPS only
    SESSION_COOKIE_HTTPONLY: bool = True  # No JS access
    SESSION_COOKIE_SAMESITE: str = "lax"  # CSRF protection
    SESSION_COOKIE_MAX_AGE: int = 60 * 60 * 24 * 30  # 30 days
    SESSION_COOKIE_DOMAIN: str = ".curious.now"


# Setting the cookie
response.set_cookie(
    key=settings.SESSION_COOKIE_NAME,
    value=session_id,
    max_age=settings.SESSION_COOKIE_MAX_AGE,
    secure=settings.SESSION_COOKIE_SECURE,
    httponly=settings.SESSION_COOKIE_HTTPONLY,
    samesite=settings.SESSION_COOKIE_SAMESITE,
    domain=settings.SESSION_COOKIE_DOMAIN,
)
```

---

## Input Validation

### Request Validation

```python
# src/schemas/validation.py
from pydantic import BaseModel, EmailStr, Field, validator
import bleach

class CreateUserRequest(BaseModel):
    email: EmailStr

    @validator('email')
    def normalize_email(cls, v):
        return v.lower().strip()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    topic: str | None = Field(None, max_length=50)
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)

    @validator('query')
    def sanitize_query(cls, v):
        # Remove potential injection characters
        return bleach.clean(v, strip=True)


class SaveClusterRequest(BaseModel):
    cluster_id: str = Field(..., regex=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
```

### SQL Injection Prevention

Always use parameterized queries:

```python
# Bad - vulnerable to SQL injection
query = f"SELECT * FROM users WHERE email = '{email}'"

# Good - parameterized
query = "SELECT * FROM users WHERE email = $1"
result = await db.fetch_one(query, email)

# Good - using ORM
user = await User.filter(email=email).first()
```

### XSS Prevention

```python
# Backend: sanitize any user-generated content
import bleach

ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'a', 'ul', 'ol', 'li']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}

def sanitize_html(content: str) -> str:
    return bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True
    )
```

```tsx
// Frontend: use React's built-in escaping
// This is safe - React escapes by default
<p>{userContent}</p>

// Dangerous - only use with sanitized content
<div dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />
```

---

## Monitoring & Observability

### Metrics (Prometheus)

```python
# src/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Business metrics
ACTIVE_USERS = Gauge(
    'active_users_total',
    'Number of active users in last 24h'
)

CLUSTERS_CREATED = Counter(
    'clusters_created_total',
    'Total clusters created',
    ['topic']
)

STORIES_SAVED = Counter(
    'stories_saved_total',
    'Total stories saved by users'
)

# System metrics
DB_POOL_SIZE = Gauge(
    'db_connection_pool_size',
    'Database connection pool size'
)

CACHE_HIT_RATE = Gauge(
    'cache_hit_rate',
    'Redis cache hit rate'
)

# Application info
APP_INFO = Info('app', 'Application information')
APP_INFO.info({
    'version': '1.0.0',
    'environment': 'production'
})
```

### Middleware for Metrics

```python
# src/middleware/metrics.py
import time
from fastapi import Request
from .metrics import REQUEST_COUNT, REQUEST_LATENCY

class MetricsMiddleware:
    async def __call__(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        # Record metrics
        duration = time.time() - start_time
        endpoint = self._get_endpoint_label(request)

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)

        return response

    def _get_endpoint_label(self, request: Request) -> str:
        # Normalize path to avoid high cardinality
        path = request.url.path
        # Replace UUIDs and IDs with placeholder
        import re
        path = re.sub(r'/[a-f0-9-]{36}', '/{id}', path)
        path = re.sub(r'/\d+', '/{id}', path)
        return path
```

### Logging Configuration

```python
# src/logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
    "loggers": {
        "uvicorn": {"level": "WARNING"},
        "sqlalchemy": {"level": "WARNING"},
    },
}
```

### Request Tracing

```python
# src/middleware/tracing.py
import uuid
from fastapi import Request

class TracingMiddleware:
    async def __call__(self, request: Request, call_next):
        # Get or create request ID
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

        # Add to request state
        request.state.request_id = request_id

        # Add to logging context
        import logging
        logger = logging.getLogger()
        old_factory = logger.makeRecord

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logger.makeRecord = record_factory

        try:
            response = await call_next(request)
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            logger.makeRecord = old_factory
```

---

## Alerting Rules

### Prometheus Alert Rules

```yaml
# prometheus/alerts.yml
groups:
  - name: curious-now-alerts
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m]))
          > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} over the last 5 minutes"

      # High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
          > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "P95 latency is {{ $value }}s"

      # Database connection issues
      - alert: DatabaseConnectionPoolExhausted
        expr: db_connection_pool_available == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database connection pool exhausted"

      # Redis connection issues
      - alert: RedisCacheDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis cache is down"

      # Low cache hit rate
      - alert: LowCacheHitRate
        expr: cache_hit_rate < 0.5
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Cache hit rate is low ({{ $value | humanizePercentage }})"

      # Pod restarts
      - alert: PodRestarting
        expr: |
          increase(kube_pod_container_status_restarts_total{namespace="curious-now"}[1h]) > 3
        labels:
          severity: warning
        annotations:
          summary: "Pod {{ $labels.pod }} is restarting frequently"

      # Disk space
      - alert: DiskSpaceLow
        expr: |
          (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Disk space is below 10%"

      # Memory usage
      - alert: HighMemoryUsage
        expr: |
          container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Container memory usage is above 90%"

      # SSL certificate expiry
      - alert: SSLCertificateExpiringSoon
        expr: |
          (probe_ssl_earliest_cert_expiry - time()) / 86400 < 14
        labels:
          severity: warning
        annotations:
          summary: "SSL certificate expires in {{ $value | humanizeDuration }}"
```

### PagerDuty Integration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m
  pagerduty_url: 'https://events.pagerduty.com/v2/enqueue'

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
    - match:
        severity: warning
      receiver: 'slack-warnings'

receivers:
  - name: 'default'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts'

  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '${PAGERDUTY_SERVICE_KEY}'
        severity: critical

  - name: 'slack-warnings'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts-warnings'
```

---

## Health Checks

### Health Endpoints

```python
# src/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/live")
async def liveness():
    """
    Liveness probe - is the process alive?
    Used by Kubernetes to restart unhealthy pods.
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    Readiness probe - is the service ready to accept traffic?
    Checks all dependencies.
    """
    checks = {}

    # Check database
    try:
        await db.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    # Check Redis
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"

    # Overall status
    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "checks": checks}
        )

    return {"status": "healthy", "checks": checks}


@router.get("")
async def health(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    Comprehensive health check with metrics.
    """
    from datetime import datetime
    import psutil

    checks = await readiness(db, redis)

    return {
        **checks,
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": time.time() - START_TIME,
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
        }
    }
```

---

## Disaster Recovery

### Backup Strategy

| Data | Frequency | Retention | Location |
|------|-----------|-----------|----------|
| PostgreSQL | Continuous (WAL) | 30 days | S3 + Cross-region |
| PostgreSQL | Daily full | 90 days | S3 + Cross-region |
| Redis | Hourly RDB | 7 days | S3 |
| User uploads | Real-time | Indefinite | S3 + Cross-region |
| Secrets | On change | 30 versions | AWS Secrets Manager |

### Recovery Time Objectives

| Scenario | RTO | RPO |
|----------|-----|-----|
| Single pod failure | 30 seconds | 0 |
| Single node failure | 2 minutes | 0 |
| AZ failure | 5 minutes | 0 |
| Region failure | 1 hour | 5 minutes |
| Database corruption | 30 minutes | 1 hour |
| Accidental deletion | 1 hour | Point-in-time |

### Recovery Procedures

#### Database Recovery

```bash
# Point-in-time recovery
# 1. Stop the application
kubectl scale deployment curious-backend --replicas=0

# 2. Restore from backup
pg_restore -h $DB_HOST -U $DB_USER -d curious_restored \
  /backups/curious_20240115_0300.dump

# 3. Or use WAL for point-in-time
# Configure recovery.conf with recovery_target_time

# 4. Verify data integrity
psql -h $DB_HOST -U $DB_USER -d curious_restored \
  -c "SELECT COUNT(*) FROM clusters;"

# 5. Swap databases
psql -h $DB_HOST -U $DB_USER -c "
  ALTER DATABASE curious RENAME TO curious_old;
  ALTER DATABASE curious_restored RENAME TO curious;
"

# 6. Restart application
kubectl scale deployment curious-backend --replicas=3
```

#### Region Failover

```bash
# 1. Update DNS to point to DR region
aws route53 change-resource-record-sets \
  --hosted-zone-id $ZONE_ID \
  --change-batch file://failover-dns.json

# 2. Promote read replica to primary
aws rds promote-read-replica \
  --db-instance-identifier curious-db-dr

# 3. Deploy application to DR region
kubectl --context dr-cluster apply -k k8s/production/

# 4. Verify
curl https://curious.now/health
```

### Runbook: Common Incidents

#### Incident: High Error Rate

```markdown
## High Error Rate (>5% 5xx errors)

### Detection
- PagerDuty alert: HighErrorRate
- Grafana dashboard shows spike

### Diagnosis
1. Check recent deployments: `kubectl rollout history deployment/curious-backend`
2. Check logs: `kubectl logs -l app=curious-backend --since=10m | grep ERROR`
3. Check database: `kubectl exec -it postgres-0 -- pg_isready`
4. Check Redis: `kubectl exec -it redis-0 -- redis-cli ping`

### Mitigation
1. If recent deployment: `kubectl rollout undo deployment/curious-backend`
2. If database issue: Scale down, restore from backup
3. If external API: Enable circuit breaker, serve cached data

### Resolution
1. Root cause analysis
2. Fix and test in staging
3. Deploy fix
4. Update runbook if needed
```

#### Incident: Database Connection Exhausted

```markdown
## Database Connection Pool Exhausted

### Detection
- Alert: DatabaseConnectionPoolExhausted
- Application returning 503 errors

### Diagnosis
1. Check active connections: `SELECT count(*) FROM pg_stat_activity;`
2. Check for long-running queries: `SELECT * FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start;`
3. Check for connection leaks in application logs

### Mitigation
1. Kill idle connections: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';`
2. Increase pool size temporarily
3. Scale up backend pods to distribute load

### Resolution
1. Identify and fix connection leak
2. Optimize long-running queries
3. Implement connection timeouts
```

---

## Security Incident Response

### Incident Classification

| Severity | Description | Response Time | Examples |
|----------|-------------|---------------|----------|
| P1 - Critical | Active breach, data exfiltration | 15 minutes | Unauthorized access, ransomware |
| P2 - High | Vulnerability being exploited | 1 hour | SQL injection attempt, DDoS |
| P3 - Medium | Potential security issue | 4 hours | Suspicious login patterns |
| P4 - Low | Minor security concern | 24 hours | Failed login attempts |

### Response Procedure

```markdown
## Security Incident Response

### 1. Identify & Contain (First 15 minutes)
- [ ] Confirm incident is real
- [ ] Identify affected systems
- [ ] Isolate compromised systems
- [ ] Preserve evidence (logs, memory dumps)

### 2. Assess & Communicate (First hour)
- [ ] Determine scope of breach
- [ ] Identify compromised data
- [ ] Notify incident response team
- [ ] Begin incident documentation

### 3. Eradicate & Recover
- [ ] Remove threat actor access
- [ ] Patch vulnerabilities
- [ ] Restore from clean backups
- [ ] Reset compromised credentials

### 4. Post-Incident
- [ ] Complete incident report
- [ ] Update security controls
- [ ] Conduct lessons learned
- [ ] Notify affected users (if required)
```

### Contact List

| Role | Contact | Escalation |
|------|---------|------------|
| On-call Engineer | PagerDuty | Auto-escalate after 15 min |
| Security Lead | security@curious.now | P1/P2 incidents |
| Engineering Lead | eng@curious.now | P1 incidents |
| Legal/Compliance | legal@curious.now | Data breach |

---

## Compliance Checklist

### GDPR Requirements

- [ ] Data minimization - only collect necessary data
- [ ] Right to access - users can export their data
- [ ] Right to erasure - users can delete their account
- [ ] Data portability - data export in standard format
- [ ] Breach notification - notify within 72 hours
- [ ] Privacy policy - clearly explains data use
- [ ] Cookie consent - explicit opt-in for non-essential

### SOC 2 Controls

- [ ] Access control - role-based permissions
- [ ] Encryption - data encrypted at rest and in transit
- [ ] Logging - comprehensive audit logs
- [ ] Change management - documented deployment process
- [ ] Incident response - documented procedures
- [ ] Vendor management - third-party risk assessment
- [ ] Business continuity - disaster recovery tested
