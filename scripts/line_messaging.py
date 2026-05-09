from __future__ import annotations

import logging
import os

import requests

LOGGER = logging.getLogger(__name__)
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def notify_line(digest_url: str, papers: list[dict]) -> None:
    token = os.getenv("LINE_CHANNEL_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_TOKEN is not set")

    must_reads = [
        paper for paper in papers
        if (paper.get("classification") or {}).get("recommendation") == "必読"
    ][:3]
    lines = ["今週のPaper Digest", digest_url]
    lines.extend(f"- {paper.get('title', '')}" for paper in must_reads)
    message = "\n".join(lines)

    response = requests.post(
        LINE_BROADCAST_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": message[:5000]}]},
        timeout=30,
    )
    response.raise_for_status()
    LOGGER.info("Sent LINE Messaging API broadcast")
