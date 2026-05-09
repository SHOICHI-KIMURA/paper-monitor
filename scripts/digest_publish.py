from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def publish_digest(digest_path: str | Path, docs_dir: str | Path = "docs") -> str:
    digest_path = Path(digest_path)
    docs = Path(docs_dir)
    docs.mkdir(parents=True, exist_ok=True)

    target = docs / digest_path.name
    shutil.copy2(digest_path, target)
    index = docs / "index.html"
    index.write_text(_index_html(target.name), encoding="utf-8")

    base_url = os.getenv("DIGEST_BASE_URL", "").rstrip("/")
    url = f"{base_url}/index.html" if base_url else str(index)
    LOGGER.info("Published digest to %s", target)
    return url


def _index_html(latest_name: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={latest_name}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Latest ENT Paper Digest</title>
</head>
<body>
  <p><a href="{latest_name}">最新のENT Paper Digestを開く</a></p>
</body>
</html>
"""
