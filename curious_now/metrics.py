"""Prometheus metrics module.

This module provides Prometheus-compatible metrics for monitoring
the Curious Now application.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable

# Global metrics storage
_START_TIME = time.time()
_LOCK = Lock()


@dataclass
class MetricValue:
    """A single metric value with labels."""

    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Metric:
    """A metric with name, type, help text, and values."""

    name: str
    metric_type: str  # counter, gauge, histogram
    help_text: str
    values: list[MetricValue] = field(default_factory=list)


# Global metrics registry
_METRICS: dict[str, Metric] = {}

# Request counters
_REQUEST_COUNT: Counter[tuple[str, str, int]] = Counter()
_REQUEST_LATENCY: dict[tuple[str, str], list[float]] = {}

# Business metrics
_CLUSTERS_CREATED = 0
_STORIES_SAVED = 0
_SEARCHES_PERFORMED = 0
_ACTIVE_USERS_24H = 0


def _labels_to_str(labels: dict[str, str]) -> str:
    """Convert labels dict to Prometheus label string."""
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


def register_metric(
    name: str,
    metric_type: str,
    help_text: str,
) -> None:
    """Register a new metric."""
    with _LOCK:
        if name not in _METRICS:
            _METRICS[name] = Metric(
                name=name,
                metric_type=metric_type,
                help_text=help_text,
            )


def set_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """Set a gauge metric value."""
    with _LOCK:
        if name not in _METRICS:
            _METRICS[name] = Metric(name=name, metric_type="gauge", help_text="")

        metric = _METRICS[name]
        labels = labels or {}

        # Update or add value
        for mv in metric.values:
            if mv.labels == labels:
                mv.value = value
                return
        metric.values.append(MetricValue(value=value, labels=labels))


def inc_counter(name: str, value: float = 1, labels: dict[str, str] | None = None) -> None:
    """Increment a counter metric."""
    with _LOCK:
        if name not in _METRICS:
            _METRICS[name] = Metric(name=name, metric_type="counter", help_text="")

        metric = _METRICS[name]
        labels = labels or {}

        # Update or add value
        for mv in metric.values:
            if mv.labels == labels:
                mv.value += value
                return
        metric.values.append(MetricValue(value=value, labels=labels))


def record_request(method: str, endpoint: str, status_code: int, latency_seconds: float) -> None:
    """Record an HTTP request for metrics."""
    with _LOCK:
        key = (method, endpoint, status_code)
        _REQUEST_COUNT[key] += 1

        latency_key = (method, endpoint)
        if latency_key not in _REQUEST_LATENCY:
            _REQUEST_LATENCY[latency_key] = []
        _REQUEST_LATENCY[latency_key].append(latency_seconds)

        # Keep only last 1000 samples per endpoint
        if len(_REQUEST_LATENCY[latency_key]) > 1000:
            _REQUEST_LATENCY[latency_key] = _REQUEST_LATENCY[latency_key][-1000:]


def record_cluster_created(topic: str | None = None) -> None:
    """Record a cluster creation."""
    global _CLUSTERS_CREATED
    with _LOCK:
        _CLUSTERS_CREATED += 1
    inc_counter("curious_clusters_created_total", labels={"topic": topic or "unknown"})


def record_story_saved() -> None:
    """Record a story save action."""
    global _STORIES_SAVED
    with _LOCK:
        _STORIES_SAVED += 1
    inc_counter("curious_stories_saved_total")


def record_search() -> None:
    """Record a search performed."""
    global _SEARCHES_PERFORMED
    with _LOCK:
        _SEARCHES_PERFORMED += 1
    inc_counter("curious_searches_total")


def set_active_users(count: int) -> None:
    """Set the active users gauge."""
    global _ACTIVE_USERS_24H
    with _LOCK:
        _ACTIVE_USERS_24H = count
    set_gauge("curious_active_users_24h", count)


def generate_metrics() -> str:
    """Generate Prometheus-format metrics output."""
    lines: list[str] = []

    # App info
    lines.append("# HELP curious_app_info Application information")
    lines.append("# TYPE curious_app_info gauge")
    lines.append('curious_app_info{version="0.1.0",environment="production"} 1')
    lines.append("")

    # Uptime
    uptime = time.time() - _START_TIME
    lines.append("# HELP curious_uptime_seconds Application uptime in seconds")
    lines.append("# TYPE curious_uptime_seconds gauge")
    lines.append(f"curious_uptime_seconds {uptime:.2f}")
    lines.append("")

    # Request metrics
    lines.append("# HELP curious_http_requests_total Total HTTP requests")
    lines.append("# TYPE curious_http_requests_total counter")
    with _LOCK:
        for (method, endpoint, status), count in _REQUEST_COUNT.items():
            labels = f'method="{method}",endpoint="{endpoint}",status="{status}"'
            lines.append(f"curious_http_requests_total{{{labels}}} {count}")
    lines.append("")

    # Request latency histogram buckets
    lines.append("# HELP curious_http_request_duration_seconds HTTP request latency")
    lines.append("# TYPE curious_http_request_duration_seconds histogram")
    buckets = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    with _LOCK:
        for (method, endpoint), latencies in _REQUEST_LATENCY.items():
            if not latencies:
                continue
            labels_base = f'method="{method}",endpoint="{endpoint}"'

            # Calculate bucket counts
            for bucket in buckets:
                count = sum(1 for lat in latencies if lat <= bucket)
                metric_name = "curious_http_request_duration_seconds_bucket"
                lines.append(f'{metric_name}{{{labels_base},le="{bucket}"}} {count}')
            metric_name = "curious_http_request_duration_seconds_bucket"
            lines.append(f'{metric_name}{{{labels_base},le="+Inf"}} {len(latencies)}')
            lines.append(
                f"curious_http_request_duration_seconds_sum{{{labels_base}}} {sum(latencies):.4f}"
            )
            lines.append(
                f"curious_http_request_duration_seconds_count{{{labels_base}}} {len(latencies)}"
            )
    lines.append("")

    # Business metrics
    lines.append("# HELP curious_clusters_created_total Total clusters created")
    lines.append("# TYPE curious_clusters_created_total counter")
    with _LOCK:
        lines.append(f"curious_clusters_created_total {_CLUSTERS_CREATED}")
    lines.append("")

    lines.append("# HELP curious_stories_saved_total Total stories saved by users")
    lines.append("# TYPE curious_stories_saved_total counter")
    with _LOCK:
        lines.append(f"curious_stories_saved_total {_STORIES_SAVED}")
    lines.append("")

    lines.append("# HELP curious_searches_total Total searches performed")
    lines.append("# TYPE curious_searches_total counter")
    with _LOCK:
        lines.append(f"curious_searches_total {_SEARCHES_PERFORMED}")
    lines.append("")

    lines.append("# HELP curious_active_users_24h Active users in last 24 hours")
    lines.append("# TYPE curious_active_users_24h gauge")
    with _LOCK:
        lines.append(f"curious_active_users_24h {_ACTIVE_USERS_24H}")
    lines.append("")

    # Custom registered metrics
    with _LOCK:
        for metric in _METRICS.values():
            if metric.values:
                lines.append(f"# HELP {metric.name} {metric.help_text}")
                lines.append(f"# TYPE {metric.name} {metric.metric_type}")
                for mv in metric.values:
                    labels_str = _labels_to_str(mv.labels)
                    lines.append(f"{metric.name}{labels_str} {mv.value}")
                lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware helper
# ─────────────────────────────────────────────────────────────────────────────


class MetricsMiddleware:
    """ASGI middleware to record request metrics."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[dict[str, Any]], Any],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        status_code = 500  # Default if something goes wrong

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency = time.time() - start_time
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")

            # Normalize path to avoid high cardinality
            # Replace UUIDs and numeric IDs with placeholders
            import re

            normalized_path = re.sub(
                r"/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
                "/{id}",
                path,
            )
            normalized_path = re.sub(r"/\d+", "/{id}", normalized_path)

            record_request(method, normalized_path, status_code, latency)
