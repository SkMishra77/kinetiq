"""Unified research search across PubMed, Semantic Scholar and OpenAlex.

The functions are async and use ``httpx``. When a provider fails or is rate
limited, we fall back to the next one and to the local cache, returning
``errors[]`` in the response so Claude can honestly say what happened.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx

from ...db.connection import Database
from ...db.repos import knowledge as krepo
from ..sanitize import clean, UNTRUSTED_NOTICE

log = logging.getLogger(__name__)


@dataclass
class Paper:
    title: str
    year: int | None = None
    journal: str | None = None
    pmid: str | None = None
    doi: str | None = None
    s2_id: str | None = None
    openalex_id: str | None = None
    abstract: str | None = None
    tldr: str | None = None
    citation_count: int | None = None
    study_type_guess: str | None = None
    url: str | None = None
    authors: list[str] = field(default_factory=list)


def _hash(provider: str, params: dict) -> str:
    return hashlib.sha256((provider + "|" + json.dumps(params, sort_keys=True)).encode()).hexdigest()


def _guess_study_type(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    if "meta-analysis" in t or "meta analysis" in t:
        return "meta_analysis"
    if "systematic review" in t:
        return "systematic_review"
    if "randomized" in t or "randomised" in t:
        return "rct"
    if "cohort" in t:
        return "cohort"
    if "review" in t:
        return "review"
    return None


async def _pubmed(query: str, max_results: int, api_key: str | None) -> list[Paper]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    async with httpx.AsyncClient(timeout=8.0) as client:
        params = {"db": "pubmed", "term": query, "retmax": max_results,
                  "retmode": "json", "sort": "relevance"}
        if api_key:
            params["api_key"] = api_key
        r = await client.get(f"{base}/esearch.fcgi", params=params)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        # esummary
        r2 = await client.get(f"{base}/esummary.fcgi",
                              params={"db": "pubmed", "id": ",".join(ids),
                                      "retmode": "json",
                                      **({"api_key": api_key} if api_key else {})})
        r2.raise_for_status()
        summ = r2.json().get("result", {})
        # efetch (XML) for abstracts
        r3 = await client.get(f"{base}/efetch.fcgi",
                              params={"db": "pubmed", "id": ",".join(ids),
                                      "rettype": "abstract", "retmode": "xml",
                                      **({"api_key": api_key} if api_key else {})})
        r3.raise_for_status()
        abstracts = _parse_pubmed_abstracts(r3.text)
    papers: list[Paper] = []
    for pmid in ids:
        s = summ.get(pmid, {})
        title = clean(s.get("title") or "")
        year = None
        if s.get("pubdate"):
            m = re.search(r"\d{4}", s["pubdate"])
            year = int(m.group(0)) if m else None
        journal = s.get("fulljournalname") or s.get("source")
        pub_types = s.get("pubtype") or []
        st_guess = _guess_study_type(" ".join(pub_types) + " " + (title or ""))
        papers.append(Paper(
            title=title or "(no title)",
            year=year,
            journal=journal,
            pmid=pmid,
            doi=(s.get("elocationid") or "").replace("doi: ", "") or None,
            abstract=clean(abstracts.get(pmid)),
            citation_count=None,
            study_type_guess=st_guess,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            authors=[a.get("name") for a in (s.get("authors") or []) if a.get("name")][:6],
        ))
    return papers


def _parse_pubmed_abstracts(xml_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for art in root.iter("PubmedArticle"):
        pmid_el = art.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        parts: list[str] = []
        for a in art.iter("AbstractText"):
            if a.text:
                label = a.attrib.get("Label")
                parts.append((f"{label}: " if label else "") + a.text)
        if parts:
            out[pmid_el.text] = " ".join(parts)
    return out


async def _semantic_scholar(query: str, max_results: int, api_key: str | None) -> list[Paper]:
    headers = {"x-api-key": api_key} if api_key else {}
    fields = "title,year,abstract,tldr,citationCount,externalIds,openAccessPdf,venue,publicationTypes,authors"
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(url, params={"query": query, "limit": max_results, "fields": fields}, headers=headers)
        r.raise_for_status()
        data = r.json()
    papers: list[Paper] = []
    for p in data.get("data", []) or []:
        ext = p.get("externalIds") or {}
        st_guess = _guess_study_type(" ".join(p.get("publicationTypes") or []) + " " + (p.get("title") or ""))
        papers.append(Paper(
            title=clean(p.get("title") or "(no title)") or "(no title)",
            year=p.get("year"),
            journal=(p.get("venue") or None),
            pmid=ext.get("PubMed") or ext.get("PMID"),
            doi=ext.get("DOI"),
            s2_id=p.get("paperId"),
            abstract=clean(p.get("abstract")),
            tldr=clean((p.get("tldr") or {}).get("text")),
            citation_count=p.get("citationCount"),
            study_type_guess=st_guess,
            url=f"https://www.semanticscholar.org/paper/{p.get('paperId')}" if p.get("paperId") else None,
            authors=[a.get("name") for a in p.get("authors") or [] if a.get("name")][:6],
        ))
    return papers


async def _openalex(query: str, max_results: int, mailto: str | None) -> list[Paper]:
    params: dict[str, Any] = {"search": query, "per-page": max_results, "filter": "type:article"}
    if mailto:
        params["mailto"] = mailto
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get("https://api.openalex.org/works", params=params)
        r.raise_for_status()
        data = r.json()
    papers: list[Paper] = []
    for w in data.get("results", []) or []:
        # Reconstruct abstract from inverted index if provided
        abstract = None
        idx = w.get("abstract_inverted_index")
        if idx:
            positions: list[tuple[int, str]] = []
            for word, poss in idx.items():
                for p in poss:
                    positions.append((p, word))
            positions.sort()
            abstract = " ".join(w for _, w in positions)
        title = clean(w.get("title") or "(no title)") or "(no title)"
        doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
        primary_loc = w.get("primary_location") or {}
        journal = ((primary_loc.get("source") or {}).get("display_name"))
        papers.append(Paper(
            title=title,
            year=w.get("publication_year"),
            journal=journal,
            doi=doi,
            openalex_id=w.get("id"),
            abstract=clean(abstract),
            citation_count=w.get("cited_by_count"),
            study_type_guess=_guess_study_type(title),
            url=w.get("id"),
            authors=[a.get("author", {}).get("display_name") for a in (w.get("authorships") or [])[:6] if a.get("author")],
        ))
    return papers


PROVIDERS = {
    "pubmed": _pubmed,
    "semantic_scholar": _semantic_scholar,
    "openalex": _openalex,
}


async def search(
    db: Database,
    *,
    query: str,
    providers: list[str],
    max_results: int = 8,
    api_keys: dict | None = None,
    force_refresh: bool = False,
) -> dict:
    api_keys = api_keys or {}
    results: dict[str, list[Paper]] = {}
    errors: list[dict] = []
    from_cache: dict[str, bool] = {}
    for p in providers:
        if p not in PROVIDERS:
            errors.append({"provider": p, "error": "unknown provider"})
            continue
        params = {"query": query, "max_results": max_results}
        qh = _hash(p, params)
        cached = None if force_refresh else krepo.get_cached(db, p, qh)
        if cached and cached.get("response"):
            results[p] = [Paper(**pp) for pp in cached["response"].get("papers", [])]
            from_cache[p] = True
            continue
        try:
            fn = PROVIDERS[p]
            if p == "pubmed":
                papers = await fn(query, max_results, api_keys.get("ncbi"))  # type: ignore[arg-type]
            elif p == "semantic_scholar":
                papers = await fn(query, max_results, api_keys.get("s2"))  # type: ignore[arg-type]
            else:
                papers = await fn(query, max_results, api_keys.get("openalex_mailto"))  # type: ignore[arg-type]
            results[p] = papers
            krepo.set_cached(db, p, qh, query, params,
                              {"papers": [pp.__dict__ for pp in papers]}, 200)
        except Exception as e:  # noqa: BLE001
            log.warning("research provider %s failed: %s", p, e)
            errors.append({"provider": p, "error": str(e)[:200]})
            if cached and cached.get("response"):
                results[p] = [Paper(**pp) for pp in cached["response"].get("papers", [])]
                from_cache[p] = True
    merged = _merge(results)
    return {
        "papers": [_paper_dict(p) for p in merged[:max_results]],
        "providers": {p: ("ok" if p in results and not from_cache.get(p) else
                          "cached" if p in results else "error")
                       for p in providers},
        "from_cache": from_cache,
        "errors": errors,
        "notice": UNTRUSTED_NOTICE,
        "untrusted": True,
    }


def _merge(by_provider: dict[str, list[Paper]]) -> list[Paper]:
    seen: dict[str, Paper] = {}
    order: list[str] = []
    for _, papers in by_provider.items():
        for p in papers:
            key = p.pmid or p.doi or p.s2_id or p.openalex_id or (p.title or "").lower()
            if not key:
                continue
            if key in seen:
                cur = seen[key]
                cur.abstract = cur.abstract or p.abstract
                cur.tldr = cur.tldr or p.tldr
                cur.citation_count = cur.citation_count if cur.citation_count is not None else p.citation_count
                cur.pmid = cur.pmid or p.pmid
                cur.doi = cur.doi or p.doi
            else:
                seen[key] = p
                order.append(key)
    return [seen[k] for k in order]


def _paper_dict(p: Paper) -> dict:
    return {
        "title": p.title, "year": p.year, "journal": p.journal,
        "pmid": p.pmid, "doi": p.doi, "s2_id": p.s2_id, "openalex_id": p.openalex_id,
        "abstract": p.abstract, "tldr": p.tldr, "citation_count": p.citation_count,
        "study_type_guess": p.study_type_guess, "url": p.url, "authors": p.authors,
    }


async def verify_pmid(pmid: str, api_key: str | None = None) -> dict:
    """Fetch title/year for a PMID; used by verify-citations."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "json",
                    **({"api_key": api_key} if api_key else {})},
        )
        r.raise_for_status()
        result = r.json().get("result", {}).get(pmid, {})
    return {
        "pmid": pmid,
        "title": clean(result.get("title") or ""),
        "year": (re.search(r"\d{4}", result.get("pubdate") or "") or [None])[0],
        "journal": result.get("fulljournalname"),
    }
