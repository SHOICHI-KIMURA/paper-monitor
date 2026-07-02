from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# モデル名起因の障害(400/404)に備えたフォールバック順。
# 先頭の -latest エイリアスはGoogle側のモデル改廃に自動追従する。
_FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3-flash", "gemini-2.5-flash"]
_active_model: str | None = None


def _candidate_models(preferred: str | None = None) -> list[str]:
    configured = (os.getenv("GEMINI_MODEL") or "").strip()
    ordered = [preferred, _active_model, configured, *_FALLBACK_MODELS]
    candidates: list[str] = []
    for name in ordered:
        if name and name not in candidates:
            candidates.append(name)
    return candidates

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


SYSTEM_PROMPT = """あなたは耳鼻咽喉科・頭頸部外科医向けの医学論文スクリーニング補助AIです。
入力される論文情報だけを根拠に、ENT医にとっての関連度、臨床インパクト、読む優先度を判定してください。

厳守事項:
- 抄録・タイトルにない数値、効果量、結論を作らない。
- 不明な場合は category を other にし、短い一般表現で書く。
- 出力は必ず有効なJSONだけ。Markdown、前置き、解説文は出さない。
- 文章は日本語。
- ENT医の関心領域は、頭頸部癌、鼻科、アレルギー、気道、難聴、めまい、嚥下、唾液腺、甲状腺、AI画像、マイクロバイオーム。
"""


USER_TEMPLATE = """以下の論文を分類してください。

PMID: {pmid}
Title: {title}
Journal: {journal}
Published Date: {pub_date}
Abstract:
{abstract}

返すJSON形式:
{{
  "ent_relevance": "high|middle|low",
  "category": "head_neck_oncology|rhinology|allergy|airway|hearing|vestibular|dysphagia|microbiome|AI|thyroid|salivary|other",
  "clinical_impact": "high|middle|low",
  "recommendation": "必読|要約保存|スキップ",
  "japanese_summary_3lines": ["...", "...", "..."],
  "why_important_for_ent": ["...", "...", "..."],
  "keywords": ["...", "..."],
  "confidence": 0.0
}}
"""


def classify_paper(paper: dict, model: str | None = None) -> dict[str, Any]:
    global _active_model
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    prompt = USER_TEMPLATE.format(
        pmid=paper.get("pmid", ""),
        title=paper.get("title", ""),
        journal=paper.get("journal", ""),
        pub_date=paper.get("pub_date", ""),
        abstract=paper.get("abstract", "")[:6000],
    )

    last_error: Exception | None = None
    for candidate in _candidate_models(preferred=model):
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    GEMINI_URL_TEMPLATE.format(model=candidate),
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
                result = _validate_classification(_loads_json(content))
                if candidate != _active_model:
                    LOGGER.info("Gemini model resolved to %s", candidate)
                    _active_model = candidate
                return result
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "Gemini classification failed for PMID=%s model=%s attempt=%s: %s",
                    paper.get("pmid"),
                    candidate,
                    attempt,
                    exc,
                )
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (400, 404):
                    # モデル名起因(廃止・改名)の可能性が高いのでリトライせず次の候補へ
                    break
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
