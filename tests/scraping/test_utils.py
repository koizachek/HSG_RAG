import json
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.scraping.utils import load_set_dict


def test_load_set_dict_preserves_metadata_lists(tmp_path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    payload = {
        "https://example.com": [
            {
                "chunk_id": "chunk-1",
                "topic": "general",
            }
        ]
    }

    with open(metadata_dir / "raw_chunk_metadata.json", "w", encoding="utf-8") as f:
        json.dump(payload, f)

    loaded = load_set_dict(str(metadata_dir), "raw_chunk_metadata")

    assert isinstance(loaded["https://example.com"], list)
    assert loaded["https://example.com"][0]["chunk_id"] == "chunk-1"


def test_load_set_dict_restores_set_backed_values(tmp_path):
    urls_dir = tmp_path / "urls"
    urls_dir.mkdir()

    payload = {
        "high": ["https://example.com"],
    }

    with open(urls_dir / "url_priorities.json", "w", encoding="utf-8") as f:
        json.dump(payload, f)

    loaded = load_set_dict(str(urls_dir), "url_priorities")

    assert loaded["high"] == {"https://example.com"}
