from __future__ import annotations

import logging
import os

from .notion_client import get_notion_client

LOGGER = logging.getLogger(__name__)


def save_papers_to_notion(papers: list[dict]) -> list[dict]:
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID is not set")

    notion = get_notion_client()
    saved = []
    for paper in papers:
        pmid = paper.get("pmid", "")
        if not pmid:
            continue
        if _exists(notion, database_id, pmid):
            LOGGER.info("Skipping duplicate PMID=%s", pmid)
            paper["notion_status"] = "duplicate"
            saved.append(paper)
            continue
        notion.pages.create(parent={"database_id": database_id}, properties=_properties(paper))
        paper["notion_status"] = "created"
        saved.append(paper)
        LOGGER.info("Created Notion page for PMID=%s", pmid)
    return saved


def _exists(notion, database_id: str, pmid: str) -> bool:
    response = notion.databases.query(
        database_id=database_id,
        filter={"property": "PMID", "rich_text": {"equals": pmid}},
        page_size=1,
    )
    return bool(response.get("results"))


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
    }
    if paper.get("pub_date") and len(paper["pub_date"]) >= 10:
        properties["Published Date"] = {"date": {"start": paper["pub_date"][:10]}}
    return properties


def _clip(value: str, limit: int) -> str:
    return (value or "")[:limit]
