"""Shared programme identifiers and normalization helpers."""

from __future__ import annotations

import re


PROGRAMME_IDS = ("emba", "iemba", "emba_x")


def normalize_programme_id(programme: str | None) -> str | None:
    """Normalize user/tool programme names to internal ids."""
    if not programme:
        return None

    text = str(programme).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)

    if text in {"emba_x", "embax", "emba_eth", "emba_eth_zurich"}:
        return "emba_x"
    if text in {"iemba", "iemba_hsg", "international_emba", "international_executive_mba"}:
        return "iemba"
    if text in {"emba", "emba_hsg", "executive_mba", "executive_mba_hsg"}:
        return "emba"
    return None


def normalize_programme_ids(programmes: list[str] | tuple[str, ...] | str | None) -> list[str]:
    """Normalize and de-duplicate a programme collection while preserving order."""
    if programmes is None:
        return []
    raw_programmes = [programmes] if isinstance(programmes, str) else list(programmes)
    normalized: list[str] = []
    for programme in raw_programmes:
        programme_id = normalize_programme_id(programme)
        if programme_id and programme_id not in normalized:
            normalized.append(programme_id)
    return normalized
