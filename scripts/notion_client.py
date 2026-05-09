from __future__ import annotations

import os

from notion_client import Client


def get_notion_client() -> Client:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")
    return Client(auth=token)
