"""
sources/web_scraper.py — Skrapar godtyckliga URL:er efter jobbannonser.

Används för anpassade källsidor (t.ex. företagets karriärsida, LinkedIn-sidor,
Stockholms stad, etc.) som lagras i tabellen `sources` i databasen.

Varje URL hämtas, texten extraheras, och Ollama-analyzern avgör relevans.
"""

import os
import re
import hashlib
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _clean_text(html: str) -> str:
    """Extraherar ren text ur HTML, tar bort scripts/styles."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Komprimera whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _url_to_source_id(url: str) -> str:
    """Genererar ett stabilt ID från URL (för dedup i databasen)."""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def scrape_url(url: str, source_name: str = "custom") -> dict | None:
    """
    Hämtar en URL och returnerar ett jobb-dict med råtext som description.
    Returnerar None om sidan inte kunde hämtas.
    """
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"    Skrapningfel för {url}: {e}")
        return None

    text = _clean_text(resp.text)
    if len(text) < 100:
        return None

    # Försök hitta en rubrik (title-taggen)
    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title else url

    return {
        "source":          source_name,
        "source_id":       _url_to_source_id(url),
        "source_url":      url,
        "company_name":    None,
        "company_url":     None,
        "contact_person":  None,
        "contact_email":   None,
        "job_title":       title[:200],
        "job_description": text[:4000],
        "location":        None,
        "is_remote":       False,
        "is_relevant":     None,
        "relevance_note":  None,
    }


def scrape_all(sources: list[dict], verbose: bool = True) -> list[dict]:
    """
    Skrapar alla aktiverade anpassade källor.
    sources: lista av dicts med {id, name, url}
    Returnerar lista av jobb-dicts.
    """
    results = []
    for src in sources:
        if verbose:
            print(f"  Skrapar: {src['name']} ({src['url']})")
        job = scrape_url(src["url"], source_name=src["name"])
        if job:
            results.append(job)
        else:
            if verbose:
                print(f"    (ingen data hämtades)")

    if verbose:
        print(f"  Webb-skrapare: {len(results)} sidor hämtade.")
    return results
