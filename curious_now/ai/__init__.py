"""AI module for LLM integrations."""

from curious_now.ai.citation_check import (
    CheckedClaim,
    CitationCheckInput,
    CitationCheckResult,
    CitationFlag,
    FlagType,
    check_citations,
    check_deep_dive_citations,
    check_takeaway_citations,
)
from curious_now.ai.deep_dive import (
    DeepDiveContent,
    DeepDiveInput,
    DeepDiveResult,
    SourceSummary,
    deep_dive_from_json,
    deep_dive_to_json,
    generate_deep_dive,
    generate_deep_dive_from_db_data,
)
from curious_now.ai.embeddings import (
    ClusterEmbeddingInput,
    EmbeddingProvider,
    EmbeddingResult,
    cosine_similarity,
    generate_cluster_embedding,
    generate_query_embedding,
    get_embedding_provider,
)
from curious_now.ai.intuition import (
    GlossaryTerm,
    IntuitionInput,
    IntuitionResult,
    generate_intuition,
    generate_intuition_from_db_data,
)
from curious_now.ai.lineage import (
    EdgeType,
    LineageAnalysisInput,
    LineageAnalysisResult,
    LineageEdge,
    StoryNode,
    analyze_lineage,
    analyze_lineage_from_db_data,
    find_potential_connections,
    lineage_edge_to_json,
    lineage_result_to_json,
)
from curious_now.ai.llm_adapter import (
    LLMAdapter,
    LLMResponse,
    get_llm_adapter,
)
from curious_now.ai.takeaways import (
    ItemSummary,
    TakeawayInput,
    TakeawayResult,
    generate_takeaway,
    generate_takeaway_from_db_data,
)
from curious_now.ai.update_detection import (
    UpdateDetectionInput,
    UpdateDetectionResult,
    UpdateType,
    detect_update,
    detect_update_from_db_data,
    update_result_to_json,
)

__all__ = [
    # LLM Adapter
    "LLMAdapter",
    "LLMResponse",
    "get_llm_adapter",
    # Takeaways
    "ItemSummary",
    "TakeawayInput",
    "TakeawayResult",
    "generate_takeaway",
    "generate_takeaway_from_db_data",
    # Embeddings
    "ClusterEmbeddingInput",
    "EmbeddingProvider",
    "EmbeddingResult",
    "generate_cluster_embedding",
    "generate_query_embedding",
    "get_embedding_provider",
    "cosine_similarity",
    # Intuition
    "GlossaryTerm",
    "IntuitionInput",
    "IntuitionResult",
    "generate_intuition",
    "generate_intuition_from_db_data",
    # Deep Dive
    "DeepDiveContent",
    "DeepDiveInput",
    "DeepDiveResult",
    "SourceSummary",
    "generate_deep_dive",
    "generate_deep_dive_from_db_data",
    "deep_dive_to_json",
    "deep_dive_from_json",
    # Citation Check
    "CitationCheckInput",
    "CitationCheckResult",
    "CitationFlag",
    "CheckedClaim",
    "FlagType",
    "check_citations",
    "check_takeaway_citations",
    "check_deep_dive_citations",
    # Update Detection (Phase 3)
    "UpdateDetectionInput",
    "UpdateDetectionResult",
    "UpdateType",
    "detect_update",
    "detect_update_from_db_data",
    "update_result_to_json",
    # Lineage (Phase 3)
    "EdgeType",
    "LineageAnalysisInput",
    "LineageAnalysisResult",
    "LineageEdge",
    "StoryNode",
    "analyze_lineage",
    "analyze_lineage_from_db_data",
    "find_potential_connections",
    "lineage_edge_to_json",
    "lineage_result_to_json",
]
