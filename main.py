from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from scripts.digest_publish import publish_digest
from scripts.digest_render import render_digest
from scripts.fetch_pubmed import fetch_pubmed
from scripts.if_filter import attach_if_metadata, keep_after_classification, load_journals, tag_ai_dx
from scripts.line_messaging import notify_line
from scripts.llm_classify import classify_papers
from scripts.notion_save import save_papers_to_notion


ROOT = Path(__file__).parent


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logger = logging.getLogger("paper-monitor")

    logger.info("Loading configs")
    keywords = _load_yaml(ROOT / "config" / "keywords.yaml")
    journals = load_journals(ROOT / "config" / "journals_if.csv")

    logger.info("Fetching PubMed records")
    papers = fetch_pubmed(keywords, [row["journal"] for row in journals])
    tag_ai_dx(papers, keywords.get("ai_terms", []))

    logger.info("Filtering by configured journal IF")
    if_matched = attach_if_metadata(papers, journals)
    if not if_matched:
        logger.info("No IF-matched papers found")

    logger.info("Classifying with LLM")
    classified = classify_papers(if_matched) if if_matched else []
    candidates = [paper for paper in classified if keep_after_classification(paper)]
    logger.info("Keeping %d/%d classified papers", len(candidates), len(classified))

    logger.info("Saving to Notion")
    saved = save_papers_to_notion(candidates) if candidates else []

    logger.info("Rendering digest")
    digest_path = render_digest(saved)

    logger.info("Publishing digest")
    digest_url = publish_digest(digest_path)

    logger.info("Sending LINE notification")
    notify_line(digest_url, saved)

    logger.info("Done")


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


if __name__ == "__main__":
    main()
