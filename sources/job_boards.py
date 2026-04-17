"""
sources/job_boards.py — Söker på svenska jobbsajter efter LIA-annonser.

Komplement till JobTech. Söker samma nyckelord på:
  - Karriär.se       (svenska akademiker, IT/data)
  - Blocket Jobb     (bred svensk marknad)
  - Jobbsafari       (svensk aggregator)
  - Graduateland     (student/trainee-fokus)

Varje sökning hämtar en resultatlista, extraherar individuella jobb-URL:er
och hämtar annonstexten för Ollama-analys.
"""

import hashlib
import urllib.parse
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Svenska jobbsajter med sök-URL-mall
# Karriär.se och Blocket blockerar enkla HTTP-anrop (ConnectError)
# Jobbsafari är JS-renderad (inga länkar hittas)
# Graduateland hade fel URL-struktur
# Dessa är inaktiverade tills en fungerande lösning finns.
SEARCH_BOARDS: list[dict] = []

# Karriärsidor som förseeds i databasen (används av web_scraper.py vid varje körning)
DEFAULT_CAREER_SOURCES = [
    # --- Bemannings- och konsultföretag (LIA-vänliga) ---
    {"name": "Academic Work — Data & IT",       "url": "https://www.academicwork.se/lediga-jobb?q=data"},
    {"name": "TNG — IT & Data",                 "url": "https://www.tng.se/lediga-jobb/?searchQuery=data+engineer"},
    {"name": "Nexer Group — Karriär",           "url": "https://www.nexergroup.com/karriar/"},
    {"name": "Knowit — Lediga tjänster",        "url": "https://www.knowit.se/karriar/lediga-tjanster/"},
    {"name": "Sigma IT — Karriär",              "url": "https://www.sigma.se/karriar/"},
    {"name": "Netlight — Karriär",              "url": "https://www.netlight.com/career/"},
    {"name": "AFRY — Join Us",                  "url": "https://afry.com/en/join-us"},
    {"name": "Accenture Sverige — Karriär",     "url": "https://www.accenture.com/se-en/careers"},
    {"name": "Capgemini Sverige — Karriär",     "url": "https://www.capgemini.com/se-en/careers/"},
    {"name": "HiQ — Karriär",                   "url": "https://hiq.se/karriar/"},
    {"name": "Sogeti Sverige — Karriär",        "url": "https://www.sogeti.se/karriar/"},
    # --- Tech-startups & scaleups i Sverige ---
    {"name": "Klarna — Careers",                "url": "https://www.klarna.com/careers/"},
    {"name": "Epidemic Sound — Careers",        "url": "https://www.epidemicsound.com/careers/"},
    {"name": "Storytel — Jobs",                 "url": "https://jobs.storytel.com/"},
    {"name": "Trustly — Careers",               "url": "https://www.trustly.com/careers"},
    {"name": "Anyfin — Careers",                "url": "https://anyfin.com/careers"},
    {"name": "Zettle / PayPal — Careers",       "url": "https://www.zettle.com/gb/careers"},
    {"name": "King — Careers",                  "url": "https://careers.king.com/"},
    {"name": "DICE / EA — Careers",             "url": "https://www.dice.se/careers/"},
    {"name": "Spotify — Jobs",                  "url": "https://www.lifeatspotify.com/jobs"},
    {"name": "Einride — Karriär",               "url": "https://www.einride.tech/career"},
    {"name": "Mentimeter — Careers",            "url": "https://www.mentimeter.com/team"},
    # --- Stora svenska bolag med datateam ---
    {"name": "IKEA — Lediga jobb",              "url": "https://www.ikea.com/se/sv/this-is-ikea/work-with-us/"},
    {"name": "SEB — Tech Careers",              "url": "https://sebgroup.com/career"},
    {"name": "Ericsson — Careers",              "url": "https://jobs.ericsson.com/"},
    {"name": "Sandvik — Careers",               "url": "https://www.home.sandvik/en/careers/"},
    {"name": "Atlas Copco — Careers",           "url": "https://www.atlascopco.com/en-us/careers"},
    {"name": "Scania — Karriär",                "url": "https://www.scania.com/se/sv/home/karriar.html"},
    {"name": "Vattenfall — Karriär",            "url": "https://www.vattenfall.se/karriar/"},
    {"name": "Volvo Cars — Jobs",               "url": "https://jobs.volvocars.com/"},
    {"name": "Swedbank — Karriär",              "url": "https://www.swedbank.com/sv/om-swedbank/karriar.html"},
    {"name": "Tele2 — Karriär",                 "url": "https://www.tele2.com/sv/om-tele2/karriar/"},
    # --- Fintech & bank ---
    {"name": "Avanza — Karriär",                "url": "https://www.avanza.se/om-avanza/jobba-hos-oss.html"},
    {"name": "Nordnet — Karriär",               "url": "https://www.nordnet.se/se/om-nordnet/om-foretaget/jobba-hos-oss.html"},
    {"name": "Klarna — Engineering",            "url": "https://www.klarna.com/careers/engineering/"},
]


def _url_to_source_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines() if ln.strip()]
    return "\n".join(lines)


def _find_job_links(soup: BeautifulSoup, base_url: str, patterns: list[str]) -> list[str]:
    """Extraherar jobb-URL:er från en sökresultatsida.
    Behåller query-parametrar — många sajter använder ?id=123 som del av URL:en.
    """
    seen: set[str] = set()
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0]   # strip fragment only, keep query params
        if not href:
            continue
        if href.startswith("/"):
            href = base_url + href
        elif not href.startswith("http"):
            continue
        if href in seen:
            continue
        path = urllib.parse.urlparse(href).path
        if any(p in href for p in patterns) and len(path) > 8:
            seen.add(href)
            links.append(href)
    return links


def _scrape_job_page(url: str, board_name: str) -> dict | None:
    """Hämtar en enskild jobbannonssida och returnerar ett normaliserat jobb-dict."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception:
        return None
    text = _clean_text(resp.text)
    if len(text) < 150:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title else url
    return {
        "source":          board_name,
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


def fetch_from_board(board: dict, keyword: str, log=None) -> list[dict]:
    """Söker ett nyckelord på en jobbsajt och returnerar matchande annonser."""
    if log is None:
        log = print
    search_url = board["search_url"].format(keyword=urllib.parse.quote(keyword))
    try:
        resp = httpx.get(search_url, headers=HEADERS, timeout=20, follow_redirects=True)
        if resp.status_code == 404:
            log(f"[{board['name']}] URL ej funnen (404) — hoppar över")
            return []
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        log(f"[{board['name']}] HTTP-fel {e.response.status_code} — hoppar över")
        return []
    except Exception as e:
        log(f"[{board['name']}] anslutningsfel: {type(e).__name__} — hoppar över")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = _find_job_links(soup, board["base_url"], board["job_patterns"])
    links = links[:board.get("max_jobs", 15)]

    if not links:
        log(f"[{board['name']}] '{keyword}': inga jobb-länkar hittades (JS-renderad sida?)")
        return []

    results = []
    for url in links:
        job = _scrape_job_page(url, board["name"])
        if job:
            results.append(job)
    return results


def fetch_all_boards(
    keywords: list[str],
    stop_flag: list | None = None,
    max_keywords: int = 5,
    log=None,
) -> list[dict]:
    """
    Söker alla konfigurerade jobbsajter för de första max_keywords sökorden.
    Returnerar en deduplicerad lista av jobb-dicts redo för Ollama-analys.
    """
    if stop_flag is None:
        stop_flag = [False]

    seen_ids: set[str] = set()
    results: list[dict] = []

    if log is None:
        log = print

    for board in SEARCH_BOARDS:
        if stop_flag[0]:
            break
        board_count = 0
        for keyword in keywords[:max_keywords]:
            if stop_flag[0]:
                break
            jobs = fetch_from_board(board, keyword, log=log)
            for job in jobs:
                sid = job.get("source_id", "")
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    results.append(job)
                    board_count += 1
        log(f"[{board['name']}] {board_count} unika annonser hämtade")

    return results
