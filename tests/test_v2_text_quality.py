from __future__ import annotations

import pytest
import trafilatura

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.retrieval.quality import (
    TextVerdict,
    assess_text,
)
from tests.fixtures.loader import fixture_text


def extract(name: str) -> str:
    return trafilatura.extract(fixture_text(name), favor_recall=True) or ""


# Verdicts below are asserted against real captured pages, not synthetic text.
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Nature serves 119 words of teaser plus a subscription pitch under 200.
        ("nature_article_html", TextVerdict.SOFT_PAYWALL),
        # STAT+ truncates mid-article behind a subscriber wall.
        ("statnews_html", TextVerdict.SOFT_PAYWALL),
        # A complete short news article, shorter than STAT's teaser.
        ("bbc_news_html", TextVerdict.USABLE),
        ("quanta_news_html", TextVerdict.USABLE),
        ("carbonbrief_html", TextVerdict.USABLE),
        ("google_research_blog_html", TextVerdict.USABLE),
        ("microsoft_research_blog_html", TextVerdict.USABLE),
        ("esa_press_html", TextVerdict.USABLE),
        ("nasa_press_html", TextVerdict.USABLE),
    ],
)
def test_real_pages_receive_the_right_verdict(
    name: str,
    expected: TextVerdict,
) -> None:
    assert assess_text(extract(name)).verdict is expected


def test_length_alone_cannot_separate_paywalls_from_short_articles() -> None:
    """A complete BBC article and a STAT teaser are within ~40 words of each
    other, so no length threshold separates them. The markers do that work."""

    bbc = assess_text(extract("bbc_news_html"))
    stat = assess_text(extract("statnews_html"))

    assert abs(bbc.words - stat.words) < 100
    assert bbc.verdict is TextVerdict.USABLE
    assert stat.verdict is TextVerdict.SOFT_PAYWALL


def test_short_usable_articles_support_only_glance() -> None:
    assessment = assess_text(extract("bbc_news_html"))

    assert assessment.supported_depths == (ExplanationDepth.GLANCE,)


def test_long_articles_do_not_guess_depth_from_length() -> None:
    assessment = assess_text(extract("microsoft_research_blog_html"))

    assert assessment.words > 600
    assert assessment.supported_depths == (ExplanationDepth.GLANCE,)


def test_structure_does_not_guess_technical_at_retrieval_time() -> None:
    body = " ".join(
        ["Introduction methods results discussion conclusion references"] * 400
    )

    without_structure = assess_text(body, has_structure=False)
    with_structure = assess_text(body, has_structure=True)

    assert without_structure.supported_depths == (ExplanationDepth.GLANCE,)
    assert with_structure.supported_depths == (ExplanationDepth.GLANCE,)


def test_an_article_discussing_subscriptions_is_not_a_paywall() -> None:
    """Commerce coverage legitimately quotes prices and subscription language."""

    body = (
        "Streaming services raised prices again this year. "
        "One service now charges $12.99 / month, and analysts said the "
        "subscribe now button converted poorly. "
    ) + " ".join(["Analysts examined the pricing data in detail."] * 200)

    assessment = assess_text(body)

    assert assessment.verdict is TextVerdict.USABLE


def test_empty_and_trivial_text_is_rejected() -> None:
    assert assess_text("").verdict is TextVerdict.TOO_SHORT
    assert assess_text("   \n  ").verdict is TextVerdict.TOO_SHORT
    assert assess_text("A short sentence.").verdict is TextVerdict.TOO_SHORT


def test_rejected_text_supports_no_depths() -> None:
    for name in ("nature_article_html", "statnews_html"):
        assert assess_text(extract(name)).supported_depths == ()
