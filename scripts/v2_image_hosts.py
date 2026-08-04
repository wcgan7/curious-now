"""Image hosts the corpus uses, and whether the reader is allowed to fetch them.

Next resizes and caches every picture the reader shows, which means it will only
fetch from hosts named in apps/reader/next.config.ts. That list is explicit on
purpose — a wildcard would make the reader an image proxy for anyone who found
the URL — and the cost of being explicit is that it goes stale silently: a new
source's pictures simply fail to load, and a card with no picture is what 48% of
stories look like anyway, so nothing appears wrong.

Run this after adding a source. It prints what the corpus holds and what the
reader cannot reach.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import psycopg

CONFIG = Path(__file__).resolve().parent.parent / "apps/reader/next.config.ts"
URL = os.environ["CURIOUS_NOW_V2_DATABASE_URL"]

# The array literal, not the whole file: a hostname mentioned in the prose above
# it is a comment, not a permission.
block = re.search(r"const IMAGE_HOSTS = \[(.*?)\];", CONFIG.read_text(), re.S)
allowed = set(re.findall(r'"([^"]+)"', block.group(1))) if block else set()

with psycopg.connect(URL) as conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT i.image_url
        FROM stories s
        JOIN story_items si ON si.story_id = s.id
        JOIN items i ON i.id = si.item_id
        WHERE s.status = 'published' AND i.image_url IS NOT NULL
        UNION ALL
        SELECT f->>'image_url'
        FROM stories s
        JOIN story_items si ON si.story_id = s.id
        JOIN items i ON i.id = si.item_id,
          LATERAL jsonb_array_elements(
            COALESCE(i.text_structure->'figures', '[]'::jsonb)
          ) f
        WHERE s.status = 'published' AND f->>'image_url' IS NOT NULL;
        """
    )
    hosts = Counter(urlparse(url).netloc for (url,) in cur.fetchall() if url)

print(f"{sum(hosts.values())} images across {len(hosts)} hosts\n")
for host, count in hosts.most_common():
    print(f"  {'ok ' if host in allowed else 'NOT ALLOWED'}  {count:6d}  {host}")

missing = {host: n for host, n in hosts.items() if host not in allowed}
if missing:
    print(f"\nAdd to IMAGE_HOSTS in {CONFIG.relative_to(CONFIG.parents[2])}:")
    for host in sorted(missing, key=lambda h: -missing[h]):
        print(f'  "{host}",')

unused = allowed - set(hosts)
if unused:
    # Not an error. A host can be listed before its source ships, and a source
    # can stop syndicating pictures without anything going wrong.
    print("\nallowed but unused: " + ", ".join(sorted(unused)))
