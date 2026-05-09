from __future__ import annotations

import html
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)


def render_digest(papers: list[dict], output_dir: str | None = None) -> Path:
    tz = ZoneInfo(os.getenv("TZ", "Asia/Tokyo"))
    now = datetime.now(tz)
    output = Path(output_dir or os.getenv("DIGEST_OUTPUT_DIR", "outputs"))
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"digest_{now:%Y-%m-%d}.html"

    counts = Counter((p.get("classification") or {}).get("recommendation", "スキップ") for p in papers)
    path.write_text(_html(papers, now, counts), encoding="utf-8")
    LOGGER.info("Rendered digest: %s", path)
    return path


def _html(papers: list[dict], generated_at: datetime, counts: Counter) -> str:
    cards = "\n".join(_card(paper) for paper in _sort_papers(papers))
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ENT Paper Digest {generated_at:%Y-%m-%d}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17212b;
      --muted: #667085;
      --line: #d8dee8;
      --bg: #f6f8fb;
      --must: #b42318;
      --keep: #9a6700;
      --skip: #667085;
    }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 18px 48px; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .summary {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .pill {{ border: 1px solid var(--line); background: #fff; padding: 8px 10px; border-radius: 6px; font-size: 14px; }}
    .card {{ background: #fff; border: 1px solid var(--line); border-left: 6px solid var(--skip); border-radius: 8px; padding: 18px; margin: 14px 0; }}
    .card.must {{ border-left-color: var(--must); }}
    .card.keep {{ border-left-color: var(--keep); }}
    .card.skip {{ opacity: .78; }}
    h2 {{ font-size: 19px; line-height: 1.35; margin: 0 0 10px; letter-spacing: 0; }}
    .journal {{ color: var(--muted); font-size: 14px; margin-bottom: 14px; }}
    .badge {{ display: inline-block; font-weight: 700; margin-right: 8px; }}
    .must .badge {{ color: var(--must); }}
    .keep .badge {{ color: var(--keep); }}
    ul {{ padding-left: 20px; }}
    li {{ margin: 4px 0; }}
    a {{ color: #175cd3; }}
    footer {{ margin-top: 26px; color: var(--muted); font-size: 13px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>ENT Paper Digest</h1>
      <div class="meta">生成日時: {generated_at:%Y-%m-%d %H:%M %Z}</div>
      <div class="summary">
        <span class="pill">合計 {len(papers)} 件</span>
        <span class="pill">必読 {counts.get("必読", 0)} 件</span>
        <span class="pill">要約保存 {counts.get("要約保存", 0)} 件</span>
        <span class="pill">スキップ {counts.get("スキップ", 0)} 件</span>
      </div>
    </header>
    {cards or "<p>今週の候補論文はありません。</p>"}
    <footer>PMID重複除外、IFフィルタ、LLM分類を経て生成。</footer>
  </main>
</body>
</html>
"""


def _card(paper: dict) -> str:
    c = paper.get("classification") or {}
    recommendation = c.get("recommendation", "スキップ")
    cls = {"必読": "must", "要約保存": "keep"}.get(recommendation, "skip")
    summary = "".join(f"<li>{html.escape(line)}</li>" for line in c.get("japanese_summary_3lines", []) if line)
    reading_points = "".join(f"<li>{html.escape(line)}</li>" for line in c.get("ent_reading_points", c.get("why_important_for_ent", [])) if line)
    cautions = "".join(f"<li>{html.escape(line)}</li>" for line in c.get("limitations_or_cautions", []) if line)
    return f"""<article class="card {cls}">
  <h2>{html.escape(paper.get("title", ""))}</h2>
  <div class="journal">
    <span class="badge">{html.escape(recommendation)}</span>
    {html.escape(paper.get("journal", ""))} / IF {paper.get("impact_factor", "")} / {html.escape(paper.get("pub_date", ""))}
  </div>
  <strong>3行要約</strong>
  <ul>{summary}</ul>
  <strong>ENTでの読みどころ</strong>
  <ul>{reading_points}</ul>
  <strong>限界・注意点</strong>
  <ul>{cautions or "<li>抄録情報からは明確な限界を判断できません。</li>"}</ul>
  <a href="{html.escape(paper.get("url", ""))}" target="_blank" rel="noopener">論文ページを開く</a>
</article>"""



def _sort_papers(papers: list[dict]) -> list[dict]:
    rank = {"必読": 0, "要約保存": 1, "スキップ": 2}
    return sorted(
        papers,
        key=lambda p: (
            rank.get((p.get("classification") or {}).get("recommendation", "スキップ"), 9),
            -float(p.get("impact_factor") or 0),
        ),
    )
