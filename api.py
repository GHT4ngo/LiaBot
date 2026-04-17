"""
api.py — FastAPI REST-lager för LiaBot.
Exponerar data från PostgreSQL-databasen för Lovable-frontend.

Starta: python api.py
Eller:  uvicorn api:app --reload --port 8001
"""

import os
import sys
import asyncio
from typing import Optional, Any
from datetime import datetime, date, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

import database as db
from sources import jobtech
from sources import web_scraper
from sources import job_boards
import analyzer

app = FastAPI(
    title="LiaBot API",
    description="Hitta LIA-praktikplatser för Data Engineering",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic-modeller ---

class JobOut(BaseModel):
    id: int
    source: str
    source_url: Optional[str]
    company_name: Optional[str]
    company_url: Optional[str]
    contact_person: Optional[str]
    contact_title: Optional[str]
    contact_email: Optional[str]
    contact_linkedin: Optional[str]
    job_title: Optional[str]
    job_description: Optional[str]
    ai_highlight: Optional[str]
    prerequisites: Optional[str]
    location: Optional[str]
    is_remote: Optional[bool]
    posted_date: Optional[date]
    relevant_period: Optional[str]
    start_date: Optional[date]
    is_relevant: Optional[bool]
    cold_contact: Optional[bool]
    relevance_note: Optional[str]
    # Spårningsfält
    tracking_status: Optional[str]
    lead_source: Optional[str]
    priority: Optional[int]
    date_sent: Optional[date]
    reply_received: Optional[bool]
    reply_date: Optional[date]
    next_step: Optional[str]
    user_comment: Optional[str]
    scraped_at: Optional[datetime]
    emailed_at: Optional[datetime]

    class Config:
        from_attributes = True


class JobPatch(BaseModel):
    tracking_status: Optional[str] = None
    lead_source: Optional[str] = None
    priority: Optional[int] = None
    contact_person: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    contact_linkedin: Optional[str] = None
    company_url: Optional[str] = None
    date_sent: Optional[date] = None
    reply_received: Optional[bool] = None
    reply_date: Optional[date] = None
    next_step: Optional[str] = None
    user_comment: Optional[str] = None
    relevant_period: Optional[str] = None
    start_date: Optional[date] = None


class SourceIn(BaseModel):
    name: str
    url: str


class SourceOut(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    last_run: Optional[datetime]

    class Config:
        from_attributes = True


class SearchStatus(BaseModel):
    status: str
    message: str


class KeywordsIn(BaseModel):
    keywords: list[str]


# In-memory loggsystem
_search_running = False
_search_log: list[str] = []        # kompat: används av /search/status
_stop_flag: list[bool] = [False]

from collections import deque
import threading
_log_lock = threading.Lock()
_log_buffer: deque = deque(maxlen=1000)  # {ts, msg, cat}


def _log(msg: str, cat: str = "system"):
    """Lägg till en loggpost i bufferten och skriv till stdout."""
    entry = {
        "ts":  datetime.now(timezone.utc).isoformat(),
        "msg": msg,
        "cat": cat,   # system | search | ai | success | error
    }
    with _log_lock:
        _log_buffer.append(entry)
    _search_log.append(msg)
    print(msg)


# --- Endpoints ---

@app.on_event("startup")
def on_startup():
    db.init_db()
    db.seed_default_sources(job_boards.DEFAULT_CAREER_SOURCES)
    _log("LiaBot API startad", "system")


@app.get("/logs", tags=["System"])
def get_logs(offset: int = Query(0, ge=0)):
    """Returnerar loggposter från in-memory-bufferten."""
    with _log_lock:
        items = list(_log_buffer)
    return {"entries": items[offset:], "total": len(items)}


@app.get("/jobs", response_model=list[JobOut], tags=["Jobb"])
def get_jobs(
    relevant: Optional[bool] = Query(None, description="True = bara relevanta"),
    uncontacted: bool = Query(False, description="True = bara ej kontaktade"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Hämtar jobb med valfria filter. Standard: alla jobb, paginerat."""
    relevant_only = relevant is True
    offset = (page - 1) * page_size
    return db.list_jobs(
        relevant_only=relevant_only,
        uncontacted_only=uncontacted,
        limit=page_size,
        offset=offset,
    )


@app.get("/jobs/{job_id}", response_model=JobOut, tags=["Jobb"])
def get_job(job_id: int):
    """Hämtar ett specifikt jobb med fullständig beskrivning."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Jobb hittades inte")
    return job


@app.post("/jobs/{job_id}/mark-emailed", tags=["Jobb"])
def mark_emailed(job_id: int):
    """Markerar ett jobb som kontaktat (emailed_at sätts till nu)."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Jobb hittades inte")
    db.mark_emailed(job_id)
    return {"ok": True, "job_id": job_id}


@app.patch("/jobs/{job_id}", response_model=JobOut, tags=["Jobb"])
def patch_job(job_id: int, body: JobPatch):
    """
    Uppdaterar spårningsfält på ett jobb (från frontend-dashboard).
    Skicka bara de fält som ska ändras.
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Jobb hittades inte")

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if fields:
        db.patch_job(job_id, fields)

    # Synka emailed_at om date_sent sätts och tracking_status → Skickat
    if "date_sent" in fields or body.tracking_status == "Skickat":
        db.mark_emailed(job_id)

    return db.get_job(job_id)


@app.get("/stats", tags=["Statistik"])
def get_stats():
    """Returnerar övergripande statistik."""
    total = db.count_jobs()
    relevant = db.count_jobs(relevant_only=True)
    uncontacted = db.count_jobs(relevant_only=True, uncontacted_only=True)
    return {
        "total_jobs":          total,
        "relevant_jobs":       relevant,
        "uncontacted_relevant": uncontacted,
    }


# --- Anpassade källor ---

@app.get("/sources", response_model=list[SourceOut], tags=["Källor"])
def get_sources():
    """Listar alla konfigurerade anpassade källor."""
    return db.list_sources(enabled_only=False)


@app.post("/sources", response_model=SourceOut, tags=["Källor"])
def add_source(body: SourceIn):
    """Lägger till en ny anpassad källa (webbsida att skrapa)."""
    new_id = db.add_source(body.name, body.url)
    sources = db.list_sources(enabled_only=False)
    for s in sources:
        if s["id"] == new_id:
            return s
    raise HTTPException(status_code=500, detail="Kunde inte skapa källa")


@app.patch("/sources/{source_id}/toggle", tags=["Källor"])
def toggle_source(source_id: int, enabled: bool):
    """Aktiverar eller inaktiverar en källa."""
    db.toggle_source(source_id, enabled)
    return {"ok": True, "source_id": source_id, "enabled": enabled}


# --- Sökord ---

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


def _write_env_var(key: str, value: str):
    """Skriver/uppdaterar en nyckel i .env-filen."""
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}\n")
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Kunde inte skriva .env ({key}): {e}")


def _write_keywords_to_env(keywords: list[str]):
    _write_env_var("SEARCH_KEYWORDS", ",".join(keywords))


@app.get("/keywords", tags=["Sökord"])
def get_keywords():
    """Returnerar sökord och sökavsikt."""
    raw = os.getenv("SEARCH_KEYWORDS", "")
    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    intent = os.getenv("SEARCH_INTENT", "")
    return {"keywords": keywords, "intent": intent}


@app.put("/keywords", tags=["Sökord"])
def update_keywords(body: KeywordsIn):
    """Sparar en ny lista med sökord (uppdaterar .env och minnet)."""
    cleaned = [k.strip() for k in body.keywords if k.strip()]
    os.environ["SEARCH_KEYWORDS"] = ",".join(cleaned)
    _write_keywords_to_env(cleaned)
    return {"keywords": cleaned}


class IntentIn(BaseModel):
    intent: str
    extra_context: Optional[str] = None


@app.post("/keywords/from-intent", tags=["Sökord"])
def keywords_from_intent(body: IntentIn):
    """
    Genererar sökord från fri-text sökavsikt via Ollama.
    Sparar sökavsikten och de genererade sökorden i .env.
    """
    # Spara avsikten oavsett om Ollama är tillgänglig
    os.environ["SEARCH_INTENT"] = body.intent
    _write_env_var("SEARCH_INTENT", body.intent)

    if not analyzer.check_ollama_available():
        raise HTTPException(status_code=503, detail="Ollama ej tillgänglig — starta Ollama och försök igen")

    extra = f"\nExtra kontext: {body.extra_context}" if body.extra_context else ""
    prompt = f"""Du hjälper en Data Engineering-student att hitta LIA-praktikplats i Sverige via JobTech API.

Sökavsikt: {body.intent}{extra}

Generera 12-15 konkreta sökord (blandning svenska och engelska) för JobTech API:s textsökning.
Regler:
- Fokusera på rollnamn och yrkesbenämningar
- Inkludera junior/praktik/trainee-varianter
- Undvik för breda ord som bara "data" eller "analytics"
- Varje sökord ska vara 1-4 ord

Svara ENBART med ett JSON-objekt:
{{"keywords": ["sökord1", "sökord2", "sökord3"]}}"""

    try:
        import ollama as _ol, re, json
        client = _ol.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        resp = client.generate(model=os.getenv("OLLAMA_MODEL", "llama3.2"), prompt=prompt)
        m = re.search(r"\{.*\}", resp.response, re.DOTALL)
        keywords = json.loads(m.group()).get("keywords", []) if m else []
        if not keywords:
            raise HTTPException(status_code=500, detail="Ollama returnerade inga sökord — försök igen")
        os.environ["SEARCH_KEYWORDS"] = ",".join(keywords)
        _write_keywords_to_env(keywords)
        _log(f"Sökord genererade från avsikt: {len(keywords)} st", "ai")
        return {"keywords": keywords, "intent": body.intent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/keywords/suggest", tags=["Sökord"])
def suggest_keywords(background_tasks: BackgroundTasks):
    """Låter Ollama föreslå nya sökord baserat på befintlig lista."""
    if not analyzer.check_ollama_available():
        raise HTTPException(status_code=503, detail="Ollama ej tillgänglig")

    current = os.getenv("SEARCH_KEYWORDS", "")
    prompt = f"""Du hjälper en Data Engineering-student att hitta LIA-praktik i Sverige.
Nuvarande sökord: {current}

Föreslå 8 ytterligare svenska och engelska sökord för JobTech API:s söktjänst som INTE redan finns i listan ovan.
Fokusera på: praktikroller, trainee-program, junior positioner inom data/BI/analytics.
Svara ENBART med ett JSON-objekt:
{{"suggestions": ["sökord1", "sökord2", "sökord3", "sökord4", "sökord5", "sökord6", "sökord7", "sökord8"]}}"""

    try:
        import ollama as _ol, re, json
        client = _ol.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        resp = client.generate(model=os.getenv("OLLAMA_MODEL", "llama3.2"), prompt=prompt)
        m = re.search(r"\{.*\}", resp.response, re.DOTALL)
        suggestions = json.loads(m.group()).get("suggestions", []) if m else []
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- System ---

@app.post("/system/restart", tags=["System"])
def restart_api():
    """Startar om API-processen via launcher (port 8003)."""
    import threading

    def _do_restart():
        import time, subprocess
        _log("Startar om API...", "system")
        time.sleep(0.5)
        try:
            import httpx as _hx
            _hx.post("http://localhost:8003/start", timeout=3)
        except Exception:
            # Launcher ej tillgänglig — starta direkt
            subprocess.Popen(
                [sys.executable, os.path.abspath(__file__)],
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
        os._exit(0)

    threading.Thread(target=_do_restart, daemon=True).start()
    return {"ok": True, "message": "Startar om..."}


# --- Sökning (bakgrundsprocess) ---

@app.post("/search", response_model=SearchStatus, tags=["Sökning"])
def trigger_search(background_tasks: BackgroundTasks, use_ai: bool = True):
    """
    Startar en sökning i bakgrunden.
    Resultat finns i /search/status och /jobs när klart.
    """
    global _search_running, _search_log
    if _search_running:
        return SearchStatus(status="running", message="Sökning pågår redan.")

    _search_log = []
    background_tasks.add_task(_run_search, use_ai=use_ai)
    return SearchStatus(status="started", message="Sökning startad i bakgrunden.")


@app.get("/search/status", tags=["Sökning"])
def search_status():
    """Returnerar status för pågående/senaste sökning."""
    return {
        "running": _search_running,
        "log":     _search_log[-50:],  # senaste 50 rader
    }


@app.post("/search/stop", response_model=SearchStatus, tags=["Sökning"])
def stop_search():
    """Stoppar pågående sökning (sätter stop-flagga)."""
    global _stop_flag
    if not _search_running:
        return SearchStatus(status="idle", message="Ingen sökning pågår.")
    _stop_flag[0] = True
    return SearchStatus(status="stopping", message="Stoppsignal skickad.")


@app.post("/jobs/{job_id}/refresh", response_model=JobOut, tags=["Jobb"])
def refresh_job(job_id: int, background_tasks: BackgroundTasks):
    """
    Uppdaterar ett jobb: hämtar ny data från JobTech (posted_date, period, mm)
    och kör om Ollama-analys i bakgrunden.
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Jobb hittades inte")

    # Re-fetch basic metadata from JobTech if applicable
    if job.get("source") == "jobtech" and job.get("source_id"):
        try:
            import httpx as _httpx
            from sources.jobtech import _normalize_hit as _nh
            resp = _httpx.get(
                f"https://jobsearch.api.jobtechdev.se/ad/{job['source_id']}",
                headers={"accept": "application/json"},
                timeout=10,
            )
            if resp.is_success:
                fresh = _nh(resp.json())
                fields = {}
                if fresh.get("posted_date"):
                    fields["posted_date"] = fresh["posted_date"]
                if fresh.get("relevant_period"):
                    fields["relevant_period"] = fresh["relevant_period"]
                if fresh.get("company_url") and not job.get("company_url"):
                    fields["company_url"] = fresh["company_url"]
                if fields:
                    db.patch_job(job_id, fields)
        except Exception as e:
            print(f"JobTech refresh fel: {e}")

    background_tasks.add_task(_analyze_single_job, job_id)
    return db.get_job(job_id)


@app.post("/jobs/{job_id}/analyze", tags=["Jobb"])
def analyze_job(job_id: int, background_tasks: BackgroundTasks):
    """Kör Ollama-analys på ett specifikt jobb (bakgrundsprocess)."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Jobb hittades inte")
    background_tasks.add_task(_analyze_single_job, job_id)
    return {"ok": True, "job_id": job_id, "message": "Analys startad i bakgrunden."}


def _analyze_single_job(job_id: int):
    job = db.get_job(job_id)
    if not job:
        return
    try:
        analyzed = analyzer.analyze_job(job)
        db.update_job_analysis(
            job_id,
            is_relevant=analyzed.get("is_relevant", False),
            relevance_note=analyzed.get("relevance_note"),
            contact_person=analyzed.get("contact_person"),
            contact_email=analyzed.get("contact_email"),
            ai_highlight=analyzed.get("ai_highlight"),
            prerequisites=analyzed.get("prerequisites"),
        )
        # Patch extra fields that update_job_analysis doesn't handle
        extra = {}
        if analyzed.get("relevant_period"):
            extra["relevant_period"] = analyzed["relevant_period"]
        if analyzed.get("start_date"):
            extra["start_date"] = analyzed["start_date"]
        if extra:
            db.patch_job(job_id, extra)
    except Exception as e:
        print(f"Analysfel för jobb {job_id}: {e}")


def _run_search(use_ai: bool = True):
    global _search_running, _search_log, _stop_flag
    _search_running = True
    _search_log = []
    _stop_flag = [False]

    try:
        keywords_raw = os.getenv(
            "SEARCH_KEYWORDS",
            "data engineer,data analyst,dataingenjör,BI-utvecklare,ETL"
        )
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

        if use_ai and not analyzer.check_ollama_available():
            _log(f"Ollama-modellen '{os.getenv('OLLAMA_MODEL')}' hittades inte. Sparar utan AI-analys.", "error")
            use_ai = False

        _log("Hämtar från JobTech (Platsbanken + 200 sajter)...", "search")
        jobs = jobtech.fetch_all(keywords, stop_flag=_stop_flag)
        _log(f"JobTech: {len(jobs)} annonser hämtade", "search")

        if not _stop_flag[0]:
            _log("Söker på Karriär.se, Blocket, Jobbsafari, Graduateland...", "search")
            board_jobs = job_boards.fetch_all_boards(
                keywords,
                stop_flag=_stop_flag,
                log=lambda msg: _log(msg, "search"),
            )
            _log(f"Jobbsajter: {len(board_jobs)} annonser hämtade", "search")
            jobs += board_jobs

        custom_sources = db.list_sources(enabled_only=True)
        if custom_sources and not _stop_flag[0]:
            _log(f"Skrapar {len(custom_sources)} karriärsidor...", "search")
            custom_jobs = web_scraper.scrape_all(custom_sources, verbose=False)
            jobs += custom_jobs
            for src in custom_sources:
                db.update_source_last_run(src["id"])

        new_count = 0
        duplicate_count = 0
        for i, job in enumerate(jobs, 1):
            if use_ai:
                _log(f"Analyserar ({i}/{len(jobs)}): {job.get('company_name', '?')} — {job.get('job_title', '?')[:50]}", "ai")
                job = analyzer.analyze_job(job)
            job_id = db.upsert_job(job)
            if job_id:
                new_count += 1
            else:
                duplicate_count += 1

        _log(f"Klart! {new_count} nya jobb sparade. {duplicate_count} redan i databasen.", "success")
    except Exception as e:
        _log(f"Fel under sökning: {e}", "error")
    finally:
        _search_running = False


# --- Setup / Health ---

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# Keys that are safe to expose to the frontend (no raw passwords)
_SAFE_KEYS = {"PG_HOST", "PG_PORT", "PG_DATABASE", "PG_USER",
              "OLLAMA_MODEL", "OLLAMA_BASE_URL", "API_HOST", "API_PORT"}
_SECRET_KEYS = {"PG_PASSWORD"}


def _read_env_file() -> dict[str, str]:
    """Parse the .env file into a dict, preserving all keys."""
    result: dict[str, str] = {}
    if not os.path.exists(ENV_PATH):
        return result
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _write_env_value(key: str, value: str):
    """Update or append a single key in the .env file."""
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
        return
    with open(ENV_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped == key:
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


@app.get("/setup/health", tags=["Setup"])
def setup_health():
    """Kontrollerar status för alla tjänster: PostgreSQL, Ollama, Git."""
    result = {}

    # PostgreSQL
    try:
        import database as _db
        conn = _db.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        result["postgres"] = {"ok": True, "message": "Ansluten"}
    except Exception as e:
        result["postgres"] = {"ok": False, "message": str(e)}

    # Ollama
    try:
        import httpx as _hx
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        r = _hx.get(f"{base}/api/tags", timeout=4)
        models = [m["name"] for m in r.json().get("models", [])]
        wanted = os.getenv("OLLAMA_MODEL", "llama3.2")
        ok = any(wanted in m for m in models)
        result["ollama"] = {
            "ok": ok,
            "message": f"Modell '{wanted}' {'hittad' if ok else 'saknas'}",
            "models": models,
        }
    except Exception as e:
        result["ollama"] = {"ok": False, "message": f"Ollama nås ej: {e}"}

    # Git
    try:
        import subprocess
        r = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            result["git"] = {"ok": True, "message": r.stdout.strip()}
        else:
            result["git"] = {"ok": False, "message": "Ej ett git-repo"}
    except Exception as e:
        result["git"] = {"ok": False, "message": str(e)}

    return result


@app.get("/setup/config", tags=["Setup"])
def get_config():
    """Returnerar nuvarande konfiguration (lösenord dolt)."""
    env = _read_env_file()
    config = {}
    for k in _SAFE_KEYS:
        config[k] = env.get(k, "")
    for k in _SECRET_KEYS:
        config[k] = "••••••••" if env.get(k) else ""
    return config


class ConfigUpdate(BaseModel):
    key: str
    value: str


@app.patch("/setup/config", tags=["Setup"])
def update_config(update: ConfigUpdate):
    """Uppdaterar ett konfigurationsvärde i .env-filen."""
    allowed = _SAFE_KEYS | _SECRET_KEYS
    if update.key not in allowed:
        raise HTTPException(status_code=400, detail=f"Okänd nyckel: {update.key}")
    # Don't overwrite secret with placeholder
    if update.key in _SECRET_KEYS and update.value.startswith("•"):
        return {"ok": True, "message": "Lösenord oförändrat"}
    _write_env_value(update.key, update.value)
    # Reload env so the running process picks up the change
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    return {"ok": True, "message": f"{update.key} uppdaterad"}


@app.post("/setup/update", tags=["Setup"])
def git_pull():
    """Kör git pull för att hämta senaste versionen från GitHub."""
    import subprocess
    try:
        r = subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=30
        )
        output = (r.stdout + r.stderr).strip()
        ok = r.returncode == 0
        return {"ok": ok, "output": output}
    except FileNotFoundError:
        return {"ok": False, "output": "git är inte installerat eller inte i PATH"}
    except Exception as e:
        return {"ok": False, "output": str(e)}


# --- Start ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8001)),
        reload=True,
    )
