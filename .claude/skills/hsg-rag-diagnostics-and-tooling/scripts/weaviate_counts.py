"""Object counts per Weaviate collection + embax.ch share.

Usage (from repo root, with the repo venv — it has weaviate-client installed):

    venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/weaviate_counts.py

Reads WEAVIATE_CLUSTER_URL / WEAVIATE_API_KEY from the repo-root .env.

Expected shape (baseline 2026-07-07): hsg_rag_content_de=227, hsg_rag_content_en=144,
embax.ch objects: 12 in EN, 0 in DE. Zero embax objects in DE is PLAUSIBLE, not a bug:
embax.ch is an English-only site; German emba-X content enters the DE collection via
emba.unisg.ch articles instead. Alarm signs: a collection at 0, or EN << 100 (EN/embax
underrepresented after a re-import).
"""
import os
import sys
from pathlib import Path

# scripts/ -> skill dir -> skills/ -> .claude/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]

from dotenv import load_dotenv

# Explicit path: load_dotenv() without arguments walks the caller's frames and
# crashes with AssertionError when run through a heredoc / -c one-liner.
load_dotenv(REPO_ROOT / ".env")

import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=os.environ["WEAVIATE_CLUSTER_URL"],
    auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
)
try:
    ok = True
    for name in ("hsg_rag_content_de", "hsg_rag_content_en"):
        coll = client.collections.get(name)
        total = coll.aggregate.over_all(total_count=True).total_count
        embax = coll.aggregate.over_all(
            total_count=True,
            filters=Filter.by_property("source").like("*embax.ch*"),
        ).total_count
        print(f"{name}: {total} objects ({embax} from embax.ch)")
        if not total:
            ok = False
        # two sample sources so a human can eyeball provenance
        for obj in coll.query.fetch_objects(limit=2).objects:
            print(f"   sample source: {str(obj.properties.get('source', ''))[:80]}")
    sys.exit(0 if ok else 1)
finally:
    client.close()
