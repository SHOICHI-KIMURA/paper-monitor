from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def normalize_journal(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def load_journals(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["if"] = float(row["if"])
        row["normalized_journal"] = normalize_journal(row["journal"])
    return rows


def attach_if_metadata(papers: list[dict], journals: list[dict]) -> list[dict]:
    by_journal = {row["normalized_journal"]: row for row in journals}
    matched = []
    for paper in papers:
        journal_key = normalize_journal(paper.get("journal", ""))
        meta = by_journal.get(journal_key)
        if not meta:
            # PubMedの正式誌名に副題（" : official journal of ..."）が付く誌への対応
            meta = next(
                (row for row in journals if journal_key.startswith(row["normalized_journal"] + " :")),
                None,
            )
        if not meta:
            continue
        enriched = {
            **paper,
            "impact_factor": meta["if"],
            "tier": meta["tier"],
            "track": meta.get("track", ""),
            "configured_journal": meta["journal"],
        }
        matched.append(enriched)
    LOGGER.info("IF filter matched %d/%d papers", len(matched), len(papers))
    return matched


def tag_ai_dx(papers: list[dict], ai_terms: list[str]) -> list[dict]:
    """タイトル・抄録にAI/DX関連語が含まれるかだけを見てタグを立てる（収集条件には使わない）。"""
    terms = [t.lower() for t in ai_terms if t]
    for paper in papers:
        haystack = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        paper["ai_dx"] = any(term in haystack for term in terms)
    return papers


def keep_after_classification(paper: dict) -> bool:
    tier = paper.get("tier")
    if tier == "IF50":
        return True
    classification = paper.get("classification") or {}
    return tier == "IF10" and classification.get("ent_relevance") in {"high", "middle"}
