from curious_now_v2 import __name__ as package_name
from scripts.v2_field_coverage import (
    Coverage,
    balance_warnings,
    coverage_failures,
    source_origin,
)


def test_topical_feeds_share_one_origin() -> None:
    assert source_origin("https://news.mit.edu/topic/robotics", "MIT Robotics") == (
        "news.mit.edu"
    )
    assert source_origin("https://news.mit.edu/topic/math", "MIT Mathematics") == (
        "news.mit.edu"
    )


def test_coverage_separates_missing_coverage_from_source_balance() -> None:
    coverage = Coverage(
        stories=8,
        origins=2,
        top_origin="example.test",
        top_share=0.75,
    )
    assert coverage_failures(
        coverage,
        min_stories=10,
        min_origins=3,
    ) == ("stories<10", "origins<3")
    assert balance_warnings(coverage, max_top_share=0.60) == ("top>60%",)


def test_a_large_diverse_field_is_covered_despite_a_balance_warning() -> None:
    coverage = Coverage(
        stories=387,
        origins=9,
        top_origin="arxiv.org",
        top_share=0.65,
    )
    assert coverage_failures(
        coverage,
        min_stories=10,
        min_origins=3,
    ) == ()
    assert balance_warnings(coverage, max_top_share=0.60) == ("top>60%",)


def test_package_is_importable_during_script_tests() -> None:
    assert package_name == "curious_now_v2"
