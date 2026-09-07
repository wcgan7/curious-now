from __future__ import annotations

from curious_now_v2.db.images import merge_figure_images
from curious_now_v2.retrieval.document import Figure
from curious_now_v2.retrieval.extract_jats import extract_jats
from curious_now_v2.retrieval.images import extract_html_preview_image


def test_html_preview_uses_declared_article_image_and_resolves_relative_url() -> None:
    html = '<meta property="og:image" content="/media/story.jpg">'

    assert extract_html_preview_image(
        html, base_url="https://news.example/articles/one"
    ) == "https://news.example/media/story.jpg"


def test_html_preview_rejects_generic_publisher_logo() -> None:
    html = (
        '<meta property="og:image" '
        'content="https://www.medrxiv.org/images/medrxiv_logo.png">'
    )

    assert (
        extract_html_preview_image(
            html, base_url="https://www.medrxiv.org/content/paper"
        )
        is None
    )


def test_npr_preview_unwraps_its_source_owned_asset() -> None:
    html = (
        '<meta property="og:image" content="https://npr.brightspotcdn.com/'
        "dims3/default/resize/1400/format/jpeg/?url=http%3A%2F%2F"
        'npr-brightspot.s3.amazonaws.com%2F06%2F51%2Fstory.jpg">'
    )

    assert extract_html_preview_image(
        html, base_url="https://www.npr.org/2026/08/10/a-story"
    ) == "https://npr-brightspot.s3.amazonaws.com/06/51/story.jpg"


def test_npr_preview_does_not_unwrap_an_arbitrary_nested_host() -> None:
    html = (
        '<meta property="og:image" content="https://npr.brightspotcdn.com/'
        'dims3/?url=https%3A%2F%2Fevil.example%2Ftracking.jpg">'
    )

    assert (
        extract_html_preview_image(
            html, base_url="https://www.npr.org/2026/08/10/a-story"
        )
        is None
    )


def test_html_preview_rejects_a_known_unservable_publisher_host() -> None:
    html = (
        '<meta property="og:image" '
        'content="https://physics.aps.org/assets/story/thumb.png">'
    )

    assert (
        extract_html_preview_image(
            html, base_url="https://physics.aps.org/articles/v19/120"
        )
        is None
    )


def test_plos_jats_info_doi_becomes_figure_endpoint() -> None:
    document = extract_jats(
        """
        <article xmlns:xlink="http://www.w3.org/1999/xlink">
          <body><fig><label>Figure 1</label><caption><p>Outcome.</p></caption>
            <graphic xlink:href="info:doi/10.1371/journal.pmed.1005191.g001"/>
          </fig></body>
        </article>
        """,
        source="plos_jats",
        base_url=(
            "https://journals.plos.org/plosmedicine/article/file"
            "?id=10.1371/journal.pmed.1005191&amp;type=manuscript"
        ),
    )

    assert document.figures[0].image_url == (
        "https://journals.plos.org/plosmedicine/article/figure/image"
        "?id=10.1371/journal.pmed.1005191.g001&size=inline"
    )


def test_elife_jats_filename_becomes_iiif_image() -> None:
    document = extract_jats(
        """
        <article xmlns:xlink="http://www.w3.org/1999/xlink">
          <body><fig><label>Figure 1</label><caption><p>Cells.</p></caption>
            <graphic xlink:href="elife-109174-fig1-v1.tif"/>
          </fig></body>
        </article>
        """,
        source="elife_jats",
        base_url="https://elifesciences.org/articles/109174.xml",
    )

    assert document.figures[0].image_url == (
        "https://iiif.elifesciences.org/lax:109174/"
        "elife-109174-fig1-v1.tif/full/,1000/0/default.jpg"
    )


def test_merge_figure_images_matches_labels_before_position() -> None:
    structure = {
        "figures": [
            {"label": "Figure 2", "caption": "Second", "image_url": None},
            {"label": "Figure 1", "caption": "First", "image_url": None},
        ]
    }
    figures = (
        Figure("Figure 1", "First", "https://example.test/one.jpg"),
        Figure("Figure 2", "Second", "https://example.test/two.jpg"),
    )

    enriched, changed = merge_figure_images(structure, figures)

    assert changed == 2
    assert enriched["figures"][0]["image_url"].endswith("two.jpg")
    assert enriched["figures"][1]["image_url"].endswith("one.jpg")
    assert structure["figures"][0]["image_url"] is None
