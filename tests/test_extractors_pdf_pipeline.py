from __future__ import annotations

import httpx

from curious_now.extractors import paper_sources as ps


def test_reflow_pdf_lines_merges_wrapped_and_hyphenated_lines() -> None:
    raw = """
This is a long para that wraps at the end of a line and
continues on the next line.
Molecu-
lar absorption is observed.

2 Introduction
""".strip()
    out = ps._reflow_pdf_lines(raw)
    assert "line and continues" in out
    assert "Molecular absorption" in out
    assert "2 Introduction" in out


def test_reflow_pdf_lines_keeps_compound_hyphen() -> None:
    raw = "high signal-to-\nnoise ratio is observed."
    out = ps._reflow_pdf_lines(raw)
    assert "signal-to-noise" in out


def test_reflow_pdf_lines_merges_keyword_wrap() -> None:
    raw = "Keywords: Active galactic nuclei, Little Red\nDots, Molecular absorption"
    out = ps._reflow_pdf_lines(raw)
    assert "Little Red Dots, Molecular absorption" in out


def test_reflow_pdf_lines_merges_across_single_blank_gap() -> None:
    raw = "We impose a redshift 2\n\n5 per pixel cut for stability."
    out = ps._reflow_pdf_lines(raw)
    assert "redshift 2 5 per pixel cut" in out


def test_trim_pdf_frontmatter_starts_at_abstract_and_keeps_title() -> None:
    raw = """
Water absorption confirms cool atmospheres in two little red dots
Department of Astrophysical Sciences, Princeton University
someone@uni.edu
Abstract
We report key findings.
Methods follow.
""".strip()
    out = ps._trim_pdf_frontmatter(raw)
    assert out.startswith("Water absorption confirms cool atmospheres")
    assert "Department of Astrophysical Sciences" not in out
    assert "someone@uni.edu" not in out
    assert "Abstract" in out


def test_postprocess_pdf_text_collapses_excess_blank_lines() -> None:
    raw = "Title\n\n\n\nAbstract\nBody"
    out = ps._postprocess_pdf_text(raw)
    assert "\n\n\n" not in out


def test_filter_pdf_noise_lines_removes_numeric_axis_noise() -> None:
    raw = "2.5 2.5 0.0 0.0 -2.5 -2.5\nClean sentence here."
    out = ps._filter_pdf_noise_lines(raw)
    assert "2.5 2.5" not in out
    assert "Clean sentence here." in out


def test_filter_pdf_noise_lines_removes_figure_legend_artifacts() -> None:
    raw = (
        "2.5 2.5 a)WIDE-EGS-2974 Blackbody fit\n"
        "a)\n"
        "H2O H2O 1.0 1.0 value band\n"
        "Valid body sentence remains."
    )
    out = ps._filter_pdf_noise_lines(raw)
    assert "2.5 2.5 a)" not in out
    assert "a)" not in out
    assert "Valid body sentence remains." in out


def test_filter_pdf_noise_lines_removes_axis_tick_fragments() -> None:
    raw = "-2.5\nA]\nClean line"
    out = ps._filter_pdf_noise_lines(raw)
    assert "-2.5" not in out
    assert "A]" not in out
    assert "Clean line" in out


def test_filter_pdf_noise_lines_removes_figure_caption_and_panel_labels() -> None:
    raw = (
        "Fig. 1: Detection of water absorption.\n"
        "a)\n"
        "Narrative sentence with (Fig. 1) should stay."
    )
    out = ps._filter_pdf_noise_lines(raw)
    assert "Fig. 1:" not in out
    assert "a)" not in out
    assert "Narrative sentence with (Fig. 1) should stay." in out


def test_filter_pdf_noise_lines_removes_legend_token_soup() -> None:
    raw = (
        "No water absorption 2.5 a)WIDE-EGS-2974 M Dwarf (T ≈1760K) "
        "T = 4000K b)Water absorption strength 0.0 T = 3000K\n"
        "Narrative sentence remains."
    )
    out = ps._filter_pdf_noise_lines(raw)
    assert "No water absorption 2.5 a)" not in out
    assert "Narrative sentence remains." in out


def test_filter_pdf_noise_lines_removes_axis_label_unit_rows() -> None:
    raw = "lambda_rest [A]\nClean narrative sentence."
    out = ps._filter_pdf_noise_lines(raw)
    assert "lambda_rest [A]" not in out
    assert "Clean narrative sentence." in out


def test_repair_pdf_broken_numeric_fragments_merges_comparator_split() -> None:
    raw = (
        "The threshold is <\n"
        "5 in this run.\n"
        "Next sentence."
    )
    out = ps._repair_pdf_broken_numeric_fragments(raw)
    assert "threshold is < 5 in this run." in out
    assert "Next sentence." in out


def test_repair_pdf_broken_numeric_fragments_keeps_regular_text() -> None:
    raw = "Regular line one.\nRegular line two."
    out = ps._repair_pdf_broken_numeric_fragments(raw)
    assert out == raw


def test_serialize_pdf_table_rows_outputs_pipe_table() -> None:
    rows = [["Round", "Outcome"], ["1", "Edge Created (B→A)"], ["2", "Score: 0.77"]]
    out = ps._serialize_pdf_table_rows(rows)
    assert out is not None
    assert "Round | Outcome" in out
    assert "--- | ---" in out
    assert "1 | Edge Created (B→A)" in out


def test_serialize_pdf_table_rows_repairs_hyphenated_cell_wrap() -> None:
    rows = [["Query", "Key"], ["I need imple- mentation details", "Provide test suite"]]
    out = ps._serialize_pdf_table_rows(rows)
    assert out is not None
    assert "implementation details" in out
    assert "imple- mentation" not in out


def test_serialize_pdf_table_rows_drops_sparse_noise_tables() -> None:
    rows = [["", "", "A"], ["", "", ""], ["", "", ""]]
    out = ps._serialize_pdf_table_rows(rows)
    assert out is None


def test_serialize_pdf_table_rows_rejects_fragmented_split_cells() -> None:
    rows = [
        ["c1", "c2", "c3", "c4", "c5", "c6"],
        ["sag", "esonlyalo", "ngtheac", "tivatedlin", "ks", "system"],
        ["alpha", "betaword", "gammaword", "deltaword", "epsilon", "zeta"],
    ]
    out = ps._serialize_pdf_table_rows(rows)
    assert out is None


def test_page_text_from_blocks_uses_column_order_when_clearly_two_column() -> None:
    blocks = [
        (40.0, 10.0, 250.0, 20.0, "L1"),
        (320.0, 10.0, 520.0, 20.0, "R1"),
        (40.0, 30.0, 250.0, 40.0, "L2"),
        (320.0, 30.0, 520.0, 40.0, "R2"),
        (40.0, 50.0, 250.0, 60.0, "L3"),
        (320.0, 50.0, 520.0, 60.0, "R3"),
    ]
    out = ps._page_text_from_blocks(blocks, page_width=560.0)
    assert out.splitlines()[:3] == ["L1", "L2", "L3"]
    assert out.splitlines()[-3:] == ["R1", "R2", "R3"]


def test_fetch_pdf_text_invokes_rejected_callback() -> None:
    called: list[str] = []

    def _mock_get(_url: str) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.4 mock",
            headers={"content-type": "application/pdf"},
        )

    out = ps.fetch_pdf_text(
        "https://example.org/paper.pdf",
        http_get=_mock_get,
        extract_pdf_text_fn=lambda _bytes: "noisy extracted text",
        is_fulltext_quality_sufficient=lambda _text: False,
        on_quality_rejected=lambda text: called.append(text),
    )
    assert out is None
    assert called == ["noisy extracted text"]
