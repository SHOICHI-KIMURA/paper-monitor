from __future__ import annotations

import logging
import os

import requests

LOGGER = logging.getLogger(__name__)
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def save_papers_to_notion(papers: list[dict]) -> list[dict]:
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID is not set")

    saved = []
    for paper in papers:
        pmid = paper.get("pmid", "")
        if not pmid:
            continue
        if _exists(database_id, pmid):
            LOGGER.info("Skipping duplicate PMID=%s", pmid)
            paper["notion_status"] = "duplicate"
            saved.append(paper)
            continue
        _create_page(database_id, paper)
        paper["notion_status"] = "created"
        saved.append(paper)
        LOGGER.info("Created Notion page for PMID=%s", pmid)
    return saved


def _exists(database_id: str, pmid: str) -> bool:
    response = requests.post(
        f"{NOTION_API_BASE}/databases/{database_id}/query",
        headers=_headers(),
        json={
            "filter": {
                "property": "PMID",
                "rich_text": {"equals": pmid},
            },
            "page_size": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    return bool(response.json().get("results"))


def _create_page(database_id: str, paper: dict) -> None:
    response = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(),
        json={
            "parent": {"database_id": database_id},
            "properties": _properties(paper),
        },
        timeout=30,
    )
    response.raise_for_status()


def _headers() -> dict:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _properties(paper: dict) -> dict:
    classification = paper.get("classification") or {}
    summary = "\n".join(classification.get("japanese_summary_3lines", []))
    why = "\n".join(classification.get("why_important_for_ent", []))

    properties = {
        "Title": {"title": [{"text": {"content": _clip(paper.get("title", ""), 1900)}}]},
        "PMID": {"rich_text": [{"text": {"content": paper.get("pmid", "")}}]},
        "DOI": {"rich_text": [{"text": {"content": paper.get("doi", "")}}]},
        "URL": {"url": paper.get("url") or None},
        "Journal": {"rich_text": [{"text": {"content": paper.get("journal", "")}}]},
        "IF": {"number": paper.get("impact_factor")},
        "Tier": {"select": {"name": paper.get("tier", "IF10")}},
        "ENT relevance": {"select": {"name": classification.get("ent_relevance", "low")}},
        "Category": {"select": {"name": classification.get("category", "other")}},
        "Clinical Impact": {"select": {"name": classification.get("clinical_impact", "low")}},
        "Recommendation": {"select": {"name": classification.get("recommendation", "スキップ")}},
        "Japanese Summary": {"rich_text": [{"text": {"content": _clip(summary, 1900)}}]},
        "Why Important": {"rich_text": [{"text": {"content": _clip(why, 1900)}}]},
        "AI/DX": {"checkbox": bool(paper.get("ai_dx"))},
    }
    if paper.get("pub_date") and len(paper["pub_date"]) >= 10:
        properties["Published Date"] = {"date": {"start": paper["pub_date"][:10]}}
    return properties


def _clip(value: str, limit: int) -> str:
    return (value or "")[:limit]
