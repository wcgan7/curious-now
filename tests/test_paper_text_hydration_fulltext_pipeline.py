from __future__ import annotations

import io
import tarfile
from pathlib import Path

import httpx
import pytest

import curious_now.paper_text_hydration as pth


@pytest.mark.parametrize(
    "text,expected",
    [
        ("short text", False),
        (" ".join(["word"] * 450) + " introduction method", False),
        (
            " ".join(["word"] * 650)
            + " introduction methods results discussion references",
            True,
        ),
    ],
)
def test_fulltext_quality_gate(text: str, expected: bool) -> None:
    assert pth._is_fulltext_quality_sufficient(text) is expected


def test_fetch_landing_page_text_requires_open_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_get(_url: str, *, timeout_s: float = 12.0) -> httpx.Response:
        raise AssertionError("network should not be called when open_access_ok=False")

    monkeypatch.setattr(pth, "_http_get", _fail_get)
    text, status = pth._fetch_landing_page_text("https://example.org/paper", open_access_ok=False)
    assert text is None
    assert status == "not_found"


def test_extract_item_text_prefers_arxiv_html(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pth, "_fetch_arxiv_html_full_text", lambda _id: "full text from html")
    monkeypatch.setattr(pth, "_fetch_arxiv_pdf_full_text", lambda _id: "full text from pdf")
    monkeypatch.setattr(pth, "_fetch_arxiv_eprint_full_text", lambda _id: "full text from tex")
    monkeypatch.setattr(pth, "_fetch_arxiv_abstract", lambda _id: "abstract")

    text, status, source, kind, license_name = pth._extract_item_text(
        {"arxiv_id": "1234.56789", "doi": None, "url": None, "canonical_url": None}
    )
    assert text == "full text from html"
    assert status == "ok"
    assert source == "arxiv_html"
    assert kind == "fulltext"
    assert license_name == "arxiv"


def test_extract_item_text_chooses_higher_quality_pdf_over_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    low_html = "introduction methods " + ("word " * 450)
    high_pdf = "introduction methods results discussion references " + ("word " * 900)
    monkeypatch.setattr(pth, "_fetch_arxiv_html_full_text", lambda _id: low_html)
    monkeypatch.setattr(pth, "_fetch_arxiv_pdf_full_text", lambda _id: high_pdf)
    monkeypatch.setattr(pth, "_fetch_arxiv_eprint_full_text", lambda _id: None)
    monkeypatch.setattr(pth, "_fetch_arxiv_abstract", lambda _id: "abstract")

    text, status, source, kind, _license_name = pth._extract_item_text(
        {"arxiv_id": "1234.56789", "doi": None, "url": None, "canonical_url": None}
    )
    assert status == "ok"
    assert source == "arxiv_pdf"
    assert kind == "fulltext"
    assert text == high_pdf


def test_extract_item_text_uses_unpaywall_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pth,
        "_fetch_unpaywall_record",
        lambda _doi: {
            "is_oa": True,
            "best_oa_location": {
                "url_for_pdf": "https://oa.example.org/paper.pdf",
                "license": "cc-by",
            },
            "oa_locations": [],
        },
    )
    monkeypatch.setattr(pth, "_fetch_openalex_oa_candidates", lambda _doi: [])
    monkeypatch.setattr(pth, "_fetch_crossref_oa_candidates", lambda _doi: [])
    monkeypatch.setattr(pth, "_fetch_crossref_abstract", lambda _doi: None)
    monkeypatch.setattr(pth, "_fetch_openalex_abstract", lambda _doi: None)
    monkeypatch.setattr(
        pth,
        "_fetch_pdf_text",
        lambda url: "full doi text" if url.endswith("paper.pdf") else None,
    )

    text, status, source, kind, license_name = pth._extract_item_text(
        {
            "arxiv_id": None,
            "doi": "10.1234/example",
            "url": "https://publisher.example.org/article",
            "canonical_url": "https://publisher.example.org/article",
        }
    )
    assert text == "full doi text"
    assert status == "ok"
    assert source == "unpaywall_pdf"
    assert kind == "fulltext"
    assert license_name == "cc-by"


def test_extract_item_text_falls_back_to_abstract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pth, "_fetch_unpaywall_record", lambda _doi: None)
    monkeypatch.setattr(pth, "_fetch_openalex_oa_candidates", lambda _doi: [])
    monkeypatch.setattr(pth, "_fetch_crossref_oa_candidates", lambda _doi: [])
    monkeypatch.setattr(pth, "_fetch_crossref_abstract", lambda _doi: "crossref abstract")
    monkeypatch.setattr(pth, "_fetch_openalex_abstract", lambda _doi: None)

    text, status, source, kind, license_name = pth._extract_item_text(
        {
            "arxiv_id": None,
            "doi": "10.1234/example",
            "url": "https://publisher.example.org/article",
            "canonical_url": "https://publisher.example.org/article",
        }
    )
    assert text == "crossref abstract"
    assert status == "ok"
    assert source == "crossref"
    assert kind == "abstract"
    assert license_name is None


def test_fetch_arxiv_eprint_full_text_parses_tex(monkeypatch: pytest.MonkeyPatch) -> None:
    latex = r"""
    \section{Introduction}
    This paper studies a model with many details. % comment
    \section{Methods}
    We optimize the system and evaluate it across tasks.
    \section{Results}
    Results improve strongly over baseline in multiple settings.
    \section{Discussion}
    Discussion and conclusions are included.
    """
    latex = latex + (" filler" * 600)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = latex.encode("utf-8")
        info = tarfile.TarInfo(name="main.tex")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    def _mock_get(_url: str, *, timeout_s: float = 20.0) -> httpx.Response:
        return httpx.Response(200, content=buf.getvalue())

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    text = pth._fetch_arxiv_eprint_full_text("1234.56789")
    assert text is not None
    lower = text.lower()
    assert "introduction" in lower
    assert "results" in lower


def test_fetch_arxiv_html_full_text_parses_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (
        "<html><body><main><h1>Title</h1><h2>Introduction</h2>"
        + ("word " * 250)
        + "<h2>Methods</h2>"
        + ("word " * 250)
        + "<h2>Results</h2>"
        + ("word " * 250)
        + "<h2>Discussion</h2>"
        + ("word " * 250)
        + "<footer>footer text</footer>"
        + "<script>ignore me</script></main></body></html>"
    )

    def _mock_get(_url: str, *, timeout_s: float = 20.0) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    text = pth._fetch_arxiv_html_full_text("1234.56789")
    assert text is not None
    lower = text.lower()
    assert "introduction" in lower
    assert "methods" in lower
    assert "results" in lower
    assert "ignore me" not in lower


def test_fetch_arxiv_html_image_url_uses_og_image_and_resolves_relative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = """
    <html>
      <head>
        <meta property="og:image" content="/html/1234.56789v1/figures/hero.png" />
      </head>
      <body><main><p>Content</p></main></body>
    </html>
    """

    def _mock_get(_url: str, *, timeout_s: float = 20.0) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    image_url = pth._fetch_arxiv_html_image_url("1234.56789")
    assert image_url == "https://arxiv.org/html/1234.56789v1/figures/hero.png"


def test_fetch_arxiv_html_image_url_resolves_plain_relative_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = """
    <html>
      <body>
        <main>
          <figure><img src="x1.png" /></figure>
        </main>
      </body>
    </html>
    """

    def _mock_get(_url: str, *, timeout_s: float = 20.0) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    image_url = pth._fetch_arxiv_html_image_url("2602.12259v1")
    assert image_url == "https://arxiv.org/html/2602.12259v1/x1.png"


def test_fetch_arxiv_html_image_url_prefers_base_href_for_relative_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = """
    <html>
      <head>
        <base href="/html/2602.12259v1/" />
      </head>
      <body>
        <main>
          <figure><img src="x1.png" /></figure>
        </main>
      </body>
    </html>
    """

    def _mock_get(_url: str, *, timeout_s: float = 20.0) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    image_url = pth._fetch_arxiv_html_image_url("2602.12259")
    assert image_url == "https://arxiv.org/html/2602.12259v1/x1.png"


def test_clean_full_text_preserves_angle_bracket_math_in_plain_text() -> None:
    text = "We impose a redshift 2 < z < 3 and signal-to-noise > 5 per pixel."
    out = pth._clean_full_text(text)
    assert out is not None
    assert "2 < z < 3" in out
    assert "signal-to-noise > 5" in out


def test_extract_arxiv_html_body_text_prefers_tex_annotation_and_dedupes() -> None:
    raw_html = """
    <html><body><main>
      <div class="ltx_para">
        <p>
          We formalize as
          <math alttext="G(t)">
            <semantics>
              <mrow><mi>G</mi></mrow>
              <annotation encoding="application/x-tex">\\mathcal{G}=\\{G^{(t)}\\}_{t=0}^{T-1}</annotation>
            </semantics>
          </math>
          and proceed.
        </p>
      </div>
      <p>
          We formalize as
          <math alttext="G(t)">
            <semantics>
              <mrow><mi>G</mi></mrow>
              <annotation encoding="application/x-tex">\\mathcal{G}=\\{G^{(t)}\\}_{t=0}^{T-1}</annotation>
            </semantics>
          </math>
          and proceed.
      </p>
    </main></body></html>
    """
    text = pth._extract_arxiv_html_body_text(raw_html)
    assert text is not None
    assert text.count("\\mathcal{G}=\\{G^{(t)}\\}_{t=0}^{T-1}") == 1
    assert "<math" not in text
    assert "semantics" not in text.lower()


def test_extract_arxiv_html_body_text_serializes_table_rows() -> None:
    raw_html = """
    <html><body><main>
      <figure class="ltx_table" id="T1">
        <figcaption>Table 1: Example outcomes.</figcaption>
        <table class="ltx_tabular">
          <tr><th>Round</th><th>Outcome</th></tr>
          <tr><td>1</td><td>Edge Created (B\\to A)</td></tr>
          <tr><td>2</td><td>Score: 0.77 (High)</td></tr>
        </table>
      </figure>
    </main></body></html>
    """
    text = pth._extract_arxiv_html_body_text(raw_html)
    assert text is not None
    assert "Table 1: Example outcomes." in text
    assert "\nRound | Outcome\n" in text
    assert "\n--- | ---\n" in text
    assert "\n1 | Edge Created (B→ A)\n" in text or "\n1 | Edge Created (B→A)\n" in text
    assert "\n2 | Score: 0.77 (High)" in text


def test_extract_arxiv_html_body_text_removes_keywords_block() -> None:
    raw_html = """
    <html><body><main>
      <div class="ltx_keywords">Machine Learning, ICML</div>
      <p>Actual content paragraph.</p>
    </main></body></html>
    """
    text = pth._extract_arxiv_html_body_text(raw_html)
    assert text is not None
    assert "Actual content paragraph." in text
    assert "Machine Learning, ICML" not in text


def test_extract_arxiv_html_body_text_trims_affiliation_frontmatter() -> None:
    raw_html = """
    <html><body><main>
      <p>Water absorption confirms cool atmospheres in two little red dots</p>
      <p>[1] Department of Astrophysical Sciences, Princeton University</p>
      <p>[2] Center for Computational Astrophysics</p>
      <p>[3] Institute of Physics, Example University</p>
      <p>someone@example.edu</p>
      <h2>Abstract</h2>
      <p>Little red dots are abundant compact sources...</p>
    </main></body></html>
    """
    text = pth._extract_arxiv_html_body_text(raw_html)
    assert text is not None
    assert text.startswith("Water absorption confirms cool atmospheres in two little red dots")
    assert "Department of Astrophysical Sciences" not in text
    assert "someone@example.edu" not in text
    assert "Abstract" in text


def test_fetch_pdf_text_extracts_structured_content(monkeypatch: pytest.MonkeyPatch) -> None:
    fitz = pytest.importorskip("fitz")

    doc = fitz.open()
    for idx in range(3):
        page = doc.new_page()
        page_text = (
            "Introduction\n"
            "Methods\n"
            "Results\n"
            "Discussion\n"
            "References\n"
            + " ".join(["signal"] * 220)
            + f"\nEquation {idx}: x^2 + y^2 = z^2\n"
            "Table 1: A B C"
        )
        page.insert_textbox((40, 40, 550, 820), page_text, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()

    def _mock_get(_url: str, *, timeout_s: float = 20.0) -> httpx.Response:
        return httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    monkeypatch.setattr(pth, "_is_fulltext_quality_sufficient", lambda _text: True)
    text = pth._fetch_pdf_text("https://arxiv.org/pdf/1234.56789.pdf")
    assert text is not None
    assert "Introduction" in text
    assert "Equation" in text
    assert "Table 1" in text


def test_score_fulltext_quality_penalizes_structural_noise() -> None:
    clean = (
        "Abstract\n"
        + ("word " * 700)
        + "\nIntroduction\nMethods\nResults\nDiscussion\nReferences\n"
    )
    noisy = (
        clean
        + "\nA\nC\ni\nj\n"
        + "\n".join(["Table (PDF p.1.1)", "Averyveryveryveryverylonggluedtokenwithoutspaces"])
        + "\n"
        + ("|\n" * 20)
        + "\n"
        + "\x10\x11"
    )
    assert pth._score_fulltext_quality(clean) > pth._score_fulltext_quality(noisy)


def test_dump_rejected_pdf_text_for_debug_writes_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _Settings:
        paper_text_debug_dump_pdf_rejected = True
        paper_text_debug_dump_dir = str(tmp_path)

    monkeypatch.setattr(pth, "get_settings", lambda: _Settings())
    pth._dump_rejected_pdf_text_for_debug("https://example.org/p.pdf", "noisy text body")
    files = list(tmp_path.glob("pdf-rejected-*.txt"))
    assert len(files) == 1
    payload = files[0].read_text(encoding="utf-8")
    assert "reason: quality_rejected" in payload
    assert "url: https://example.org/p.pdf" in payload
    assert "noisy text body" in payload


def test_stitch_citation_lines_preserves_comma_and_year() -> None:
    lines = [
        "Early work shows improvements",
        "(",
        "Li",
        "et al.",
        ",",
        "2023",
        ")",
        ", while later work expands this",
    ]
    stitched = pth._stitch_citation_lines(lines)
    assert "(Li et al., 2023)" in stitched
    assert ", while later work expands this" in stitched


def test_stitch_citation_lines_merges_multi_cite_chain() -> None:
    lines = [
        "(",
        "Tran",
        "et al.,",
        "2025;",
        "Li",
        "et al.,",
        "2024",
        ")",
        ". More discussion follows.",
    ]
    stitched = pth._stitch_citation_lines(lines)
    assert "(Tran et al., 2025; Li et al., 2024)" in stitched
    assert ". More discussion follows." in stitched


def test_stitch_citation_lines_handles_mixed_year_author_chunk() -> None:
    lines = [
        "(",
        "Tran",
        "et al.,",
        "2025; Li",
        "et al.,",
        "2024",
        ")",
    ]
    stitched = pth._stitch_citation_lines(lines)
    assert stitched == ["(Tran et al., 2025; Li et al., 2024)"]


def test_stitch_citation_lines_preserves_tail_after_close() -> None:
    lines = [
        "Context before citation",
        "(",
        "Li",
        "et al.,",
        "2023) while extending prior setup",
        "Next line",
    ]
    stitched = pth._stitch_citation_lines(lines)
    assert "(Li et al., 2023)" in stitched
    assert "while extending prior setup" in stitched


def test_stitch_citation_lines_supports_numeric_brackets() -> None:
    lines = [
        "[",
        "12,",
        "14-16",
        "]",
    ]
    stitched = pth._stitch_citation_lines(lines)
    assert stitched == ["[12, 14-16]"]


def test_stitch_math_spill_lines_merges_equation_tokens() -> None:
    lines = [
        "The memory update rule is:",
        "H",
        "i",
        "(",
        "t",
        "+",
        "1",
        ")",
        "=",
        "H",
        "i",
        "(",
        "t",
        ")",
        ".",
        "(3)",
    ]
    stitched = pth._stitch_math_spill_lines(lines)
    assert any("H i (t+1)=H i (t).(3)" in line for line in stitched)


def test_stitch_math_spill_lines_ignores_plain_prose_tokens() -> None:
    lines = [
        "Introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "references",
    ]
    stitched = pth._stitch_math_spill_lines(lines)
    assert stitched == lines


def test_stitch_math_spill_lines_ignores_table_rows() -> None:
    lines = [
        "Round | Query | Outcome",
        "--- | --- | ---",
        "1 | Agent A asks | Edge Created (B\\to A)",
    ]
    stitched = pth._stitch_math_spill_lines(lines)
    assert stitched == lines


def test_dedupe_adjacent_semantic_repeats_keeps_bullet_once() -> None:
    lines = [
        "• Goal: Verify code against specific test cases.",
        "",
        "Goal: Verify code against specific test cases.",
    ]
    deduped = pth._dedupe_adjacent_semantic_repeats(lines)
    assert deduped == [lines[0], ""]


def test_drop_visual_legend_artifacts_filters_plot_residue() -> None:
    lines = [
        "2.5 2.5",
        "a)",
        "-2.5",
        "A]",
        "Valid narrative sentence remains here.",
    ]
    out = pth._drop_visual_legend_artifacts(lines)
    assert out == ["Valid narrative sentence remains here."]


def test_drop_visual_legend_artifacts_filters_legend_token_soup() -> None:
    lines = [
        "No water absorption 2.5 a)WIDE-EGS-2974 M Dwarf (T ≈1760K) T = 4000K b)Water absorption strength 0.0 T = 3000K",
        "Narrative sentence remains.",
    ]
    out = pth._drop_visual_legend_artifacts(lines)
    assert out == ["Narrative sentence remains."]


def test_normalize_inline_tex_tokens_converts_common_operators() -> None:
    text = r"Edge Created (B\to C), with T\leq T_{\max} and x\times y."
    normalized = pth._normalize_inline_tex_tokens(text)
    assert "B→C" in normalized
    assert "T≤T_{\\max}" in normalized
    assert "x×y" in normalized


def test_normalize_inline_tex_tokens_tightens_punctuation_spacing() -> None:
    text = "See (Tran et al. , 2025 ; Li et al. , 2024 ) ."
    normalized = pth._normalize_inline_tex_tokens(text)
    assert normalized == "See (Tran et al., 2025; Li et al., 2024)."


def test_merge_section_number_headings_handles_blank_gap() -> None:
    lines = [
        "1",
        "",
        "Introduction",
        "Text starts here.",
    ]
    merged = pth._merge_section_number_headings(lines)
    assert merged[0] == "1 Introduction"
    assert "Text starts here." in merged


def test_merge_section_number_headings_supports_unicode_title() -> None:
    lines = [
        "2",
        "Méthodes et Résultats",
        "Body.",
    ]
    merged = pth._merge_section_number_headings(lines)
    assert merged[0] == "2 Méthodes et Résultats"


def test_reflow_inline_fragments_does_not_merge_title_like_line() -> None:
    lines = [
        "This is a sufficiently long previous sentence for context in extraction.",
        "Background",
        "This is another sufficiently long sentence that follows in the paragraph.",
    ]
    reflowed = pth._reflow_inline_fragments(lines)
    assert reflowed == lines


def test_backfill_images_updates_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """backfill_images queries items, fetches images, and updates rows."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    item_id = uuid4()
    rows = [{"item_id": str(item_id), "arxiv_id": "2401.00001", "url": None, "canonical_url": None, "image_url": None}]

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [rows, []]  # arxiv pass, then empty landing pass
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    monkeypatch.setattr(
        pth,
        "_fetch_arxiv_html_image_url",
        lambda aid: "https://arxiv.org/html/2401.00001v1/fig1.png",
    )

    result = pth.backfill_images(mock_conn, limit=10)

    assert result.items_scanned == 1
    assert result.images_found == 1
    assert result.images_failed == 0
    assert result.items_skipped == 0

    # Verify the update was called with correct image URL and item_id
    update_calls = [
        c for c in mock_cursor.execute.call_args_list
        if "UPDATE items" in str(c)
    ]
    assert len(update_calls) == 1
    args = update_calls[0][0]
    assert "https://arxiv.org/html/2401.00001v1/fig1.png" in args[1]


def test_backfill_images_skips_when_no_image_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """backfill_images increments skipped when extractor returns None."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    item_id = uuid4()
    rows = [{"item_id": str(item_id), "arxiv_id": "2401.00002", "url": None, "canonical_url": None, "image_url": None}]

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [rows, []]  # arxiv pass, then empty landing pass
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    monkeypatch.setattr(pth, "_fetch_arxiv_html_image_url", lambda aid: None)

    result = pth.backfill_images(mock_conn, limit=10)

    assert result.items_scanned == 1
    assert result.images_found == 0
    assert result.items_skipped == 1


def test_backfill_images_handles_fetch_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """backfill_images increments failed on exception and continues."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    item_id = uuid4()
    rows = [{"item_id": str(item_id), "arxiv_id": "2401.00003", "url": None, "canonical_url": None, "image_url": None}]

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [rows, []]  # arxiv pass, then empty landing pass
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    def _fail(aid: str) -> str:
        raise ConnectionError("network down")

    monkeypatch.setattr(pth, "_fetch_arxiv_html_image_url", _fail)

    result = pth.backfill_images(mock_conn, limit=10)

    assert result.items_scanned == 1
    assert result.images_found == 0
    assert result.images_failed == 1


def test_drop_early_duplicate_lines_keeps_single_word_and_parenthetical_tokens() -> None:
    lines = [
        "DyTopo",
        "DyTopo",
        "(Zhang",
        "(Zhang",
        "et al.,",
    ]
    deduped = pth._drop_early_duplicate_lines(lines)
    assert deduped == lines


def test_fetch_landing_page_image_url_extracts_og_image(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch_landing_page_image_url extracts og:image from HTML responses."""
    html_body = """
    <html>
      <head>
        <meta property="og:image" content="https://example.com/hero.jpg" />
      </head>
      <body><main><p>Content</p></main></body>
    </html>
    """

    def _mock_get(_url: str, *, timeout_s: float = 12.0) -> httpx.Response:
        return httpx.Response(200, text=html_body, headers={"content-type": "text/html"})

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    monkeypatch.setattr(pth, "_DOMAIN_LAST_FETCH", {})
    image_url = pth._fetch_landing_page_image_url("https://example.com/article/1")
    assert image_url == "https://example.com/hero.jpg"


def test_fetch_landing_page_image_url_returns_none_for_non_html(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch_landing_page_image_url returns None when content is not HTML."""

    def _mock_get(_url: str, *, timeout_s: float = 12.0) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    monkeypatch.setattr(pth, "_http_get", _mock_get)
    monkeypatch.setattr(pth, "_DOMAIN_LAST_FETCH", {})
    assert pth._fetch_landing_page_image_url("https://example.com/paper.pdf") is None


def test_domain_throttle_sleeps_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """_throttle_domain sleeps when the same domain is hit within min_interval_s."""
    import time as _time

    sleep_calls: list[float] = []
    monkeypatch.setattr(_time, "sleep", lambda s: sleep_calls.append(s))

    # Simulate that the domain was fetched very recently (0.1s ago)
    pth._DOMAIN_LAST_FETCH.clear()
    now = _time.monotonic()
    pth._DOMAIN_LAST_FETCH["example.com"] = now

    pth._throttle_domain("https://example.com/page2", min_interval_s=2.0)

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


def test_domain_throttle_does_not_sleep_for_new_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """_throttle_domain does not sleep for a never-seen domain."""
    import time as _time

    sleep_calls: list[float] = []
    monkeypatch.setattr(_time, "sleep", lambda s: sleep_calls.append(s))

    pth._DOMAIN_LAST_FETCH.clear()
    pth._throttle_domain("https://brand-new-domain.org/page", min_interval_s=2.0)

    assert len(sleep_calls) == 0


def test_backfill_images_fetches_landing_page_for_non_arxiv(monkeypatch: pytest.MonkeyPatch) -> None:
    """backfill_images calls _fetch_landing_page_image_url for non-arXiv items."""
    from unittest.mock import MagicMock
    from uuid import uuid4

    arxiv_item_id = uuid4()
    landing_item_id = uuid4()

    arxiv_rows = [{"item_id": str(arxiv_item_id), "arxiv_id": "2401.00001", "url": None, "canonical_url": None, "image_url": None}]
    landing_rows = [{"item_id": str(landing_item_id), "arxiv_id": None, "url": "https://news.example.com/article", "canonical_url": "https://news.example.com/article", "image_url": None}]

    call_count = {"arxiv": 0, "landing_page": 0}

    def _mock_get_items(conn, *, limit, source="arxiv"):
        call_count[source] += 1
        if source == "arxiv":
            return arxiv_rows
        return landing_rows

    monkeypatch.setattr(pth, "_get_items_needing_image_backfill", _mock_get_items)
    monkeypatch.setattr(
        pth,
        "_fetch_arxiv_html_image_url",
        lambda aid: "https://arxiv.org/html/2401.00001v1/fig1.png",
    )
    monkeypatch.setattr(
        pth,
        "_fetch_landing_page_image_url",
        lambda url: "https://news.example.com/og-image.jpg",
    )

    update_calls: list[tuple] = []
    monkeypatch.setattr(
        pth,
        "_update_item_image",
        lambda conn, *, item_id, image_url: update_calls.append((item_id, image_url)),
    )

    mock_conn = MagicMock()
    result = pth.backfill_images(mock_conn, limit=10)

    assert call_count["arxiv"] == 1
    assert call_count["landing_page"] == 1
    assert result.items_scanned == 2
    assert result.images_found == 2
    assert len(update_calls) == 2
    assert update_calls[0] == (arxiv_item_id, "https://arxiv.org/html/2401.00001v1/fig1.png")
    assert update_calls[1] == (landing_item_id, "https://news.example.com/og-image.jpg")
