"""
sources/jobtech.py — Hämtar jobbannonser från Arbetsförmedlingens JobTech API.

Dokumentation: https://jobsearch.api.jobtechdev.se/
Täcker Platsbanken och 200+ jobbsiter i Sverige.
"""

import os
import httpx
from typing import Callable
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

JOBTECH_BASE = "https://jobsearch.api.jobtechdev.se"
STOCKHOLM_MUNICIPALITY = "0180"  # Stockholms stad
STOCKHOLM_REGION = (
    "01"  # Stockholms Län — täcker hela länet inkl. Nacka, Solna, Lidingö m.fl.
)
PAGE_SIZE = 100
MAX_RESULTS_PER_QUERY = 2000

# Alla tillgängliga platser — visas i frontend
AVAILABLE_LOCATIONS: list[dict] = [
    {
        "id": "stockholm",
        "label": "Stockholm (stad)",
        "description": "Stockholms stad (municipality 0180)",
    },
    {
        "id": "stockholm_region",
        "label": "Nära Stockholm",
        "description": "Stockholms Län — inkl. Nacka, Solna, Sundbyberg, Lidingö m.fl.",
    },
    {"id": "remote", "label": "Distansarbete", "description": "Jobb med remote-flagga"},
    {
        "id": "sweden",
        "label": "Hela Sverige",
        "description": "Ingen geografisk begränsning",
    },
]

DEFAULT_LOCATIONS = ["stockholm", "remote", "sweden"]


def _fetch_page(keyword: str, offset: int, location: str) -> dict:
    """
    Hämtar en sida med träffar.
    location = 'stockholm' | 'stockholm_region' | 'remote' | 'sweden'
      - stockholm:        Stockholms stad (municipality 0180)
      - stockholm_region: Stockholms Län (region 01) — nära Stockholm
      - remote:           distansarbete (remote=true)
      - sweden:           hela Sverige utan geografiskt filter
    """
    if location == "stockholm":
        params = {
            "q": keyword,
            "municipality": STOCKHOLM_MUNICIPALITY,
            "offset": offset,
            "limit": PAGE_SIZE,
            "sort": "pubdate-desc",
        }
    elif location == "stockholm_region":
        params = {
            "q": keyword,
            "region": STOCKHOLM_REGION,
            "offset": offset,
            "limit": PAGE_SIZE,
            "sort": "pubdate-desc",
        }
    elif location == "remote":
        params = {
            "q": keyword,
            "remote": "true",
            "offset": offset,
            "limit": PAGE_SIZE,
            "sort": "pubdate-desc",
        }
    else:  # sweden — nationwide, no location filter
        params = {
            "q": keyword,
            "offset": offset,
            "limit": PAGE_SIZE,
            "sort": "pubdate-desc",
        }

    resp = httpx.get(
        f"{JOBTECH_BASE}/search",
        params=params,
        headers={"accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_date(date_str: str | None) -> str | None:
    """Returnerar YYYY-MM-DD eller None."""
    if not date_str:
        return None
    return date_str[:10]


def _normalize_hit(hit: dict, is_remote_search: bool = False) -> dict:
    """Omvandlar ett JobTech-objekt till LiaBots interna format."""
    employer = hit.get("employer", {})
    workplace = hit.get("workplace_address", {})
    description_text = hit.get("description", {}).get("text", "") or ""
    application = hit.get("application_details", {}) or {}

    location_parts = []
    if workplace.get("city"):
        location_parts.append(workplace["city"])
    if workplace.get("municipality"):
        location_parts.append(workplace["municipality"])
    location = ", ".join(location_parts) or workplace.get("region", "")

    # Sista ansökningsdatum → relevant_period
    deadline = _parse_date(hit.get("application_deadline"))
    relevant_period = f"t.o.m. {deadline}" if deadline else None

    return {
        "source": "jobtech",
        "source_id": hit.get("id", ""),
        "source_url": hit.get("webpage_url") or application.get("url"),
        "company_name": employer.get("name"),
        "company_url": employer.get("url"),
        "contact_person": None,
        "contact_email": None,
        "contact_title": None,
        "contact_linkedin": None,
        "job_title": hit.get("headline", ""),
        "job_description": description_text[:4000],
        "location": location,
        "is_remote": workplace.get("municipality") is None or is_remote_search,
        "posted_date": _parse_date(hit.get("publication_date")),
        "relevant_period": relevant_period,
        "start_date": None,  # extracted by AI from description if mentioned
        "is_relevant": None,
        "relevance_note": None,
        "ai_highlight": None,
        "prerequisites": None,
    }


def fetch_all(
    keywords: list[str],
    locations: list[str] | None = None,
    known_ids: set[str] | None = None,
    resume_state: dict | None = None,
    on_page: Callable | None = None,
    stop_flag: list | None = None,
) -> list[dict]:
    """
    Hämtar alla annonser för en lista sökord och valda platser.

    Args:
        keywords:     Lista sökord
        locations:    Lista plats-ID:n att söka på. Tillgängliga: 'stockholm',
                      'stockholm_region', 'remote', 'sweden'.
                      Standard: DEFAULT_LOCATIONS om inget anges.
        known_ids:    Set av source_id:n som redan finns i databasen. Om en hel sida
                      består av kända jobb stoppar vi pagineringen tidigt — ny content
                      kommer alltid först eftersom JobTech sorterar på pubdate-desc.
        resume_state: Dict {(keyword, location): last_offset} — börja om från dessa offsets.
                      Om en kombination är markerad 'completed' (offset >= total) hoppas den över.
        on_page:      Callback(keyword, location, page_num, total_pages, new_jobs) — anropas per sida.
        stop_flag:    Lista med ett bool-värde [False]. Sätt [True] utifrån för att avbryta.

    Returns:
        Lista av normaliserade job-dicts (deduplicerat på source_id).
    """
    if stop_flag is None:
        stop_flag = [False]
    if resume_state is None:
        resume_state = {}
    if locations is None:
        locations = DEFAULT_LOCATIONS
    if known_ids is None:
        known_ids = set()

    seen_ids: set[str] = set()
    results: list[dict] = []

    for keyword in keywords:
        for location in locations:
            if stop_flag[0]:
                return results

            resume_offset = resume_state.get((keyword, location), 0)
            resume_total = resume_state.get(f"total_{keyword}_{location}")

            # Hoppa över om vi redan är klara med den här kombinationen
            if resume_total is not None and resume_offset >= resume_total:
                continue

            offset = resume_offset
            page_num = (offset // PAGE_SIZE) + 1

            while True:
                if stop_flag[0]:
                    return results

                try:
                    data = _fetch_page(keyword, offset, location)
                except httpx.HTTPError as e:
                    # Felhantering: stanna och rapportera via on_page
                    if on_page:
                        on_page(keyword, location, page_num, page_num, [], error=str(e))
                    break

                hits = data.get("hits", [])
                total = data.get("total", {}).get("value", 0)
                total_pages = max(1, -(-total // PAGE_SIZE))  # ceil division

                page_jobs = []
                all_known = bool(hits)  # becomes False if no hits
                for hit in hits:
                    job = _normalize_hit(hit, is_remote_search=(location == "remote"))
                    sid = job["source_id"]
                    if sid and sid not in seen_ids:
                        seen_ids.add(sid)
                        if sid not in known_ids:
                            all_known = False
                            results.append(job)
                            page_jobs.append(job)
                        # else: already in DB — don't add, but keep all_known check going
                    else:
                        all_known = False  # empty/dup source_id — don't stop

                if on_page:
                    on_page(keyword, location, page_num, total_pages, page_jobs)

                offset += len(hits)
                page_num += 1

                # Stop early if the entire page was jobs we already have.
                # Since JobTech sorts newest-first, once we hit a full page of
                # known jobs there's nothing new further back.
                if all_known:
                    break

                completed = (
                    offset >= total or offset >= MAX_RESULTS_PER_QUERY or not hits
                )
                if completed:
                    break

    return results
