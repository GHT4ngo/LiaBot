"""
web_scraper.py — Skrapar karriärsidor efter individuella jobbannonser.

Flöde per källa:
  1. Hämta karriärsidan (listing-sidan)
  2. Extrahera alla jobbankarlänkar på sidan
  3. Hämta varje enskild annons och returnera den som ett eget jobb-dict

Om inga interna jobb-länkar hittas faller det tillbaka på att behandla
hela sidan som en enda annons (gamla beteendet) — ingen källa tappas bort.
"""

import hashlib
import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Nyckelord i URL-sökvägar som tyder på en individuell jobbannons
JOB_PATH_SIGNALS = [
    "job", "jobs", "career", "careers", "jobb", "jobbannons", "position",
    "opening", "vacancy", "vacancies", "role", "tjänst", "annons",
    "apply", "ansök", "rekrytering",
]

# Nyckelord i URL-sökvägar som tyder på en listningssida (skippa dessa)
LISTING_PATH_SIGNALS = [
    "search", "filter", "category", "department", "location", "team",
]

MAX_JOB_LINKS = 40   # max antal enskilda annonslänkar att följa per källa
MAX_TEXT_LEN  = 4000  # tecken att skicka till AI:n per annons


def _url_to_source_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
    return "\n".join(lines)


def _fetch(url: str) -> tuple[str, str] | None:
    """Hämtar en URL. Returnerar (html, final_url) eller None vid fel."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return resp.text, str(resp.url)
    except httpx.HTTPError:
        return None


def _extract_job_links(html: str, base_url: str) -> list[str]:
    """
    Letar efter <a>-taggar på en listningssida vars href tyder på en
    individuell jobbannons (baserat på URL-signaler och länktext).
    Returnerar en dedupliserad lista med absoluta URL:er.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    seen: set[str] = set()
    links: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        # Stanna på samma domän
        if parsed.netloc and parsed.netloc != base_domain:
            continue

        path = parsed.path.lower()

        # Skippa om sökvägen tyder på en filtreringssida
        if any(sig in path for sig in LISTING_PATH_SIGNALS):
            continue

        # Acceptera om sökvägen innehåller ett jobbsignal-ord
        if any(sig in path for sig in JOB_PATH_SIGNALS):
            clean = absolute.split("?")[0].rstrip("/")
            if clean not in seen and clean != base_url.rstrip("/"):
                seen.add(clean)
                links.append(clean)

    return links[:MAX_JOB_LINKS]


def _make_job_dict(url: str, html: str, source_name: str) -> dict:
    """Bygger ett jobb-dict från en hämtad annons-sida."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title else url
    text = _clean_text(html)
    return {
        "source":          source_name,
        "source_id":       _url_to_source_id(url),
        "source_url":      url,
        "company_name":    None,
        "company_url":     None,
        "contact_person":  None,
        "contact_email":   None,
        "job_title":       title[:200],
        "job_description": text[:MAX_TEXT_LEN],
        "location":        None,
        "is_remote":       False,
        "is_relevant":     None,
        "relevance_note":  None,
    }


def scrape_url(url: str, source_name: str = "custom") -> list[dict]:
    """
    Skrapar en karriär-URL och returnerar en lista med jobb-dicts.
    Försöker extrahera individuella annonser; faller annars tillbaka på hela sidan.
    """
    result = _fetch(url)
    if not result:
        return []
    html, final_url = result

    if len(_clean_text(html)) < 100:
        return []

    job_links = _extract_job_links(html, final_url)

    if job_links:
        jobs = []
        for link in job_links:
            r = _fetch(link)
            if r:
                job_html, job_url = r
                if len(_clean_text(job_html)) > 100:
                    jobs.append(_make_job_dict(job_url, job_html, source_name))
        if jobs:
            return jobs

    # Fallback: behandla hela sidan som en annons (t.ex. enkel statisk sida)
    return [_make_job_dict(final_url, html, source_name)]


def scrape_all(sources: list[dict], verbose: bool = True) -> list[dict]:
    """
    Skrapar alla aktiverade anpassade källor.
    sources: lista av dicts med {id, name, url}
    Returnerar en platt lista med jobb-dicts (en per individuell annons).
    """
    all_jobs: list[dict] = []
    for src in sources:
        if verbose:
            print(f"  Skrapar: {src['name']} ({src['url']})")
        jobs = scrape_url(src["url"], source_name=src["name"])
        if verbose:
            print(f"    → {len(jobs)} annons(er) hittade")
        all_jobs.extend(jobs)

    if verbose:
        print(f"  Webb-skrapare totalt: {len(all_jobs)} annonser från {len(sources)} källor.")
    return all_jobs
