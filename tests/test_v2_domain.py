from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from curious_now_v2.core.enums import (
    ClaimKind,
    ContentType,
    FeedKind,
    SourceRole,
)
from curious_now_v2.core.models import EvidenceClaim, EvidenceSupport
from curious_now_v2.core.source_registry import (
    FeedSpec,
    SourcePolicy,
    SourceRegistry,
    SourceSpec,
)


def test_claim_requires_at_least_one_supporting_item() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        EvidenceClaim(
            kind=ClaimKind.RESULT,
            text="The measured effect increased.",
            confidence=0.8,
            supports=(),
        )


def test_claim_cannot_cite_the_same_item_twice() -> None:
    item_id = uuid4()

    with pytest.raises(ValidationError, match="same item more than once"):
        EvidenceClaim(
            kind=ClaimKind.RESULT,
            text="The measured effect increased.",
            confidence=0.8,
            supports=(
                EvidenceSupport(item_id=item_id),
                EvidenceSupport(item_id=item_id, excerpt="Duplicate"),
            ),
        )


def test_discovery_source_cannot_masquerade_as_independent_evidence() -> None:
    with pytest.raises(ValidationError, match="cannot count as independent"):
        SourceSpec(
            name="Community links",
            role=SourceRole.DISCOVERY,
            feeds=(
                FeedSpec(
                    url="https://example.test/community.xml",
                    kind=FeedKind.RSS,
                    default_content_type=ContentType.NEWS,
                ),
            ),
            policy=SourcePolicy(counts_as_independent=True),
        )


def test_registry_rejects_a_feed_assigned_to_multiple_sources() -> None:
    shared_feed = FeedSpec(
        url="https://example.test/science.xml",
        default_content_type=ContentType.NEWS,
    )
    policy = SourcePolicy(counts_as_independent=True)

    with pytest.raises(ValidationError, match="unique across the registry"):
        SourceRegistry(
            version=1,
            sources=(
                SourceSpec(
                    name="Source A",
                    role=SourceRole.JOURNALISM,
                    feeds=(shared_feed,),
                    policy=policy,
                ),
                SourceSpec(
                    name="Source B",
                    role=SourceRole.INSTITUTIONAL,
                    feeds=(shared_feed,),
                    policy=policy,
                ),
            ),
        )
