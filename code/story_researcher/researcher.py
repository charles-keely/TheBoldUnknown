import requests
import json
from openai import OpenAI
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import re
from .config import config
from .prompts import (
    get_phase_1_prompt, 
    get_phase_2_angle_prompt, 
    PHASE_1_SYSTEM_PROMPT, 
    PHASE_2_SYSTEM_PROMPT
)

_URL_RE = re.compile(r"https?://[^\s)>\]]+")

def _registrable_domain(hostname: str) -> str:
    """
    Best-effort extraction of registrable domain WITHOUT extra deps.
    Handles common multi-part public suffixes (co.uk, com.au, etc.).
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]

    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host

    # Minimal set of common multi-part suffixes we see in the wild.
    multipart_suffixes = {
        "co.uk", "org.uk", "ac.uk", "gov.uk",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.jp", "ne.jp", "or.jp",
        "co.nz", "org.nz", "govt.nz",
        "com.br", "com.mx",
    }
    last_two = ".".join(parts[-2:])
    last_three = ".".join(parts[-3:])

    # If it ends with a multipart suffix, registrable is the last 3 parts.
    if last_two in multipart_suffixes and len(parts) >= 3:
        return last_three
    return last_two

def _source_name_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None

    # Exclude low-signal aggregators/social platforms from "primary sources".
    excluded = {
        "reddit.com",
        "x.com",
        "twitter.com",
        "t.co",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "youtube.com",
        "youtu.be",
        "medium.com",
    }
    for d in excluded:
        if host == d or host.endswith("." + d):
            return None

    registrable = _registrable_domain(host)

    # Common high-signal org mappings first.
    domain_map = {
        "nasa.gov": "NASA",
        "jpl.nasa.gov": "NASA JPL",
        "esa.int": "ESA",
        "noaa.gov": "NOAA",
        "nih.gov": "NIH",
        "cdc.gov": "CDC",
        "usgs.gov": "USGS",
        "who.int": "WHO",
        "un.org": "United Nations",
        "nature.com": "Nature",
        "science.org": "Science",
        "sciencemag.org": "Science",
        "nationalgeographic.com": "National Geographic",
        "smithsonianmag.com": "Smithsonian",
        "smithsonian.gov": "Smithsonian",
        "bbc.co.uk": "BBC",
        "bbc.com": "BBC",
        "reuters.com": "Reuters",
        "apnews.com": "Associated Press",
        "nytimes.com": "The New York Times",
        "washingtonpost.com": "The Washington Post",
        "theguardian.com": "The Guardian",
        "cnn.com": "CNN",
        "foxnews.com": "Fox News",
        "npr.org": "NPR",
        "pbs.org": "PBS",
        "arxiv.org": "arXiv",
        "wikipedia.org": "Wikipedia",
    }

    # Handle subdomain variants (e.g., science.nasa.gov)
    for k, v in domain_map.items():
        if host == k or host.endswith("." + k):
            return v

    # Government / academic / known institutions: use the second-level label.
    if registrable.endswith(".gov") or registrable.endswith(".edu"):
        base = registrable.split(".")[0]
        return base.upper() if len(base) <= 5 else base.title()

    # Generic fallback: turn "example.com" -> "Example"
    base = registrable.split(".")[0]
    if not base:
        return None

    # If the base includes hyphens, title-case segments.
    if "-" in base:
        return " ".join([seg.capitalize() for seg in base.split("-") if seg])
    return base.capitalize()

def _extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    urls = _URL_RE.findall(text)
    # strip trailing punctuation that often follows markdown links.
    cleaned: List[str] = []
    for u in urls:
        cleaned.append(u.rstrip(".,;:!?\"'"))
    return cleaned

def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.strip()
        if not key:
            continue
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out

def _primary_sources_from_urls(urls: List[str]) -> Tuple[List[str], List[str]]:
    """
    Returns (primary_source_names, representative_urls) in first-seen order.
    representative_urls is one URL per source-name (first seen for that source).
    """
    names: List[str] = []
    rep_urls: List[str] = []
    seen = set()
    for u in urls:
        name = _source_name_from_url(u)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
        rep_urls.append(u)
    return names, rep_urls

class PerplexityClient:
    def __init__(self):
        self.api_key = config.PERPLEXITY_API_KEY
        self.base_url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def chat(self, messages: List[Dict[str, str]], *, return_citations: bool = True) -> Dict[str, Any]:
        payload = {
            "model": config.PERPLEXITY_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "return_citations": bool(return_citations),
        }
        response = requests.post(self.base_url, json=payload, headers=self.headers)
        if not response.ok:
            print(f"Perplexity Error: {response.text}")
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Perplexity returns citations in `search_results` when return_citations=true.
        search_results = data.get("search_results") or []
        return {"content": content, "search_results": search_results}

class Researcher:
    def __init__(self):
        self.pplx = PerplexityClient()
        self.openai = OpenAI(api_key=config.OPENAI_API_KEY)

    def research_story(self, story: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the 2-phase research process.
        """
        print(f"Starting research for: {story.get('title')}")
        
        # Phase 1: General Research (Perplexity)
        print("Phase 1: Gathering Ground Truth...")
        phase_1_prompt = get_phase_1_prompt(
            story.get('title'), 
            story.get('url'), 
            story.get('summary')
        )
        
        phase_1_messages = [
            {"role": "system", "content": PHASE_1_SYSTEM_PROMPT},
            {"role": "user", "content": phase_1_prompt}
        ]
        
        phase_1_resp = self.pplx.chat(phase_1_messages, return_citations=True)
        phase_1_result = phase_1_resp.get("content", "")
        phase_1_search_results = phase_1_resp.get("search_results", []) or []
        
        # Phase 2: Check for research gaps (OpenAI)
        print("Phase 2: Checking for research gaps...")
        phase_2_prompt = get_phase_2_angle_prompt(phase_1_result)
        
        phase_2_response = self.openai.chat.completions.create(
            model=config.RESEARCHER_MODEL,
            messages=[
                {"role": "system", "content": PHASE_2_SYSTEM_PROMPT},
                {"role": "user", "content": phase_2_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        gap_analysis = json.loads(phase_2_response.choices[0].message.content)
        follow_up_question = gap_analysis.get("follow_up_question")
        
        # Optional Deep Dive (Perplexity) - only if a follow-up question was generated
        deep_dive = None
        
        if follow_up_question:
            print(f"Follow-up needed: {follow_up_question}")
            
            deep_dive_system = """You are a specialized researcher for 'TheBoldUnknown'.
Focus on finding specific, vivid details that are:
- Visually striking or easy to imagine
- Strange, counterintuitive, or surprising
- Grounded in fact (label speculation clearly)
Be concise but thorough. Prioritize details that would make someone stop scrolling."""
            
            q_prompt = f"Regarding the story '{story.get('title')}': {follow_up_question}"
            
            q_messages = [
                {"role": "system", "content": deep_dive_system},
                {"role": "user", "content": q_prompt}
            ]
            deep_dive_resp = self.pplx.chat(q_messages, return_citations=True)
            answer = deep_dive_resp.get("content", "")
            deep_dive = {
                "question": follow_up_question,
                "answer": answer,
                "search_results": deep_dive_resp.get("search_results", []) or [],
            }
        else:
            print("No follow-up needed — research is complete.")

        # Build a stable set of "primary sources" (names) + representative URLs.
        urls: List[str] = []
        urls.extend(_extract_urls_from_text(phase_1_result))
        urls.extend([sr.get("url", "") for sr in phase_1_search_results if isinstance(sr, dict)])
        if deep_dive:
            urls.extend(_extract_urls_from_text(deep_dive.get("answer", "")))
            urls.extend([sr.get("url", "") for sr in deep_dive.get("search_results", []) if isinstance(sr, dict)])
        # Always include the lead URL as context, even if it's not a primary source.
        if story.get("url"):
            urls.append(str(story["url"]))
        urls = _dedupe_preserve_order(urls)

        primary_sources, primary_source_urls = _primary_sources_from_urls(urls)

        return {
            # Backward-compatible keys used by other modules:
            "ground_truth": phase_1_result,
            "follow_up": deep_dive,

            # New structured info:
            "ground_truth_search_results": phase_1_search_results,
            "primary_sources": primary_sources,
            "primary_source_urls": primary_source_urls,
        }
