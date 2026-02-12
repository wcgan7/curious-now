"""High-impact scoring heuristics and calibration helpers."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

_PROVISIONAL_VERSION = "v1.0-provisional"
_FINAL_VERSION = "v1.0-final"
_HIGH_IMPACT_CONFIDENCE_MIN = 0.75
_EVIDENCE_GATE_MIN = 0.35
_CALIBRATION_LOOKBACK_DAYS = 180
_MIN_BUCKET_SAMPLE = 100
_ESCAPE_HATCH_EPSILON = 0.015
_ABSOLUTE_HIGH_BAR = 0.97
_MIN_QUALIFIED_SET_SIZE = 2
_RATE_GUARDRAIL_LOW = 0.007
_RATE_GUARDRAIL_HIGH = 0.013

_NOVELTY_CUES = {
    "first",
    "novel",
    "new",
    "unprecedented",
    "state-of-the-art",
    "sota",
}
_TRANSLATION_CUES = {
    "patient",
    "clinical",
    "industry",
    "policy",
    "deployment",
    "scale",
    "cost",
    "real-world",
    "outcome",
    "adoption",
}
_TRANSLATION_STRONG_CUES = {
    "clinical trial",
    "fda",
    "approved",
    "deployed",
    "deployed at scale",
    "policy change",
    "production",
    "real-world",
}
_HEDGE_CUES = {"might", "could", "may", "potentially", "possibly", "preliminary"}
_EVIDENCE_RISK_FLAGS = {"press_release_only", "preprint_not_peer_reviewed"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class HighImpactInput:
    """Inputs needed for high-impact scoring."""

    takeaway: str
    canonical_title: str
    content_types: list[str]
    anti_hype_flags: list[str]
    distinct_source_count: int
    has_full_text_paper: bool


@dataclass(frozen=True)
class HighImpactComponents:
    """Component-level scores."""

    novelty_score: float
    translation_score: float
    evidence_score: float


@dataclass(frozen=True)
class HighImpactScore:
    """Computed score payload."""

    provisional_score: float
    final_score: float | None
    confidence: float
    reasons: list[str]
    eligible_for_final: bool
    version: str


@dataclass(frozen=True)
class ThresholdResolution:
    """Resolved threshold value for top-1% labeling."""

    bucket: str
    threshold: float


@dataclass(frozen=True)
class HighImpactRateWindow:
    """Observed label rate over a trailing window."""

    days: int
    eligible_count: int
    labeled_count: int
    rate: float
    in_guardrail_band: bool


@dataclass(frozen=True)
class HighImpactDebugRow:
    """Debug row for calibration report."""

    cluster_id: str
    title: str
    final_score: float | None
    threshold: float | None
    threshold_delta: float | None
    confidence: float | None
    label: bool
    novelty_score: float | None
    translation_score: float | None
    evidence_score: float | None
    passed_threshold: bool
    passed_confidence: bool
    passed_evidence_gate: bool
    llm_shadow: dict[str, Any] | None = None


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _count_matches(text: str, cues: set[str]) -> int:
    return sum(1 for cue in cues if cue in text)


def _safe_unique_ratio(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def _score_novelty(title: str, takeaway: str) -> float:
    text = f"{title} {takeaway}".lower()
    tokens = _tokenize(text)
    novelty_hits = _count_matches(text, _NOVELTY_CUES)
    unique_ratio = _safe_unique_ratio(tokens)
    score = 0.44
    score += min(0.24, 0.06 * novelty_hits)
    score += max(-0.04, min(0.10, (unique_ratio - 0.52) * 0.25))
    if "first" in title.lower() or "novel" in title.lower():
        score += 0.05
    if "review" in text or "survey" in text:
        score -= 0.12
    if "incremental" in text or "extension" in text:
        score -= 0.08
    if "replication" in text:
        score -= 0.05
    return _clamp(score)


def _score_translation(takeaway: str) -> float:
    text = takeaway.lower()
    tokens = _tokenize(text)
    weak_hits = _count_matches(text, _TRANSLATION_CUES)
    strong_hits = _count_matches(text, _TRANSLATION_STRONG_CUES)
    hedge_hits = _count_matches(text, _HEDGE_CUES)
    score = 0.34
    score += min(0.24, weak_hits * 0.04)
    score += min(0.26, strong_hits * 0.10)
    has_quant = any(tok.isdigit() for tok in tokens)
    if has_quant:
        score += 0.05
    if "patient" in text or "clinical" in text or "policy" in text:
        score += 0.06
    score -= min(0.10, hedge_hits * 0.03)
    return _clamp(score)


def _score_evidence(
    content_types: list[str],
    anti_hype_flags: list[str],
    distinct_source_count: int,
    has_full_text_paper: bool,
) -> float:
    lowered_types = {str(ct).lower() for ct in content_types}
    lowered_flags = {str(f).lower() for f in anti_hype_flags}
    score = 0.30
    if "peer_reviewed" in lowered_types:
        score += 0.30
    elif "preprint" in lowered_types:
        score += 0.18
    elif "report" in lowered_types:
        score += 0.12
    if has_full_text_paper:
        score += 0.14
    # NOTE: single_source is intentionally not penalized here.
    source_bonus = min(0.16, math.log1p(max(0, distinct_source_count)) * 0.08)
    score += source_bonus
    if _EVIDENCE_RISK_FLAGS & lowered_flags:
        score -= 0.05
    if "press_release_only" in lowered_flags:
        score -= 0.22
    return _clamp(score)


def compute_components(input_data: HighImpactInput) -> HighImpactComponents:
    """Compute component scores used by provisional/final models."""
    novelty = _score_novelty(input_data.canonical_title, input_data.takeaway)
    translation = _score_translation(input_data.takeaway)
    evidence = _score_evidence(
        input_data.content_types,
        input_data.anti_hype_flags,
        input_data.distinct_source_count,
        input_data.has_full_text_paper,
    )
    return HighImpactComponents(
        novelty_score=novelty,
        translation_score=translation,
        evidence_score=evidence,
    )


def compute_high_impact_score(input_data: HighImpactInput) -> HighImpactScore:
    """Compute provisional score and final score when eligible."""
    components = compute_components(input_data)
    impact = _clamp(
        0.45 * components.novelty_score
        + 0.40 * components.translation_score
        + 0.15 * components.evidence_score
    )

    provisional_score = _clamp(impact * 0.96)
    eligible_for_final = input_data.has_full_text_paper
    confidence = 0.62 + min(0.12, input_data.distinct_source_count * 0.03)
    if eligible_for_final:
        confidence += 0.12
    confidence = _clamp(confidence)

    reasons: list[str] = []
    if components.novelty_score >= 0.70:
        reasons.append("high_novelty_vs_topic")
    if components.translation_score >= 0.70:
        reasons.append("high_translation_scope")
    if "peer_reviewed" in {str(t).lower() for t in input_data.content_types}:
        reasons.append("peer_reviewed_support")
    if input_data.distinct_source_count >= 3:
        reasons.append("multi_source_independent_support")
    if components.evidence_score >= _EVIDENCE_GATE_MIN:
        reasons.append("evidence_gate_passed")

    return HighImpactScore(
        provisional_score=provisional_score,
        final_score=impact if eligible_for_final else None,
        confidence=confidence,
        reasons=reasons,
        eligible_for_final=eligible_for_final,
        version=_FINAL_VERSION if eligible_for_final else _PROVISIONAL_VERSION,
    )


def high_impact_passes_gates(
    *,
    final_score: float | None,
    confidence: float,
    evidence_score: float,
    threshold: float,
    qualified_set_count: int = 0,
) -> bool:
    """Return true when the score passes threshold and safety gates."""
    if final_score is None:
        return False
    if confidence < _HIGH_IMPACT_CONFIDENCE_MIN or evidence_score < _EVIDENCE_GATE_MIN:
        return False
    standard = final_score >= threshold
    escape_hatch = final_score >= _ABSOLUTE_HIGH_BAR and final_score >= (
        threshold - _ESCAPE_HATCH_EPSILON
    )
    qualified_set_override = (
        qualified_set_count >= _MIN_QUALIFIED_SET_SIZE
        and final_score >= _ABSOLUTE_HIGH_BAR
    )
    return standard or escape_hatch or qualified_set_override


def is_absolute_high_qualifier(
    *,
    final_score: float | None,
    confidence: float,
    evidence_score: float,
) -> bool:
    """Return true for very high-quality papers eligible for qualified-set override."""
    if final_score is None:
        return False
    return (
        final_score >= _ABSOLUTE_HIGH_BAR
        and confidence >= _HIGH_IMPACT_CONFIDENCE_MIN
        and evidence_score >= _EVIDENCE_GATE_MIN
    )


def resolve_threshold_for_cluster(
    conn: psycopg.Connection[Any],
    *,
    cluster_id: Any,
) -> ThresholdResolution:
    """Resolve p99 threshold for the cluster with topic/age fallback."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
              c.created_at,
              (
                SELECT ct.topic_id
                FROM cluster_topics ct
                WHERE ct.cluster_id = c.id
                ORDER BY ct.score DESC
                LIMIT 1
              ) AS primary_topic_id
            FROM story_clusters c
            WHERE c.id = %s;
            """,
            (cluster_id,),
        )
        row = cur.fetchone()
    if not row:
        return ThresholdResolution(bucket="global", threshold=0.95)

    age_sql = (
        "CASE "
        "WHEN now() - c.created_at <= interval '30 days' THEN '0_30d' "
        "WHEN now() - c.created_at <= interval '90 days' THEN '31_90d' "
        "ELSE '91_365d' "
        "END"
    )
    with conn.cursor(row_factory=dict_row) as cur:
        # topic + age bucket
        cur.execute(
            f"""
            SELECT
              percentile_cont(0.99) WITHIN GROUP (ORDER BY c.high_impact_final_score) AS p99,
              COUNT(*) AS n
            FROM story_clusters c
            JOIN cluster_topics ct ON ct.cluster_id = c.id
            WHERE c.status = 'active'
              AND c.high_impact_eligible = TRUE
              AND c.high_impact_final_score IS NOT NULL
              AND c.high_impact_assessed_at >= now() - interval '{_CALIBRATION_LOOKBACK_DAYS} days'
              AND ct.topic_id = %s
              AND {age_sql} = (
                SELECT {age_sql}
                FROM story_clusters c2
                WHERE c2.id = %s
              );
            """,
            (row["primary_topic_id"], cluster_id),
        )
        topic_age = cur.fetchone() or {}
        if int(topic_age.get("n") or 0) >= _MIN_BUCKET_SAMPLE and topic_age.get("p99") is not None:
            return ThresholdResolution(bucket="topic_age", threshold=float(topic_age["p99"]))

        # age bucket global
        cur.execute(
            f"""
            SELECT
              percentile_cont(0.99) WITHIN GROUP (ORDER BY c.high_impact_final_score) AS p99,
              COUNT(*) AS n
            FROM story_clusters c
            WHERE c.status = 'active'
              AND c.high_impact_eligible = TRUE
              AND c.high_impact_final_score IS NOT NULL
              AND c.high_impact_assessed_at >= now() - interval '{_CALIBRATION_LOOKBACK_DAYS} days'
              AND {age_sql} = (
                SELECT {age_sql}
                FROM story_clusters c2
                WHERE c2.id = %s
              );
            """,
            (cluster_id,),
        )
        age_bucket = cur.fetchone() or {}
        if (
            int(age_bucket.get("n") or 0) >= _MIN_BUCKET_SAMPLE
            and age_bucket.get("p99") is not None
        ):
            return ThresholdResolution(bucket="age_global", threshold=float(age_bucket["p99"]))

        # global fallback
        cur.execute(
            f"""
            SELECT percentile_cont(0.99) WITHIN GROUP (ORDER BY c.high_impact_final_score) AS p99
            FROM story_clusters c
            WHERE c.status = 'active'
              AND c.high_impact_eligible = TRUE
              AND c.high_impact_final_score IS NOT NULL
              AND c.high_impact_assessed_at >= now() - interval '{_CALIBRATION_LOOKBACK_DAYS} days';
            """
        )
        global_row = cur.fetchone() or {}
    p99 = global_row.get("p99")
    return ThresholdResolution(bucket="global", threshold=float(p99) if p99 is not None else 0.95)


def get_high_impact_rate_windows(
    conn: psycopg.Connection[Any],
    *,
    windows_days: tuple[int, ...] = (7, 30),
) -> list[HighImpactRateWindow]:
    """Compute high-impact label rate windows for guardrail monitoring."""
    windows: list[HighImpactRateWindow] = []
    with conn.cursor(row_factory=dict_row) as cur:
        for days in windows_days:
            cur.execute(
                f"""
                SELECT
                  COUNT(*) FILTER (WHERE c.high_impact_eligible = TRUE) AS eligible_count,
                  COUNT(*) FILTER (
                    WHERE c.high_impact_eligible = TRUE
                      AND c.high_impact_label = TRUE
                  ) AS labeled_count
                FROM story_clusters c
                WHERE c.status = 'active'
                  AND c.high_impact_assessed_at >= now() - interval '{int(days)} days';
                """
            )
            row = cur.fetchone() or {}
            eligible = int(row.get("eligible_count") or 0)
            labeled = int(row.get("labeled_count") or 0)
            rate = (labeled / eligible) if eligible > 0 else 0.0
            windows.append(
                HighImpactRateWindow(
                    days=int(days),
                    eligible_count=eligible,
                    labeled_count=labeled,
                    rate=rate,
                    in_guardrail_band=(
                        _RATE_GUARDRAIL_LOW <= rate <= _RATE_GUARDRAIL_HIGH
                        if eligible > 0
                        else True
                    ),
                )
            )
    return windows


def get_high_impact_debug_report(
    conn: psycopg.Connection[Any],
    *,
    limit: int = 10,
    eligible_only: bool = True,
) -> tuple[list[HighImpactDebugRow], list[HighImpactDebugRow]]:
    """
    Return top passes and near-misses for calibration/debug analysis.

    - Passes are ordered by threshold delta descending.
    - Near-misses are non-labeled rows ordered by threshold delta descending.
    """
    where_eligible = "AND c.high_impact_eligible = TRUE" if eligible_only else ""
    select_sql = f"""
        SELECT
          c.id::text AS cluster_id,
          c.canonical_title AS title,
          c.high_impact_final_score AS final_score,
          c.high_impact_threshold_value AS threshold,
          (c.high_impact_final_score - c.high_impact_threshold_value) AS threshold_delta,
          c.high_impact_confidence AS confidence,
          c.high_impact_label AS label,
          COALESCE(
            (c.high_impact_debug->>'novelty_score')::double precision,
            NULL
          ) AS novelty_score,
          COALESCE(
            (c.high_impact_debug->>'translation_score')::double precision,
            NULL
          ) AS translation_score,
          COALESCE(
            (c.high_impact_debug->>'evidence_score')::double precision,
            NULL
          ) AS evidence_score,
          COALESCE(
            (c.high_impact_debug->>'passed_threshold')::boolean,
            FALSE
          ) AS passed_threshold,
          COALESCE(
            (c.high_impact_debug->>'passed_confidence')::boolean,
            FALSE
          ) AS passed_confidence,
          COALESCE(
            (c.high_impact_debug->>'passed_evidence_gate')::boolean,
            FALSE
          ) AS passed_evidence_gate,
          (c.high_impact_debug->'llm_shadow') AS llm_shadow
        FROM story_clusters c
        WHERE c.status = 'active'
          AND c.high_impact_assessed_at IS NOT NULL
          {where_eligible}
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            {select_sql}
              AND c.high_impact_label = TRUE
            ORDER BY threshold_delta DESC NULLS LAST, final_score DESC NULLS LAST
            LIMIT %s;
            """,
            (limit,),
        )
        pass_rows = [
            HighImpactDebugRow(
                cluster_id=str(r["cluster_id"]),
                title=str(r["title"] or ""),
                final_score=float(r["final_score"]) if r.get("final_score") is not None else None,
                threshold=float(r["threshold"]) if r.get("threshold") is not None else None,
                threshold_delta=(
                    float(r["threshold_delta"]) if r.get("threshold_delta") is not None else None
                ),
                confidence=float(r["confidence"]) if r.get("confidence") is not None else None,
                label=bool(r.get("label")),
                novelty_score=(
                    float(r["novelty_score"]) if r.get("novelty_score") is not None else None
                ),
                translation_score=(
                    float(r["translation_score"])
                    if r.get("translation_score") is not None
                    else None
                ),
                evidence_score=(
                    float(r["evidence_score"]) if r.get("evidence_score") is not None else None
                ),
                passed_threshold=bool(r.get("passed_threshold")),
                passed_confidence=bool(r.get("passed_confidence")),
                passed_evidence_gate=bool(r.get("passed_evidence_gate")),
                llm_shadow=(
                    dict(r["llm_shadow"])
                    if isinstance(r.get("llm_shadow"), dict)
                    else None
                ),
            )
            for r in cur.fetchall()
        ]

        cur.execute(
            f"""
            {select_sql}
              AND c.high_impact_label = FALSE
            ORDER BY threshold_delta DESC NULLS LAST, final_score DESC NULLS LAST
            LIMIT %s;
            """,
            (limit,),
        )
        near_miss_rows = [
            HighImpactDebugRow(
                cluster_id=str(r["cluster_id"]),
                title=str(r["title"] or ""),
                final_score=float(r["final_score"]) if r.get("final_score") is not None else None,
                threshold=float(r["threshold"]) if r.get("threshold") is not None else None,
                threshold_delta=(
                    float(r["threshold_delta"]) if r.get("threshold_delta") is not None else None
                ),
                confidence=float(r["confidence"]) if r.get("confidence") is not None else None,
                label=bool(r.get("label")),
                novelty_score=(
                    float(r["novelty_score"]) if r.get("novelty_score") is not None else None
                ),
                translation_score=(
                    float(r["translation_score"])
                    if r.get("translation_score") is not None
                    else None
                ),
                evidence_score=(
                    float(r["evidence_score"]) if r.get("evidence_score") is not None else None
                ),
                passed_threshold=bool(r.get("passed_threshold")),
                passed_confidence=bool(r.get("passed_confidence")),
                passed_evidence_gate=bool(r.get("passed_evidence_gate")),
                llm_shadow=(
                    dict(r["llm_shadow"])
                    if isinstance(r.get("llm_shadow"), dict)
                    else None
                ),
            )
            for r in cur.fetchall()
        ]
    return pass_rows, near_miss_rows
