from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContentType(str, Enum):
    news = "news"
    press_release = "press_release"
    preprint = "preprint"
    peer_reviewed = "peer_reviewed"
    report = "report"


class EntityType(str, Enum):
    person = "person"
    institution = "institution"
    model = "model"
    dataset = "dataset"
    method = "method"
    venue = "venue"


class SourceType(str, Enum):
    journalism = "journalism"
    journal = "journal"
    preprint_server = "preprint_server"
    university = "university"
    government = "government"
    lab = "lab"
    blog = "blog"


class ReliabilityTier(str, Enum):
    tier1 = "tier1"
    tier2 = "tier2"
    tier3 = "tier3"


class FeedType(str, Enum):
    rss = "rss"
    atom = "atom"
    api = "api"


class Source(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: UUID
    name: str
    homepage_url: str | None = None
    source_type: SourceType
    reliability_tier: ReliabilityTier | None = None
    active: bool


class SourceFeedHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feed_id: UUID
    feed_url: str
    feed_type: FeedType
    active: bool
    fetch_interval_minutes: int | None = None
    last_fetched_at: datetime | None = None
    last_status: int | None = None
    error_streak: int


class SourcesResponseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: Source
    feeds: list[SourceFeedHealth]


class SourcesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sources: list[SourcesResponseRow]


class ItemSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: UUID
    name: str


class Item(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    canonical_url: str
    url: str
    title: str
    snippet: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    content_type: ContentType
    paywalled: bool | None = None
    source: ItemSource
    arxiv_id: str | None = None
    doi: str | None = None
    pmid: str | None = None


class ItemsFeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    results: list[Item]


class TopicChip(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: UUID
    name: str
    score: float


class WhyInFeed(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reason: str = Field(..., description="Short reason string for explainability")
    details: dict[str, Any] | None = None


class ClusterCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_id: UUID
    canonical_title: str
    updated_at: datetime
    distinct_source_count: int
    top_topics: list[TopicChip] = []
    content_type_badges: list[ContentType] = []
    method_badges: list[str] = []
    takeaway: str | None = None
    confidence_band: Literal["early", "growing", "established"] | None = None
    anti_hype_flags: list[str] = []
    is_saved: bool | None = None
    is_watched: bool | None = None
    why_in_feed: WhyInFeed | None = None


class ClustersFeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tab: str
    page: int
    results: list[ClusterCard]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    title: str
    url: str
    published_at: datetime | None = None
    source: ItemSource
    content_type: ContentType


class ClusterDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_id: UUID
    canonical_title: str
    created_at: datetime
    updated_at: datetime
    distinct_source_count: int
    topics: list[TopicChip] = []
    content_type_breakdown: dict[str, int] | None = None
    evidence: dict[str, list[EvidenceItem]]

    takeaway: str | None = None
    summary_intuition: str | None = None
    summary_deep_dive: str | None = None
    assumptions: list[str] = []
    limitations: list[str] = []
    what_could_change_this: list[str] = []
    confidence_band: Literal["early", "growing", "established"] | None = None
    method_badges: list[str] = []
    anti_hype_flags: list[str] = []
    takeaway_supporting_item_ids: list[UUID] = []
    summary_intuition_supporting_item_ids: list[UUID] = []
    summary_deep_dive_supporting_item_ids: list[UUID] = []
    glossary_entries: list[GlossaryEntry] = []
    is_saved: bool | None = None
    is_watched: bool | None = None


class Topic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: UUID
    name: str
    description_short: str | None = None
    is_followed: bool | None = None


class TopicsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topics: list[Topic]


class TopicDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic: Topic
    latest_clusters: list[ClusterCard] = []
    trending_clusters: list[ClusterCard] = []


class SearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    clusters: list[ClusterCard]
    topics: list[Topic] | None = None
    entities: list[Entity] | None = None


class RedirectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    redirect_to_cluster_id: UUID


class TopicRedirectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    redirect_to_topic_id: UUID


class EntityRedirectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    redirect_to_entity_id: UUID


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    glossary_entry_id: UUID
    term: str
    definition_short: str
    definition_long: str | None = None


class GlossaryLookupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry: GlossaryEntry


class SourcePackFeed(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feed_url: str
    feed_type: FeedType
    fetch_interval_minutes: int = 30
    active: bool = True


class SourcePackSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    homepage_url: str | None = None
    source_type: SourceType
    reliability_tier: ReliabilityTier | None = None
    terms_notes: str | None = None
    active: bool = True
    feeds: list[SourcePackFeed]


class SourcePack(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sources: list[SourcePackSource]


class ImportSourcePackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sources_upserted: int
    feeds_upserted: int


class PatchSourceRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    homepage_url: str | None = None
    source_type: SourceType | None = None
    reliability_tier: ReliabilityTier | None = None
    terms_notes: str | None = None
    active: bool | None = None


class PatchFeedRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feed_url: str | None = None
    feed_type: FeedType | None = None
    fetch_interval_minutes: int | None = None
    active: bool | None = None


class RunIngestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str


class AdminRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["accepted"]


class MagicLinkStartRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email: str


class MagicLinkStartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str


class MagicLinkVerifyRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    created_at: datetime


class MagicLinkVerifyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: User


class StatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str


class SimpleOkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["ok"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: User


class UserPrefs(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_mode_default: Literal["intuition", "deep"] = "intuition"
    followed_topic_ids: list[UUID] = []
    followed_entity_ids: list[UUID] = []
    blocked_source_ids: list[UUID] = []
    saved_cluster_ids: list[UUID] = []
    hidden_cluster_ids: list[UUID] = []
    notification_settings: dict[str, Any] = {}


class UserPrefsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prefs: UserPrefs


class UserPrefsPatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_mode_default: Literal["intuition", "deep"] | None = None
    notification_settings: dict[str, Any] | None = None


class FeedbackCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_type: str
    cluster_id: UUID | None = None
    topic_id: UUID | None = None
    message: str | None = None


class FeedbackCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_id: UUID
    status: str


class FeedbackIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_type: Literal[
        "confusing",
        "overstated",
        "incorrect",
        "missing_context",
        "broken_link",
        "other",
    ]
    client_id: UUID | None = None
    cluster_id: UUID | None = None
    item_id: UUID | None = None
    topic_id: UUID | None = None
    message: str | None = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["accepted"]
    feedback_id: UUID


class FeedbackReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_id: UUID
    created_at: datetime
    feedback_type: Literal[
        "confusing",
        "overstated",
        "incorrect",
        "missing_context",
        "broken_link",
        "other",
    ]
    status: Literal["new", "triaged", "resolved", "ignored"]
    message: str | None = None
    cluster_id: UUID | None = None
    item_id: UUID | None = None
    topic_id: UUID | None = None
    user_id: UUID | None = None


class AdminFeedbackListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    results: list[FeedbackReport]


class AdminFeedbackPatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["triaged", "resolved", "ignored"] | None = None
    resolution_notes: str | None = None


class AdminClusterMergeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    to_cluster_id: UUID
    notes: str | None = None
    supporting_item_ids: list[UUID] = []


class AdminClusterMergeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_cluster_id: UUID
    to_cluster_id: UUID


class AdminClusterSplitRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    new_cluster_title: str | None = None
    move_item_ids: list[UUID]
    notes: str | None = None


class AdminClusterSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_cluster_id: UUID
    new_cluster_id: UUID


class AdminClusterQuarantineRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notes: str | None = None


class AdminClusterPatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    canonical_title: str | None = None
    representative_item_id: UUID | None = None
    takeaway: str | None = None
    takeaway_supporting_item_ids: list[UUID] = []
    summary_intuition: str | None = None
    summary_intuition_supporting_item_ids: list[UUID] = []
    summary_deep_dive: str | None = None
    summary_deep_dive_supporting_item_ids: list[UUID] = []
    assumptions: list[str] = []
    limitations: list[str] = []
    what_could_change_this: list[str] = []
    confidence_band: Literal["early", "growing", "established"] | None = None
    method_badges: list[str] = []
    anti_hype_flags: list[str] = []


class AdminClusterTopicAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: UUID
    score: float | None = None
    locked: bool | None = None


class AdminSetClusterTopicsRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    replace: bool = True
    topics: list[AdminClusterTopicAssignment]
    notes: str | None = None


class AdminTopicCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description_short: str | None = None
    aliases: list[str] = []
    parent_topic_id: UUID | None = None


class AdminTopicPatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    description_short: str | None = None
    aliases: list[str] | None = None
    parent_topic_id: UUID | None = None


class AdminTopicMergeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    to_topic_id: UUID
    notes: str | None = None


class AdminTopicMergeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_topic_id: UUID
    to_topic_id: UUID


class AdminLineageNodeCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_type: Literal["paper", "model", "dataset", "method"]
    title: str
    external_url: str | None = None
    published_at: datetime | None = None
    external_ids: dict[str, Any] | None = None
    topic_ids: list[UUID] = []


class AdminLineageEdgeCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_node_id: UUID
    to_node_id: UUID
    relation_type: Literal[
        "extends",
        "improves",
        "compresses",
        "replaces_in_some_settings",
        "contradicts",
        "orthogonal",
    ]
    evidence_item_ids: list[UUID]
    notes_short: str | None = None


class EventIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: Literal[
        "open_cluster",
        "click_item",
        "save_cluster",
        "unsave_cluster",
        "hide_cluster",
        "unhide_cluster",
        "follow_topic",
        "unfollow_topic",
        "block_source",
        "unblock_source",
    ]
    client_id: UUID | None = None
    cluster_id: UUID | None = None
    item_id: UUID | None = None
    topic_id: UUID | None = None
    meta: dict[str, Any] | None = None


class EventsIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: Literal["accepted"]


class SavedCluster(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    saved_at: datetime
    cluster: ClusterCard


class UserSavesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    saved: list[SavedCluster]


class WatchedCluster(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    watched_at: datetime
    cluster: ClusterCard


class UserWatchesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    watched: list[WatchedCluster]


class Entity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    entity_type: EntityType
    name: str
    description_short: str | None = None
    external_url: str | None = None
    is_followed: bool | None = None


class EntitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    results: list[Entity]


class EntityDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    entity_type: EntityType
    name: str
    description_short: str | None = None
    external_url: str | None = None
    is_followed: bool | None = None

    latest_clusters: list[ClusterCard] = []
    related_entities: list[Entity] = []


class UserFollowedEntitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entities: list[Entity]


class AdminEntityCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: EntityType
    name: str
    description_short: str | None = None
    external_url: str | None = None


class AdminEntityPatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: EntityType | None = None
    name: str | None = None
    description_short: str | None = None
    external_url: str | None = None


class AdminEntityMergeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    to_entity_id: UUID
    notes: str | None = None
    supporting_item_ids: list[UUID] = []


class AdminEntityMergeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_entity_id: UUID
    to_entity_id: UUID


class AdminClusterEntityAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    score: float | None = None
    locked: bool | None = None


class AdminSetClusterEntitiesRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    replace: bool = True
    entities: list[AdminClusterEntityAssignment]
    notes: str | None = None


class Experiment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    experiment_id: UUID
    key: str
    description: str | None = None
    active: bool
    start_at: datetime | None = None
    end_at: datetime | None = None


class AdminExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    description: str | None = None
    active: bool | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class AdminExperimentPatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str | None = None
    active: bool | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class FeatureFlag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    enabled: bool
    config: dict[str, Any] = {}


class AdminFeatureFlagUpsertRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool | None = None
    config: dict[str, Any] | None = None


class LineageNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    title: str
    node_type: str
    external_url: str | None = None
    published_at: datetime | None = None


class LineageEdge(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    from_node_id: UUID = Field(..., alias="from")
    to_node_id: UUID = Field(..., alias="to")
    relation_type: str
    evidence_item_ids: list[UUID] = []
    notes_short: str | None = None


class TopicLineageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    topic_id: UUID
    nodes: list[LineageNode]
    edges: list[LineageEdge]


class ClusterUpdateEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    change_type: str
    summary: str
    diff: dict[str, Any] | None = None
    supporting_item_ids: list[UUID] = []


class ClusterUpdatesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_id: UUID
    updates: list[ClusterUpdateEntry]


# Forward refs
ClusterDetail.model_rebuild()
SearchResponse.model_rebuild()
EntityDetail.model_rebuild()
