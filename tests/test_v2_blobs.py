from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from curious_now_v2.core import blobs


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "blobs"


def test_a_body_round_trips(root: Path) -> None:
    body = b"<html><body>the raw page</body></html>" * 40

    stored = blobs.put(body, root=root)

    assert stored.written
    assert blobs.get(stored.digest, root=root) == body


def test_identical_bodies_are_stored_once(root: Path) -> None:
    """Retrieval fetches the same article under two candidate names.

    publisher_html and article_html came back byte-identical at 231,143 bytes
    in this corpus; content addressing makes that one file rather than two.
    """

    body = b"identical bytes from two candidates" * 100

    first = blobs.put(body, root=root)
    second = blobs.put(body, root=root)

    assert first.path == second.path
    assert first.written and not second.written
    assert len(list(root.rglob("*.gz"))) == 1


def test_different_bodies_do_not_collide(root: Path) -> None:
    one = blobs.put(b"first body, long enough to be real" * 50, root=root)
    two = blobs.put(b"second body, long enough to be real" * 50, root=root)

    assert one.digest != two.digest
    assert len(list(root.rglob("*.gz"))) == 2


def test_markup_compresses_substantially(root: Path) -> None:
    body = (b"<p class='ltx_p'>repeated markup of the kind arXiv emits</p>") * 500

    stored = blobs.put(body, root=root)

    assert stored.ratio > 5


def test_a_missing_blob_reads_as_absent_rather_than_raising(root: Path) -> None:
    """The store is on a disk the database does not control.

    A missing body means "this needs fetching again", which the pipeline can
    act on; an exception would take down a run for a recoverable condition.
    """

    assert blobs.get("a" * 64, root=root) is None
    assert not blobs.exists("a" * 64, root=root)


def test_a_corrupt_blob_reads_as_absent(root: Path) -> None:
    stored = blobs.put(b"a body that will then be damaged" * 30, root=root)
    stored.path.write_bytes(b"not gzip at all")

    assert blobs.get(stored.digest, root=root) is None


def test_a_nonsense_digest_is_refused_not_guessed(root: Path) -> None:
    with pytest.raises(ValueError):
        blobs.path_for("../../etc/passwd", root=root)
    assert blobs.get("../../etc/passwd", root=root) is None


def test_paths_fan_out_so_no_directory_grows_unbounded(root: Path) -> None:
    digest = "ab" + "cd" + "e" * 60
    path = blobs.path_for(digest, root=root)

    assert path.relative_to(root).parts == ("ab", "cd", f"{digest}.gz")


def test_no_partial_file_is_left_behind(root: Path) -> None:
    blobs.put(b"a body written through a temporary name" * 20, root=root)

    assert not list(root.rglob("*.part"))


def test_the_same_bytes_always_produce_the_same_file(root: Path, tmp_path: Path) -> None:
    """Fixed mtime, so the store is reproducible and comparable."""

    body = b"deterministic output" * 200
    other = tmp_path / "second-root"

    first = blobs.put(body, root=root)
    second = blobs.put(body, root=other)

    assert first.path.read_bytes() == second.path.read_bytes()


def test_root_comes_from_the_environment_when_not_overridden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(blobs.ENV_VAR, str(tmp_path / "from-env"))

    assert blobs.blob_root() == tmp_path / "from-env"


def test_usability_is_reported_rather_than_discovered_mid_run(root: Path) -> None:
    ok, detail = blobs.usable(root)
    assert ok and str(root) in detail

    # A root that cannot be created — a file where the directory should be.
    blocked = root / "afile"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_bytes(b"x")
    ok, detail = blobs.usable(blocked / "under-a-file")
    assert not ok and "cannot" in detail


def test_stored_bytes_are_gzip(root: Path) -> None:
    body = b"plain body" * 100
    stored = blobs.put(body, root=root)

    assert gzip.decompress(stored.path.read_bytes()) == body
