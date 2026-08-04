"""The field taxonomy, loaded from the file the reader also reads.

A story is tagged with a leaf. Groups exist for display only, so promoting
mathematics to the top level once there is enough of it -- or merging AI back
into computer science -- is an edit to config/v2/fields.json with no re-tagging
and no migration.

Nothing here derives a group from a leaf's name or vice versa: the mapping is
data, and the only reason to hold it in code would be to let the two runtimes
disagree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "config" / "v2" / "fields.json"


@dataclass(frozen=True)
class Leaf:
    slug: str
    label: str
    group_slug: str
    group_label: str


@dataclass(frozen=True)
class Group:
    slug: str
    label: str
    note: str
    leaves: tuple[Leaf, ...]


@lru_cache(maxsize=1)
def taxonomy() -> tuple[Group, ...]:
    payload = json.loads(CONFIG.read_text())
    groups: list[Group] = []
    for raw in payload["groups"]:
        leaves = tuple(
            Leaf(
                slug=leaf["slug"],
                label=leaf["label"],
                group_slug=raw["slug"],
                group_label=raw["label"],
            )
            for leaf in raw["leaves"]
        )
        groups.append(
            Group(
                slug=raw["slug"],
                label=raw["label"],
                note=raw["note"],
                leaves=leaves,
            )
        )
    return tuple(groups)


@lru_cache(maxsize=1)
def leaves() -> tuple[Leaf, ...]:
    return tuple(leaf for group in taxonomy() for leaf in group.leaves)


@lru_cache(maxsize=1)
def leaf_slugs() -> tuple[str, ...]:
    """Every leaf, in taxonomy order. This is the model's enum."""

    return tuple(leaf.slug for leaf in leaves())


@lru_cache(maxsize=1)
def _by_slug() -> dict[str, Leaf]:
    return {leaf.slug: leaf for leaf in leaves()}


def leaf(slug: str | None) -> Leaf | None:
    """The leaf a slug names, or None.

    None rather than a fallback: a story whose field we could not establish
    should carry nothing, so that "we did not look" and "we looked and it is
    chemistry" stay distinguishable. Guessing here would put a physics story in
    front of someone who asked for medicine.
    """

    return _by_slug().get(slug) if slug else None


def group_of(slug: str | None) -> str | None:
    entry = leaf(slug)
    return entry.group_slug if entry else None


def describe_for_prompt() -> str:
    """The leaf list as the model sees it, grouped so the shape is legible.

    Rendered from the same data the enum comes from, so a leaf can never be
    offered in the schema and missing from the instructions.
    """

    lines: list[str] = []
    for group in taxonomy():
        lines.append(f"  {group.label} — {group.note}")
        for entry in group.leaves:
            lines.append(f"      {entry.slug:24s} {entry.label}")
    return "\n".join(lines)
