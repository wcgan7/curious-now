"""The field taxonomy is data, so its invariants have to be tested as data.

It lives in config/v2/fields.json because two runtimes read it -- the packet
prompt in Python and the reader in TypeScript -- and a taxonomy that drifts
between them would file a story under one field and show it under another. What
follows guards the properties a filter depends on, and the ones that broke a
previous version of this list.
"""

from __future__ import annotations

import json
from collections import Counter

from curious_now_v2.core.fields import (
    CONFIG,
    describe_for_prompt,
    group_of,
    leaf,
    leaf_slugs,
    leaves,
    taxonomy,
)
from curious_now_v2.generation.packet import SCHEMA


def test_every_leaf_belongs_to_exactly_one_group() -> None:
    """A story carries one leaf, so a leaf must imply one group. Two homes and
    the same story appears under two filters."""

    counts = Counter(entry.slug for entry in leaves())
    duplicates = [slug for slug, n in counts.items() if n > 1]
    assert not duplicates, f"leaves in more than one group: {duplicates}"


def test_no_group_is_empty() -> None:
    """v1 shipped thirteen categories of which five had nothing behind them.
    An empty group is a promise the corpus cannot keep."""

    for group in taxonomy():
        assert group.leaves, f"{group.slug} has no leaves"


def test_every_group_says_what_it_means() -> None:
    """The names alone leave real boundaries open -- life sciences against
    health, computing against physics -- and the note is where that is settled
    for a reader."""

    for group in taxonomy():
        assert len(group.note) > 10, f"{group.slug} has no useful note"


def test_slugs_are_stable_identifiers_not_labels() -> None:
    """Slugs go in the database and in URLs. A label can be reworded; a slug
    cannot, without orphaning every story already tagged with it."""

    for entry in leaves():
        assert entry.slug == entry.slug.lower()
        assert " " not in entry.slug
        assert entry.slug.replace("_", "").isalnum()


def test_the_prompt_offers_exactly_what_the_schema_accepts() -> None:
    """The model is shown a list and constrained to an enum. If they diverge it
    can be told about a field it cannot choose, or offered one it was never
    told the meaning of."""

    allowed = set(SCHEMA["properties"]["field"]["enum"])
    described = describe_for_prompt()
    assert allowed == set(leaf_slugs()) | {"unclear"}
    for slug in leaf_slugs():
        assert slug in described, f"{slug} is offered but never described"


def test_unclear_is_available_and_is_not_a_leaf() -> None:
    """"We could not establish one" has to be sayable, and has to stay
    distinguishable from any real answer -- a story filed by guesswork appears
    under a field its reader did not ask for."""

    assert "unclear" in SCHEMA["properties"]["field"]["enum"]
    assert leaf("unclear") is None
    assert group_of("unclear") is None


def test_an_unknown_slug_resolves_to_nothing_rather_than_a_default() -> None:
    assert leaf("phrenology") is None
    assert leaf(None) is None
    assert group_of(None) is None


def test_the_config_carries_a_version() -> None:
    """Regrouping is expected -- promoting mathematics once there is enough of
    it -- and a reader should be able to tell which shape it is looking at."""

    payload = json.loads(CONFIG.read_text())
    assert payload["version"]


def test_the_readers_copy_has_not_drifted() -> None:
    """The reader cannot import the canonical file, so it holds a copy.

    Next resolves neither a path outside the app root nor a symlink to one --
    the import type-checks and then fails to bundle, which is a 500 tsc cannot
    see. So the copy exists, and this is what stops it rotting: edit the config
    without running scripts/v2_sync_reader_fields.py and the suite says so,
    rather than the reader quietly showing labels for a taxonomy the generator
    no longer uses.
    """

    reader_copy = CONFIG.parents[2] / "apps" / "reader" / "lib" / "fields.json"
    assert reader_copy.exists(), f"{reader_copy} is missing"
    assert reader_copy.read_bytes() == CONFIG.read_bytes(), (
        "config/v2/fields.json and the reader's copy differ; "
        "run scripts/v2_sync_reader_fields.py"
    )
