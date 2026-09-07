from __future__ import annotations

from curious_now_v2.core.enums import ExplanationDepth
from curious_now_v2.pipeline.story_gate import ItemText, gate_story
from curious_now_v2.retrieval.extract_article import extract_article
from curious_now_v2.retrieval.extract_arxiv import extract_arxiv_html
from tests.fixtures.loader import fixture_text


def article_item(name: str, **kwargs: object) -> ItemText:
    document = extract_article(fixture_text(name))
    defaults: dict[str, object] = {
        "source_name": name,
        "text": document.text,
        "has_structure": document.has_structure,
    }
    defaults.update(kwargs)
    return ItemText(**defaults)  # type: ignore[arg-type]


def paper_item(name: str = "arxiv_latexml_html") -> ItemText:
    document = extract_arxiv_html(fixture_text(name))
    return ItemText(
        source_name="arXiv",
        text=document.text,
        has_structure=document.has_structure,
        is_primary_material=True,
    )


def test_a_story_with_no_text_is_withheld() -> None:
    gate = gate_story((ItemText(source_name="Nature", text=""),))

    assert gate.publishable is False
    assert gate.supported_depths == ()
    assert "no item yielded any text" in gate.reasons


def test_a_story_whose_only_source_is_walled_is_withheld() -> None:
    gate = gate_story((article_item("statnews_html"),))

    assert gate.publishable is False
    assert any("paywall" in reason for reason in gate.reasons)


def test_retrieval_gate_only_decides_that_a_paper_is_an_article() -> None:
    gate = gate_story((paper_item(),))

    assert gate.publishable is True
    assert gate.supported_depths == (ExplanationDepth.GLANCE,)


def test_journalism_never_reaches_technical_however_well_written() -> None:
    """Technical inspects the work itself, so it needs primary material rather
    than coverage of it."""

    gate = gate_story((article_item("quanta_news_html"),))

    assert gate.publishable is True
    assert ExplanationDepth.TECHNICAL not in gate.supported_depths


def test_a_short_article_publishes_with_glance_alone() -> None:
    gate = gate_story((article_item("bbc_news_html"),))

    assert gate.publishable is True
    assert gate.supported_depths == (ExplanationDepth.GLANCE,)


def test_the_richest_item_grounds_the_story() -> None:
    gate = gate_story(
        (
            article_item("bbc_news_html"),
            article_item("microsoft_research_blog_html"),
        )
    )

    assert gate.grounding_source == "microsoft_research_blog_html"
    assert gate.supported_depths == (ExplanationDepth.GLANCE,)


def test_thin_items_are_not_added_together() -> None:
    """Two short articles do not add up to a mechanism, and the thresholds
    were calibrated against whole documents."""

    short = article_item("bbc_news_html")
    gate = gate_story((short, short, short, short))

    assert gate.supported_depths == (ExplanationDepth.GLANCE,)


def test_a_walled_source_alongside_a_usable_one_still_publishes() -> None:
    """The paywalled item stays as evidence; it just cannot ground anything."""

    gate = gate_story(
        (article_item("statnews_html"), article_item("quanta_news_html"))
    )

    assert gate.publishable is True
    assert gate.grounding_source == "quanta_news_html"
    assert any("paywall" in reason for reason in gate.reasons)


def test_corroboration_is_recorded() -> None:
    gate = gate_story(
        (article_item("quanta_news_html"), article_item("sciencenews_html"))
    )

    assert any("2 items carry usable text" in reason for reason in gate.reasons)


def test_reasons_name_the_grounding_source_and_its_length() -> None:
    """Withholding has to be explainable, or an operator cannot tell a
    retrieval gap from a source that simply says little."""

    gate = gate_story((paper_item(),))

    assert gate.reasons
    assert "arXiv" in gate.reasons[0]
    assert "words" in gate.reasons[0]
