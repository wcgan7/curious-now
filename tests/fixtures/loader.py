from __future__ import annotations

import gzip
import json
from functools import cache
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "retrieval"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
CAPTURED_PATH = FIXTURE_DIR / "captured.json"

_EXTENSIONS = {"pdf": "pdf", "jats_xml": "xml"}


@cache
def manifest() -> dict[str, dict[str, str]]:
    """Fixture specs keyed by name."""

    data = json.loads(MANIFEST_PATH.read_text())
    return {entry["name"]: entry for entry in data["fixtures"]}


@cache
def captured() -> dict[str, dict[str, object]]:
    """Provenance for fixtures present on disk."""

    if not CAPTURED_PATH.exists():
        return {}
    return json.loads(CAPTURED_PATH.read_text())


def fixture_path(name: str) -> Path:
    spec = manifest()[name]
    return FIXTURE_DIR / f"{name}.{_EXTENSIONS.get(spec['kind'], 'html')}.gz"


def fixture_bytes(name: str) -> bytes:
    """Return one captured document, decompressed."""

    path = fixture_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"fixture {name!r} is missing; run scripts/v2_capture_fixtures.py"
        )
    return gzip.decompress(path.read_bytes())


def fixture_text(name: str, encoding: str = "utf-8") -> str:
    return fixture_bytes(name).decode(encoding, errors="replace")


def fixtures_of_kind(*kinds: str) -> tuple[str, ...]:
    """Fixture names for the given kinds, for parametrized tests."""

    wanted = set(kinds)
    return tuple(
        sorted(
            name
            for name, spec in manifest().items()
            if spec["kind"] in wanted and fixture_path(name).exists()
        )
    )
