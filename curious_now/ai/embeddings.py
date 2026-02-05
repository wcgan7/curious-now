"""Embedding generation for semantic search.

This module generates vector embeddings for story clusters to enable
semantic search capabilities using pgvector.

Note: Embeddings can be generated via:
1. LLM CLI tools that support embeddings
2. Local sentence-transformers models
3. API calls (OpenAI, Cohere, etc.)

This implementation focuses on CLI-based approaches to avoid API costs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Default embedding dimension (matches OpenAI text-embedding-3-small)
DEFAULT_EMBEDDING_DIM = 1536

# Supported embedding providers
EMBEDDING_PROVIDERS = ["ollama", "sentence-transformers", "mock"]


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""

    embedding: list[float]
    model: str
    provider: str
    source_text_hash: str
    dimensions: int
    success: bool = True
    error: str | None = None

    @staticmethod
    def failure(error: str) -> EmbeddingResult:
        """Create a failure result."""
        return EmbeddingResult(
            embedding=[],
            model="unknown",
            provider="unknown",
            source_text_hash="",
            dimensions=0,
            success=False,
            error=error,
        )


@dataclass
class ClusterEmbeddingInput:
    """Input data for cluster embedding generation."""

    cluster_id: str
    canonical_title: str
    takeaway: str | None = None
    topic_names: list[str] | None = None
    item_titles: list[str] | None = None


def _compute_text_hash(text: str) -> str:
    """Compute a hash of the source text for caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_embedding_text(input_data: ClusterEmbeddingInput) -> str:
    """
    Build the text to embed from cluster data.

    Combines title, takeaway, topics, and item titles into a single
    text representation for embedding.
    """
    parts = [input_data.canonical_title]

    if input_data.takeaway:
        parts.append(input_data.takeaway)

    if input_data.topic_names:
        parts.append(f"Topics: {', '.join(input_data.topic_names)}")

    if input_data.item_titles:
        # Include top item titles for additional context
        for title in input_data.item_titles[:3]:
            parts.append(title)

    return ". ".join(parts)


class EmbeddingProvider:
    """Base class for embedding providers."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

    def generate(self, text: str) -> EmbeddingResult:
        raise NotImplementedError


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Generate embeddings using Ollama.

    Uses the 'ollama embed' command for embedding generation.
    Requires an embedding model like 'nomic-embed-text' or 'mxbai-embed-large'.
    """

    def __init__(self, model: str = "nomic-embed-text") -> None:
        self.model = model

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """Check if ollama is available with embedding support."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding using ollama."""
        try:
            # Use ollama's embed command (if available) or API
            result = subprocess.run(
                [
                    "ollama",
                    "run",
                    self.model,
                    f"[EMBED]{text}",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                # Fallback: use curl to call ollama API
                return self._generate_via_api(text)

            # Try to parse embedding from output
            output = result.stdout.strip()
            try:
                embedding = json.loads(output)
                if isinstance(embedding, list):
                    return EmbeddingResult(
                        embedding=embedding,
                        model=self.model,
                        provider=self.name,
                        source_text_hash=_compute_text_hash(text),
                        dimensions=len(embedding),
                    )
            except json.JSONDecodeError:
                pass

            # Fallback to API method
            return self._generate_via_api(text)

        except subprocess.TimeoutExpired:
            return EmbeddingResult.failure("Ollama embedding request timed out")
        except FileNotFoundError:
            return EmbeddingResult.failure("Ollama CLI not found")
        except Exception as e:
            return EmbeddingResult.failure(str(e))

    def _generate_via_api(self, text: str) -> EmbeddingResult:
        """Generate embedding via ollama REST API."""
        try:
            import urllib.request

            data = json.dumps({
                "model": self.model,
                "prompt": text,
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/embeddings",
                data=data,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embedding = result.get("embedding", [])

                if not embedding:
                    return EmbeddingResult.failure("No embedding in response")

                return EmbeddingResult(
                    embedding=embedding,
                    model=self.model,
                    provider=self.name,
                    source_text_hash=_compute_text_hash(text),
                    dimensions=len(embedding),
                )

        except Exception as e:
            return EmbeddingResult.failure(f"Ollama API error: {e}")


class SentenceTransformersProvider(EmbeddingProvider):
    """
    Generate embeddings using sentence-transformers library.

    This runs locally without any API calls, but requires the
    sentence-transformers package to be installed.
    """

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model
        self._model: Any = None

    @property
    def name(self) -> str:
        return "sentence-transformers"

    def is_available(self) -> bool:
        """Check if sentence-transformers is available."""
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401

            return True
        except ImportError:
            return False

    def _load_model(self) -> Any:
        """Lazy load the model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding using sentence-transformers."""
        try:
            model = self._load_model()
            embedding = model.encode(text, convert_to_numpy=True)
            embedding_list = embedding.tolist()

            return EmbeddingResult(
                embedding=embedding_list,
                model=self.model_name,
                provider=self.name,
                source_text_hash=_compute_text_hash(text),
                dimensions=len(embedding_list),
            )
        except Exception as e:
            return EmbeddingResult.failure(str(e))


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Mock embedding provider for testing.

    Generates deterministic pseudo-embeddings based on text hash.
    """

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.dimensions = dimensions

    @property
    def name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def generate(self, text: str) -> EmbeddingResult:
        """Generate a deterministic mock embedding."""
        text_hash = _compute_text_hash(text)

        # Generate deterministic values from hash
        import random

        rng = random.Random(text_hash)
        embedding = [rng.gauss(0, 1) for _ in range(self.dimensions)]

        # Normalize to unit length
        magnitude = sum(x * x for x in embedding) ** 0.5
        embedding = [x / magnitude for x in embedding]

        return EmbeddingResult(
            embedding=embedding,
            model="mock",
            provider=self.name,
            source_text_hash=text_hash,
            dimensions=self.dimensions,
        )


def get_embedding_provider(provider_type: str | None = None) -> EmbeddingProvider:
    """
    Get an embedding provider by type.

    Args:
        provider_type: Type of provider ("ollama", "sentence-transformers", "mock")
                      If None, tries providers in order until one is available.

    Returns:
        EmbeddingProvider instance

    Raises:
        ValueError: If no provider is available
    """
    providers: dict[str, type[EmbeddingProvider]] = {
        "ollama": OllamaEmbeddingProvider,
        "sentence-transformers": SentenceTransformersProvider,
        "mock": MockEmbeddingProvider,
    }

    if provider_type:
        if provider_type not in providers:
            raise ValueError(f"Unknown embedding provider: {provider_type}")
        return providers[provider_type]()

    # Try providers in preference order
    for name in ["sentence-transformers", "ollama", "mock"]:
        provider = providers[name]()
        if provider.is_available():
            logger.info("Using embedding provider: %s", name)
            return provider

    # Should never happen since mock is always available
    return MockEmbeddingProvider()


def generate_cluster_embedding(
    input_data: ClusterEmbeddingInput,
    *,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingResult:
    """
    Generate an embedding for a story cluster.

    Args:
        input_data: Cluster data to embed
        provider: Embedding provider to use (auto-detected if None)

    Returns:
        EmbeddingResult with the embedding vector
    """
    if not input_data.canonical_title:
        return EmbeddingResult.failure("No canonical title provided")

    if provider is None:
        provider = get_embedding_provider()

    # Build text to embed
    text = _build_embedding_text(input_data)

    # Generate embedding
    return provider.generate(text)


def generate_query_embedding(
    query: str,
    *,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingResult:
    """
    Generate an embedding for a search query.

    Args:
        query: The search query text
        provider: Embedding provider to use (auto-detected if None)

    Returns:
        EmbeddingResult with the embedding vector
    """
    if not query or not query.strip():
        return EmbeddingResult.failure("Empty query")

    if provider is None:
        provider = get_embedding_provider()

    return provider.generate(query.strip())


def cosine_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Cosine similarity score (0-1)
    """
    if len(embedding1) != len(embedding2):
        raise ValueError("Embeddings must have same dimensions")

    dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
    magnitude1 = sum(a * a for a in embedding1) ** 0.5
    magnitude2 = sum(b * b for b in embedding2) ** 0.5

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return float(dot_product / (magnitude1 * magnitude2))


async def generate_embeddings_batch(
    clusters: list[ClusterEmbeddingInput],
    *,
    provider: EmbeddingProvider | None = None,
) -> list[EmbeddingResult]:
    """
    Generate embeddings for multiple clusters.

    Note: Currently processes sequentially. sentence-transformers
    can batch internally for better performance.

    Args:
        clusters: List of ClusterEmbeddingInput objects
        provider: Embedding provider to use

    Returns:
        List of EmbeddingResult objects in same order as input
    """
    if provider is None:
        provider = get_embedding_provider()

    results = []
    for cluster in clusters:
        result = generate_cluster_embedding(cluster, provider=provider)
        results.append(result)

    return results
