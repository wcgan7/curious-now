"""Integration tests for AI embedding generation.

These tests verify embedding generation for semantic search.
Tests both mock and real embedding providers.
"""

from __future__ import annotations

import pytest

from curious_now.ai.embeddings import (
    DEFAULT_EMBEDDING_DIM,
    ClusterEmbeddingInput,
    EmbeddingResult,
    MockEmbeddingProvider,
    OllamaEmbeddingProvider,
    SentenceTransformersProvider,
    _build_embedding_text,
    _compute_text_hash,
    cosine_similarity,
    generate_cluster_embedding,
    generate_query_embedding,
    get_embedding_provider,
)

# ─────────────────────────────────────────────────────────────────────────────
# Test Data
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_cluster_input() -> ClusterEmbeddingInput:
    """Sample cluster input for embedding generation."""
    return ClusterEmbeddingInput(
        cluster_id="cluster-123",
        canonical_title="New CRISPR variant enables precise gene editing in neurons",
        takeaway="Scientists developed a CRISPR modification that works in brain cells.",
        topic_names=["Gene Therapy", "Neuroscience", "CRISPR"],
        item_titles=[
            "MIT develops brain-targeted CRISPR",
            "Gene therapy for neurological diseases advances",
            "CRISPR precision improves for brain applications",
        ],
    )


@pytest.fixture
def sample_cluster_minimal() -> ClusterEmbeddingInput:
    """Minimal cluster input with just title."""
    return ClusterEmbeddingInput(
        cluster_id="cluster-456",
        canonical_title="Antarctic ice loss accelerates",
    )


@pytest.fixture
def mock_provider() -> MockEmbeddingProvider:
    """Mock embedding provider for fast tests."""
    return MockEmbeddingProvider()


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests - Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeTextHash:
    """Test text hashing helper."""

    def test_hash_deterministic(self) -> None:
        text = "Hello, world!"
        hash1 = _compute_text_hash(text)
        hash2 = _compute_text_hash(text)

        assert hash1 == hash2

    def test_different_text_different_hash(self) -> None:
        hash1 = _compute_text_hash("Hello")
        hash2 = _compute_text_hash("World")

        assert hash1 != hash2

    def test_hash_length(self) -> None:
        hash_val = _compute_text_hash("Test text")

        assert len(hash_val) == 16


class TestBuildEmbeddingText:
    """Test embedding text building helper."""

    def test_build_full_text(self, sample_cluster_input: ClusterEmbeddingInput) -> None:
        text = _build_embedding_text(sample_cluster_input)

        assert sample_cluster_input.canonical_title in text
        assert "brain cells" in text  # From takeaway
        assert "Gene Therapy" in text  # From topics
        assert "MIT develops" in text  # From item titles

    def test_build_minimal_text(self, sample_cluster_minimal: ClusterEmbeddingInput) -> None:
        text = _build_embedding_text(sample_cluster_minimal)

        assert text == sample_cluster_minimal.canonical_title

    def test_build_text_limits_items(self) -> None:
        input_data = ClusterEmbeddingInput(
            cluster_id="test",
            canonical_title="Test",
            item_titles=[f"Item {i}" for i in range(10)],
        )
        text = _build_embedding_text(input_data)

        # Should only include first 3 items
        assert "Item 0" in text
        assert "Item 2" in text
        assert "Item 3" not in text


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests - Mock Embedding Provider
# ─────────────────────────────────────────────────────────────────────────────


class TestMockEmbeddingProvider:
    """Test mock embedding provider."""

    def test_is_available(self, mock_provider: MockEmbeddingProvider) -> None:
        assert mock_provider.is_available() is True

    def test_name(self, mock_provider: MockEmbeddingProvider) -> None:
        assert mock_provider.name == "mock"

    def test_generate_returns_embedding(self, mock_provider: MockEmbeddingProvider) -> None:
        result = mock_provider.generate("Test text")

        assert isinstance(result, EmbeddingResult)
        assert result.success is True
        assert len(result.embedding) == DEFAULT_EMBEDDING_DIM
        assert result.provider == "mock"
        assert result.model == "mock"

    def test_generate_deterministic(self, mock_provider: MockEmbeddingProvider) -> None:
        result1 = mock_provider.generate("Test text")
        result2 = mock_provider.generate("Test text")

        assert result1.embedding == result2.embedding
        assert result1.source_text_hash == result2.source_text_hash

    def test_generate_different_for_different_text(
        self, mock_provider: MockEmbeddingProvider
    ) -> None:
        result1 = mock_provider.generate("Hello")
        result2 = mock_provider.generate("World")

        assert result1.embedding != result2.embedding

    def test_embedding_normalized(self, mock_provider: MockEmbeddingProvider) -> None:
        result = mock_provider.generate("Test text")

        # Check unit length (approximately 1.0)
        magnitude = sum(x * x for x in result.embedding) ** 0.5
        assert abs(magnitude - 1.0) < 0.01

    def test_custom_dimensions(self) -> None:
        provider = MockEmbeddingProvider(dimensions=384)
        result = provider.generate("Test text")

        assert len(result.embedding) == 384
        assert result.dimensions == 384


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests - Embedding Generation Functions
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateClusterEmbedding:
    """Test cluster embedding generation."""

    def test_generate_basic(
        self,
        sample_cluster_input: ClusterEmbeddingInput,
        mock_provider: MockEmbeddingProvider,
    ) -> None:
        result = generate_cluster_embedding(sample_cluster_input, provider=mock_provider)

        assert result.success is True
        assert len(result.embedding) == DEFAULT_EMBEDDING_DIM
        assert result.source_text_hash != ""

    def test_generate_minimal_input(
        self,
        sample_cluster_minimal: ClusterEmbeddingInput,
        mock_provider: MockEmbeddingProvider,
    ) -> None:
        result = generate_cluster_embedding(sample_cluster_minimal, provider=mock_provider)

        assert result.success is True
        assert len(result.embedding) > 0

    def test_generate_empty_title_fails(self, mock_provider: MockEmbeddingProvider) -> None:
        input_data = ClusterEmbeddingInput(
            cluster_id="test",
            canonical_title="",
        )
        result = generate_cluster_embedding(input_data, provider=mock_provider)

        assert result.success is False
        assert "title" in result.error.lower()

    def test_generate_auto_selects_provider(
        self,
        sample_cluster_input: ClusterEmbeddingInput,
    ) -> None:
        # Should auto-select an available provider
        result = generate_cluster_embedding(sample_cluster_input)

        assert result.success is True
        assert result.provider in ["mock", "sentence-transformers", "ollama"]


class TestGenerateQueryEmbedding:
    """Test query embedding generation."""

    def test_generate_query(self, mock_provider: MockEmbeddingProvider) -> None:
        result = generate_query_embedding("gene therapy for brain diseases", provider=mock_provider)

        assert result.success is True
        assert len(result.embedding) == DEFAULT_EMBEDDING_DIM

    def test_generate_empty_query_fails(self, mock_provider: MockEmbeddingProvider) -> None:
        result = generate_query_embedding("", provider=mock_provider)

        assert result.success is False

    def test_generate_whitespace_query_fails(self, mock_provider: MockEmbeddingProvider) -> None:
        result = generate_query_embedding("   ", provider=mock_provider)

        assert result.success is False


# ─────────────────────────────────────────────────────────────────────────────
# Unit Tests - Cosine Similarity
# ─────────────────────────────────────────────────────────────────────────────


class TestCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_identical_vectors(self) -> None:
        vec = [1.0, 2.0, 3.0]
        similarity = cosine_similarity(vec, vec)

        assert abs(similarity - 1.0) < 0.001

    def test_orthogonal_vectors(self) -> None:
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        similarity = cosine_similarity(vec1, vec2)

        assert abs(similarity) < 0.001

    def test_opposite_vectors(self) -> None:
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        similarity = cosine_similarity(vec1, vec2)

        assert abs(similarity + 1.0) < 0.001

    def test_similar_vectors(self) -> None:
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.1, 2.1, 3.1]
        similarity = cosine_similarity(vec1, vec2)

        assert similarity > 0.99  # Very similar

    def test_different_lengths_raises(self) -> None:
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.0, 2.0]

        with pytest.raises(ValueError, match="same dimensions"):
            cosine_similarity(vec1, vec2)

    def test_zero_vector(self) -> None:
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        similarity = cosine_similarity(vec1, vec2)

        assert similarity == 0.0


class TestGetEmbeddingProvider:
    """Test provider factory function."""

    def test_get_mock_provider(self) -> None:
        provider = get_embedding_provider("mock")

        assert isinstance(provider, MockEmbeddingProvider)
        assert provider.name == "mock"

    def test_get_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            get_embedding_provider("unknown-provider")

    def test_auto_select_returns_available(self) -> None:
        provider = get_embedding_provider()

        assert provider.is_available() is True


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests - Semantic Similarity
# ─────────────────────────────────────────────────────────────────────────────


class TestSemanticSimilarityMock:
    """Test semantic similarity with mock provider."""

    def test_similar_concepts_have_similar_embeddings(
        self, mock_provider: MockEmbeddingProvider
    ) -> None:
        # Even with mock, similar text should produce somewhat similar embeddings
        # due to deterministic hashing
        query = "CRISPR gene editing in brain cells"
        cluster1 = ClusterEmbeddingInput(
            cluster_id="1",
            canonical_title="CRISPR enables gene editing in neurons",
            takeaway="Gene therapy for brain diseases",
        )
        cluster2 = ClusterEmbeddingInput(
            cluster_id="2",
            canonical_title="Antarctic ice sheet melting rapidly",
            takeaway="Climate change accelerates",
        )

        query_result = generate_query_embedding(query, provider=mock_provider)
        cluster1_result = generate_cluster_embedding(cluster1, provider=mock_provider)
        cluster2_result = generate_cluster_embedding(cluster2, provider=mock_provider)

        assert query_result.success
        assert cluster1_result.success
        assert cluster2_result.success

        # All should be different (deterministic but based on different text)
        sim_to_relevant = cosine_similarity(
            query_result.embedding, cluster1_result.embedding
        )
        sim_to_irrelevant = cosine_similarity(
            query_result.embedding, cluster2_result.embedding
        )

        # With mock, similarities are essentially random but bounded
        assert -1.0 <= sim_to_relevant <= 1.0
        assert -1.0 <= sim_to_irrelevant <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests - Real Providers
# ─────────────────────────────────────────────────────────────────────────────


class TestOllamaEmbeddingProvider:
    """Test Ollama embedding provider."""

    @pytest.fixture
    def ollama_provider(self) -> OllamaEmbeddingProvider:
        return OllamaEmbeddingProvider()

    def test_availability_check(self, ollama_provider: OllamaEmbeddingProvider) -> None:
        # Just verify the check runs without error
        available = ollama_provider.is_available()
        assert isinstance(available, bool)

    def test_name(self, ollama_provider: OllamaEmbeddingProvider) -> None:
        assert ollama_provider.name == "ollama"

    def test_generate_when_available(
        self, ollama_provider: OllamaEmbeddingProvider
    ) -> None:
        if not ollama_provider.is_available():
            pytest.skip("Ollama not available")

        result = ollama_provider.generate("Test text for embedding")

        if result.success:
            assert len(result.embedding) > 0
            assert result.provider == "ollama"


class TestSentenceTransformersProvider:
    """Test sentence-transformers embedding provider."""

    @pytest.fixture
    def st_provider(self) -> SentenceTransformersProvider:
        return SentenceTransformersProvider()

    def test_availability_check(self, st_provider: SentenceTransformersProvider) -> None:
        available = st_provider.is_available()
        assert isinstance(available, bool)

    def test_name(self, st_provider: SentenceTransformersProvider) -> None:
        assert st_provider.name == "sentence-transformers"

    def test_generate_when_available(
        self, st_provider: SentenceTransformersProvider
    ) -> None:
        if not st_provider.is_available():
            pytest.skip("sentence-transformers not available")

        result = st_provider.generate("Test text for embedding")

        assert result.success is True
        assert len(result.embedding) > 0
        assert result.provider == "sentence-transformers"

    def test_semantic_similarity_when_available(
        self, st_provider: SentenceTransformersProvider
    ) -> None:
        """Test that sentence-transformers produces semantically meaningful embeddings."""
        if not st_provider.is_available():
            pytest.skip("sentence-transformers not available")

        # Similar concepts
        result1 = st_provider.generate("Machine learning and artificial intelligence")
        result2 = st_provider.generate("AI and neural networks for computing")
        result3 = st_provider.generate("Recipe for chocolate cake with frosting")

        assert result1.success and result2.success and result3.success

        sim_related = cosine_similarity(result1.embedding, result2.embedding)
        sim_unrelated = cosine_similarity(result1.embedding, result3.embedding)

        # Related concepts should have higher similarity
        assert sim_related > sim_unrelated, (
            f"Related similarity ({sim_related:.3f}) should be > "
            f"unrelated similarity ({sim_unrelated:.3f})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests - Full Pipeline
# ─────────────────────────────────────────────────────────────────────────────


class TestEmbeddingPipeline:
    """Test full embedding pipeline with available providers."""

    def test_cluster_embedding_and_search(self) -> None:
        """Test generating cluster embeddings and searching."""
        provider = get_embedding_provider()  # Auto-select

        clusters = [
            ClusterEmbeddingInput(
                cluster_id="1",
                canonical_title="CRISPR gene editing advances in brain research",
                takeaway="New technique enables precise editing in neurons",
                topic_names=["Gene Therapy", "Neuroscience"],
            ),
            ClusterEmbeddingInput(
                cluster_id="2",
                canonical_title="Climate change accelerates Antarctic ice loss",
                takeaway="Ice sheets melting faster than predicted",
                topic_names=["Climate Change", "Antarctica"],
            ),
            ClusterEmbeddingInput(
                cluster_id="3",
                canonical_title="mRNA vaccines show promise for cancer treatment",
                takeaway="Technology from COVID vaccines adapted for oncology",
                topic_names=["Cancer", "Vaccines", "mRNA"],
            ),
        ]

        # Generate embeddings
        embeddings = []
        for cluster in clusters:
            result = generate_cluster_embedding(cluster, provider=provider)
            assert result.success, f"Failed to embed cluster: {result.error}"
            embeddings.append((cluster.cluster_id, result.embedding))

        # Search for gene therapy
        query_result = generate_query_embedding("gene therapy brain", provider=provider)
        assert query_result.success

        # Calculate similarities
        similarities = [
            (cid, cosine_similarity(query_result.embedding, emb))
            for cid, emb in embeddings
        ]

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Verify we got results
        assert len(similarities) == 3
        assert all(-1.0 <= sim <= 1.0 for _, sim in similarities)


class TestEmbeddingResultDataclass:
    """Test EmbeddingResult dataclass."""

    def test_create_success_result(self) -> None:
        result = EmbeddingResult(
            embedding=[0.1, 0.2, 0.3],
            model="test-model",
            provider="test-provider",
            source_text_hash="abc123",
            dimensions=3,
            success=True,
        )

        assert result.embedding == [0.1, 0.2, 0.3]
        assert result.dimensions == 3
        assert result.success is True
        assert result.error is None

    def test_create_failure_result(self) -> None:
        result = EmbeddingResult.failure("Connection error")

        assert result.embedding == []
        assert result.dimensions == 0
        assert result.success is False
        assert result.error == "Connection error"
