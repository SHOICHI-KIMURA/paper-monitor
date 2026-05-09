from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

ALLOWED = {
    "ent_relevance": {"high", "middle", "low"},
    "category": {
        "head_neck_oncology", "rhinology", "allergy", "airway", "hearing",
        "vestibular", "dysphagia", "microbiome", "AI", "thyroid",
        "salivary", "other",
    },
    "clinical_impact": {"high", "middle", "low"},
    "recommendation": {"必読", "要約保存", "スキップ"},
}

DEFAULTS = {
    "ent_relevance": "low",
    "category": "other",
    "clinical_impact": "low",
    "recommendation": "スキップ",
}


SYSTEM_PROMPT = """あなたは耳鼻咽喉科・頭頸部外科医のための「論文の目利き役」です。
目的は、論文を単に要約することではなく、忙しいENT医が「読む価値」「臨床・研究への効きどころ」「限界」を短時間で判断できるようにすることです。

最重要方針:
- 抄録・タイトルに書かれていない結果、数値、結論は絶対に作らない。
- 抄録がない、または情報が少ない場合は、推測で膨らませず「抄録情報が乏しいため判断保留」と明記する。
- IFが高いだけで「必読」にしない。ENT診療・頭頸部癌・鼻科・アレルギー・気道・聴覚・めまい・嚥下・甲状腺・唾液腺・AI画像・マイクロバイオームに実質的な関係がある場合だけ高く評価する。
- ニュース記事、Editorial、Commentary、Patient Page、Reply、Career記事は、原則として「要約保存」または「スキップ」。臨床判断を変える一次研究・RCT・メタ解析・重要レビューを優先する。
- 「可能性があります」「重要です」「示唆されます」だけで終わらせない。なぜそう言えるのか、どの診療場面に効くのかを書く。
- 日本語は、専門医が読むメモとして自然に。過度に丁寧な一般論ではなく、少し踏み込んだ臨床的コメントにする。
- 出力は必ず有効なJSONのみ。Markdown、前置き、解説文は出さない。

評価基準:
- ent_relevance high: ENTの日常診療、手術、治療選択、患者説明、研究テーマに直接関係する。
- ent_relevance middle: 直接ではないが、頭頸部癌、アレルギー、気道、AI画像、マイクロバイオームなどに応用可能。
- ent_relevance low: 一般医学としては重要でもENTへの接続が弱い。

recommendation:
- 必読: ENT医の診療・研究・患者説明を変えうる一次研究、RCT、メタ解析、重要レビュー。
- 要約保存: 周辺知識として有用、研究アイデアになる、または将来応用がありそう。
- スキップ: ENTとの接続が弱い、情報が少ない、ニュース/返信/キャリア記事など。
"""


USER_TEMPLATE = """USER_TEMPLATE = """以下の論文を分類してください。

PMID: {pmid}
Title: {title}
Journal: {journal}
Published Date: {pub_date}
Abstract:
{abstract}

japanese_summary_3lines は以下の3行にしてください:
1行目: 研究デザイン・対象・問い。抄録がない場合は「抄録情報なし」と明記。
2行目: 主な結果または論点。数値が抄録にある場合は入れる。なければ作らない。
3行目: 何が新しいか、または既存知識に対して何を足したか。

why_important_for_ent は以下の3行にしてください:
1行目: ENTのどの領域に関係するか。
2行目: 診療・手術・薬物療法・患者説明・研究設計のどこに効くか。
3行目: 注意点、限界、または「今すぐ読むべき理由」。情報不足なら判断保留と書く。

避ける表現:
- 「重要です」だけで終わる文
- 「可能性があります」の連発
- 抄録にない効果や結論の創作
- IFが高いことだけを理由にした必読判定

返すJSON形式:
{{
  "ent_relevance": "high|middle|low",
  "category": "head_neck_oncology|rhinology|allergy|airway|hearing|vestibular|dysphagia|microbiome|AI|thyroid|salivary|other",
  "clinical_impact": "high|middle|low",
  "recommendation": "必読|要約保存|スキップ",
  "japanese_summary_3lines": ["...", "...", "..."],
  "ent_reading_points": ["...", "...", "..."],
  "limitations_or_cautions": ["...", "..."]
  "keywords": ["...", "..."],
  "confidence": 0.0
}}
"""

"""


def classify_paper(paper: dict, model: str | None = None) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = USER_TEMPLATE.format(
        pmid=paper.get("pmid", ""),
        title=paper.get("title", ""),
        journal=paper.get("journal", ""),
        pub_date=paper.get("pub_date", ""),
        abstract=paper.get("abstract", "")[:6000],
    )

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                GEMINI_URL_TEMPLATE.format(model=model),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json={
                    "contents": [
                        {"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                        "response_mime_type": "application/json",
                    },
                },
                timeout=60,
            )
            response.raise_for_status()
            content = _extract_gemini_text(response.json())
            return _validate_classification(_loads_json(content))
        except Exception as exc:
            last_error = exc
            LOGGER.warning(
                "Gemini classification failed for PMID=%s attempt=%s: %s",
                paper.get("pmid"),
                attempt,
                exc,
            )
    raise RuntimeError(f"Gemini classification failed after retries: {last_error}") from last_error


def classify_papers(papers: list[dict]) -> list[dict]:
    classified = []
    for index, paper in enumerate(papers, start=1):
        LOGGER.info("Classifying paper %d/%d PMID=%s", index, len(papers), paper.get("pmid"))
        classification = classify_paper(paper)
        classified.append({**paper, "classification": classification})
    return classified


def _extract_gemini_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini response has no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts)
    if not text.strip():
        raise ValueError("Gemini response text is empty")
    return text.strip()


def _loads_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _validate_classification(data: dict[str, Any]) -> dict[str, Any]:
    result = {
        "ent_relevance": data.get("ent_relevance", "low"),
        "category": data.get("category", "other"),
        "clinical_impact": data.get("clinical_impact", "low"),
        "recommendation": data.get("recommendation", "スキップ"),
        "japanese_summary_3lines": _list3(data.get("japanese_summary_3lines")),
        "why_important_for_ent": _list3(data.get("why_important_for_ent")),
        "keywords": _list(data.get("keywords"))[:8],
        "confidence": data.get("confidence", 0.0),
    }
    for key, allowed in ALLOWED.items():
        if result[key] not in allowed:
            result[key] = DEFAULTS[key]
    try:
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    return result


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _list3(value: Any) -> list[str]:
    items = _list(value)[:3]
    while len(items) < 3:
        items.append("")
    return items
