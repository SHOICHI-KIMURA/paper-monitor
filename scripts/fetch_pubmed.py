from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Iterable

import requests

LOGGER = logging.getLogger(__name__)
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class Paper:
    pmid: str
    title: str
    abstract: str
    journal: str
    pub_date: str
    authors: str
    doi: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def _or_block(terms: Iterable[str]) -> str:
    """語のリストを "..."[Title/Abstract] の OR ブロックに変換する。"""
    parts = [f'"{t}"[Title/Abstract]' for t in terms if t]
    return " OR ".join(parts)


def build_keyword_block(config: dict) -> str:
    """キーワード部分（journal・日付を除く）のクエリブロックを組み立てる。

    新方式（tracks + ai_terms）が定義されていれば、各トラックを
      ( (ai_terms の OR) AND (domain_terms の OR) )
    として組み立て、全トラックを OR で結合する。

    tracks が無い場合は旧方式（ent_keywords + if50_extra_terms をまとめて OR）
    にフォールバックする。
    """
    tracks = config.get("tracks") or []
    ai_terms = config.get("ai_terms") or []
    if tracks and ai_terms:
        ai_block = _or_block(ai_terms)
        track_blocks = []
        for track in tracks:
            domain_block = _or_block(track.get("domain_terms", []))
            if domain_block:
                track_blocks.append(f"(({ai_block}) AND ({domain_block}))")
        return " OR ".join(track_blocks)

    # --- 旧方式フォールバック ---
    return _or_block(list(config.get("ent_keywords", [])) + list(config.get("if50_extra_terms", [])))


def build_pubmed_query(config: dict, journals: Iterable[str], run_date: date | None = None) -> str:
    run_date = run_date or date.today()
    lookback_days = int(config.get("lookback_days", 7))
    start = run_date - timedelta(days=lookback_days)
    end = run_date

    journal_terms = [f'"{j}"[Journal]' for j in journals if j]
    journal_block = " OR ".join(journal_terms)
    keyword_block = build_keyword_block(config)
    date_block = f'("{start:%Y/%m/%d}"[Date - Publication] : "{end:%Y/%m/%d}"[Date - Publication])'

    if journal_block and keyword_block:
        return f"(({journal_block}) AND ({keyword_block})) AND {date_block}"
    if journal_block:
        return f"({journal_block}) AND {date_block}"
    return f"({keyword_block}) AND {date_block}"


def search_pubmed(query: str, max_results: int = 200) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results,
        "sort": "pub+date",
    }
    api_key = os.getenv("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key

    LOGGER.info("Searching PubMed: max_results=%s", max_results)
    response = requests.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=30)
    response.raise_for_status()
    ids = response.json().get("esearchresult", {}).get("idlist", [])
    LOGGER.info("PubMed returned %d PMIDs", len(ids))
    return ids


def fetch_pubmed_details(pmids: list[str]) -> list[Paper]:
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    api_key = os.getenv("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key

    time.sleep(0.34)
    response = requests.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=60)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    papers = [_parse_article(article) for article in root.findall(".//PubmedArticle")]
    papers = [paper for paper in papers if paper and paper.pmid]
    LOGGER.info("Fetched %d PubMed records", len(papers))
    return papers


def fetch_pubmed(config: dict, journals: Iterable[str]) -> list[dict]:
    query = build_pubmed_query(config, journals)
    max_results = int(config.get("max_results", 200))
    pmids = search_pubmed(query, max_results=max_results)
    return [paper.to_dict() for paper in fetch_pubmed_details(pmids)]


def _parse_article(article: ET.Element) -> Paper | None:
    medline = article.find("MedlineCitation")
    if medline is None:
        return None

    pmid = _text(medline.find("PMID"))
    article_node = medline.find("Article")
    if article_node is None:
        return None

    title = "".join(article_node.findtext("ArticleTitle", default="").split())
    title = _collect_text(article_node.find("ArticleTitle")) or title
    abstract = "\n".join(
        filter(None, (_collect_text(node) for node in article_node.findall(".//AbstractText")))
    )
    journal = _collect_text(article_node.find("./Journal/Title"))
    pub_date = _parse_pub_date(article_node.find("./Journal/JournalIssue/PubDate"))
    authors = _parse_authors(article_node.findall("./AuthorList/Author"))
    doi = _find_doi(article)
    url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

    return Paper(
        pmid=pmid,
        title=title,
        abstract=abstract,
        journal=journal,
        pub_date=pub_date,
        authors=authors,
        doi=doi,
        url=url,
    )


def _text(node: ET.Element | None) -> str:
    return node.text.strip() if node is not None and node.text else ""


def _collect_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _parse_pub_date(node: ET.Element | None) -> str:
    if node is None:
        return ""
    year = _text(node.find("Year"))
    month = _text(node.find("Month")) or "01"
    day = _text(node.find("Day")) or "01"
    month_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
    }
    month = month_map.get(month, month)
    if year:
        return f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"
    return _text(node.find("MedlineDate"))


def _parse_authors(author_nodes: list[ET.Element]) -> str:
    names = []
    for author in author_nodes[:8]:
        last = _text(author.find("LastName"))
        fore = _text(author.find("ForeName"))
        collective = _text(author.find("CollectiveName"))
        name = collective or " ".join(part for part in [fore, last] if part)
        if name:
            names.append(name)
    if len(author_nodes) > 8:
        names.append("et al.")
    return ", ".join(names)


def _find_doi(article: ET.Element) -> str:
    for node in article.findall(".//ArticleId"):
        if node.attrib.get("IdType") == "doi" and node.text:
            return node.text.strip()
    for node in article.findall(".//ELocationID"):
        if node.attrib.get("EIdType") == "doi" and node.text:
            return node.text.strip()
    return ""
