"""What the corpus actually holds, by field.

These numbers used to sit beside every field in the reader's drawer, on the
argument that a count keeps a list honest — a field holding ten stories says so
before anyone picks it. That is true of a control you meet once and wrong for
one you use repeatedly, where it is nine numbers a reader never asked for.

But the numbers are worth having, because they answer questions that come up
constantly while building this: whether a field is thin enough to be a dead end,
whether a leaf has grown enough to deserve promoting to the top level, and
whether the classifier is filing anything at all under the categories we added
for it. So they live here.

Reads the same taxonomy the generator and the reader read, so a leaf can never
be counted under a group it is not in.
"""

from __future__ import annotations

import os

import psycopg

from curious_now_v2.core.fields import leaf, taxonomy

URL = os.environ["CURIOUS_NOW_V2_DATABASE_URL"]

with psycopg.connect(URL) as conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT field, count(*)
        FROM stories
        WHERE status = 'published'
        GROUP BY field;
        """
    )
    per_leaf = {slug: n for slug, n in cur.fetchall()}
    cur.execute("SELECT count(*) FROM stories WHERE status = 'published';")
    total = cur.fetchone()[0]

unfiled = per_leaf.pop(None, 0)
filed = sum(per_leaf.values())

print(f"{total} published stories, {filed} filed ({100 * filed // max(total, 1)}%)\n")

# The bar a leaf would have to clear to be worth offering on its own. Not
# enforced anywhere — promoting a leaf changes what the group above it means,
# which is a decision to take rather than a threshold to trip.
WORTH_SPLITTING = 15

for group in taxonomy():
    held = sum(per_leaf.get(entry.slug, 0) for entry in group.leaves)
    bar = "#" * round(40 * held / max(total, 1))
    print(f"{held:5d}  {group.label:24s} {bar}")
    for entry in group.leaves:
        n = per_leaf.get(entry.slug, 0)
        mark = " <- worth splitting out" if n >= WORTH_SPLITTING else ""
        print(f"       {n:5d}  {entry.label}{mark}")
    print()

if unfiled:
    print(f"{unfiled} carry no field: the classifier could not establish one.")

strays = {slug: n for slug, n in per_leaf.items() if slug and not leaf(slug)}
if strays:
    # A leaf the taxonomy no longer names. Renaming a slug orphans every story
    # already tagged with it, which is why slugs are identifiers and labels are
    # the thing that gets reworded.
    print("\nstored under slugs the taxonomy no longer names:")
    for slug, n in sorted(strays.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {slug}")
