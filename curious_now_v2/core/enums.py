from __future__ import annotations

from enum import StrEnum


class SourceRole(StrEnum):
    PRIMARY_RESEARCH = "primary_research"
    JOURNALISM = "journalism"
    LAB_ANNOUNCEMENT = "lab_announcement"
    INSTITUTIONAL = "institutional"
    GOVERNMENT = "government"
    PRESS_RELEASE = "press_release"
    DISCOVERY = "discovery"


class FeedKind(StrEnum):
    RSS = "rss"
    ATOM = "atom"
    API = "api"


class ContentType(StrEnum):
    NEWS = "news"
    LAB_ANNOUNCEMENT = "lab_announcement"
    PRESS_RELEASE = "press_release"
    PREPRINT = "preprint"
    PEER_REVIEWED = "peer_reviewed"
    REPORT = "report"
    BLOG = "blog"
    DATASET = "dataset"
    OTHER = "other"


class AccessClass(StrEnum):
    METADATA_ONLY = "metadata_only"
    SNIPPET = "snippet"
    ABSTRACT = "abstract"
    OPEN_FULL_TEXT = "open_full_text"


class StoryItemRole(StrEnum):
    PRIMARY_EVIDENCE = "primary_evidence"
    INDEPENDENT_COVERAGE = "independent_coverage"
    ANNOUNCEMENT = "announcement"
    CONTEXT = "context"
    DISCOVERY = "discovery"


class ClaimKind(StrEnum):
    OBSERVATION = "observation"
    RESULT = "result"
    METHOD = "method"
    COMPARISON = "comparison"
    LIMITATION = "limitation"
    UNCERTAINTY = "uncertainty"
    CONTEXT = "context"


class ExplanationDepth(StrEnum):
    GLANCE = "glance"
    EXPLAIN = "explain"
    TECHNICAL = "technical"


class ExplanationStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class SpineStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


class ReaderTitleKind(StrEnum):
    DISPLAY = "display"
    SOURCE = "source"
    WORKING = "working"
