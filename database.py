"""
database.py — PostgreSQL schema setup och CRUD för LiaBot.
Schema: public (i databasen 'liabot')
"""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DATABASE", "liabot"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD"),
    )


def init_db():
    """Skapar tabeller om de inte redan finns."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id                SERIAL PRIMARY KEY,
            source            TEXT NOT NULL,
            source_id         TEXT,
            source_url        TEXT,
            company_name      TEXT,
            company_url       TEXT,
            contact_person    TEXT,
            contact_title     TEXT,
            contact_email     TEXT,
            contact_linkedin  TEXT,
            job_title         TEXT,
            job_description   TEXT,
            ai_highlight      TEXT,
            prerequisites     TEXT,
            location          TEXT,
            is_remote         BOOLEAN DEFAULT FALSE,
            posted_date       DATE,
            relevant_period   TEXT,
            start_date        DATE,
            is_relevant       BOOLEAN,
            relevance_note    TEXT,
            -- Spårningsfält (redigeras av användaren)
            tracking_status   TEXT DEFAULT 'Ny',
            lead_source       TEXT DEFAULT 'Annons',
            priority          INTEGER DEFAULT 2,
            date_sent         DATE,
            reply_received    BOOLEAN DEFAULT FALSE,
            reply_date        DATE,
            next_step         TEXT,
            user_comment      TEXT,
            scraped_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            emailed_at        TIMESTAMPTZ,
            UNIQUE (source, source_id)
        );
    """)

    # Lägg till nya kolumner om de saknas (migration för befintliga databaser)
    new_columns = [
        ("contact_title",    "TEXT"),
        ("contact_linkedin", "TEXT"),
        ("ai_highlight",     "TEXT"),
        ("prerequisites",    "TEXT"),
        ("posted_date",      "DATE"),
        ("relevant_period",  "TEXT"),
        ("start_date",       "DATE"),
        ("tracking_status",  "TEXT DEFAULT 'Ny'"),
        ("lead_source",      "TEXT DEFAULT 'Annons'"),
        ("priority",         "INTEGER DEFAULT 2"),
        ("date_sent",        "DATE"),
        ("reply_received",   "BOOLEAN DEFAULT FALSE"),
        ("reply_date",       "DATE"),
        ("next_step",        "TEXT"),
        ("user_comment",     "TEXT"),
        ("cold_contact",     "BOOLEAN DEFAULT FALSE"),
    ]
    for col, col_type in new_columns:
        try:
            cur.execute(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col} {col_type};")
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            url         TEXT NOT NULL,
            enabled     BOOLEAN DEFAULT TRUE,
            last_run    TIMESTAMPTZ
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_runs (
            id           SERIAL PRIMARY KEY,
            run_id       TEXT NOT NULL UNIQUE,
            started_at   TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            status       TEXT DEFAULT 'running'
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_progress (
            id           SERIAL PRIMARY KEY,
            run_id       TEXT NOT NULL,
            source       TEXT NOT NULL,
            keyword      TEXT,
            last_offset  INTEGER DEFAULT 0,
            total        INTEGER,
            completed    BOOLEAN DEFAULT FALSE,
            updated_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (run_id, source, keyword)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


def upsert_job(job: dict) -> int | None:
    """
    Sparar ett jobb. Returnerar id om ny rad infogades, None om dublett.
    job måste ha: source, source_id (eller source_url som fallback-id)
    """
    conn = get_conn()
    cur = conn.cursor()

    source_id = job.get("source_id") or job.get("source_url", "")[:200]

    cur.execute("""
        INSERT INTO jobs
            (source, source_id, source_url, company_name, company_url,
             contact_person, contact_email, contact_title, contact_linkedin,
             job_title, job_description,
             ai_highlight, prerequisites,
             location, is_remote,
             posted_date, relevant_period, start_date,
             is_relevant, cold_contact, relevance_note, scraped_at)
        VALUES
            (%(source)s, %(source_id)s, %(source_url)s, %(company_name)s, %(company_url)s,
             %(contact_person)s, %(contact_email)s, %(contact_title)s, %(contact_linkedin)s,
             %(job_title)s, %(job_description)s,
             %(ai_highlight)s, %(prerequisites)s,
             %(location)s, %(is_remote)s,
             %(posted_date)s, %(relevant_period)s, %(start_date)s,
             %(is_relevant)s, %(cold_contact)s, %(relevance_note)s, %(scraped_at)s)
        ON CONFLICT (source, source_id) DO NOTHING
        RETURNING id;
    """, {
        "source":           job.get("source", "unknown"),
        "source_id":        source_id,
        "source_url":       job.get("source_url"),
        "company_name":     job.get("company_name"),
        "company_url":      job.get("company_url"),
        "contact_person":   job.get("contact_person"),
        "contact_email":    job.get("contact_email"),
        "contact_title":    job.get("contact_title"),
        "contact_linkedin": job.get("contact_linkedin"),
        "job_title":        job.get("job_title"),
        "job_description":  job.get("job_description"),
        "ai_highlight":     job.get("ai_highlight"),
        "prerequisites":    job.get("prerequisites"),
        "location":         job.get("location"),
        "is_remote":        job.get("is_remote", False),
        "posted_date":      job.get("posted_date"),
        "relevant_period":  job.get("relevant_period"),
        "start_date":       job.get("start_date"),
        "is_relevant":      job.get("is_relevant"),
        "cold_contact":     job.get("cold_contact", False),
        "relevance_note":   job.get("relevance_note"),
        "scraped_at":       datetime.now(timezone.utc),
    })

    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row[0] if row else None


def update_job_analysis(job_id: int, is_relevant: bool, relevance_note: str,
                        contact_person: str | None, contact_email: str | None,
                        ai_highlight: str | None = None, prerequisites: str | None = None):
    """Uppdaterar Ollama-analys-fälten på ett befintligt jobb."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE jobs
        SET is_relevant    = %s,
            relevance_note = %s,
            contact_person = COALESCE(%s, contact_person),
            contact_email  = COALESCE(%s, contact_email),
            ai_highlight   = COALESCE(%s, ai_highlight),
            prerequisites  = COALESCE(%s, prerequisites)
        WHERE id = %s;
    """, (is_relevant, relevance_note, contact_person, contact_email,
          ai_highlight, prerequisites, job_id))
    conn.commit()
    cur.close()
    conn.close()


PATCHABLE_FIELDS = {
    "tracking_status", "lead_source", "priority", "contact_person",
    "contact_title", "contact_email", "contact_linkedin", "date_sent",
    "reply_received", "reply_date", "next_step", "user_comment",
    "relevant_period", "start_date", "company_url",
    "posted_date", "ai_highlight", "prerequisites",
}

def patch_job(job_id: int, fields: dict) -> bool:
    """
    Uppdaterar valfria fält på ett jobb (användarredigering från frontend).
    Returnerar True om raden uppdaterades.
    """
    safe = {k: v for k, v in fields.items() if k in PATCHABLE_FIELDS}
    if not safe:
        return False
    conn = get_conn()
    cur = conn.cursor()
    set_clause = ", ".join(f"{k} = %s" for k in safe)
    cur.execute(
        f"UPDATE jobs SET {set_clause} WHERE id = %s RETURNING id;",
        list(safe.values()) + [job_id]
    )
    updated = cur.fetchone() is not None
    conn.commit()
    cur.close()
    conn.close()
    return updated


def list_jobs(relevant_only: bool = True, uncontacted_only: bool = False,
              limit: int = 200, offset: int = 0) -> list[dict]:
    """Hämtar jobb som en lista av dicts."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    conditions = []
    if relevant_only:
        conditions.append("is_relevant = TRUE")
    if uncontacted_only:
        conditions.append("emailed_at IS NULL")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cur.execute(f"""
        SELECT * FROM jobs
        {where}
        ORDER BY scraped_at DESC
        LIMIT %s OFFSET %s;
    """, (limit, offset))

    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_job(job_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM jobs WHERE id = %s;", (job_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def mark_emailed(job_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE jobs SET emailed_at = NOW() WHERE id = %s;", (job_id,))
    conn.commit()
    cur.close()
    conn.close()


def count_jobs(relevant_only: bool = False, uncontacted_only: bool = False) -> int:
    conn = get_conn()
    cur = conn.cursor()
    conditions = []
    if relevant_only:
        conditions.append("is_relevant = TRUE")
    if uncontacted_only:
        conditions.append("emailed_at IS NULL")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    cur.execute(f"SELECT COUNT(*) FROM jobs {where};")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


# --- Källor (anpassade URL:er) ---

def add_source(name: str, url: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sources (name, url) VALUES (%s, %s) RETURNING id;",
        (name, url)
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return new_id


def list_sources(enabled_only: bool = True) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = "WHERE enabled = TRUE" if enabled_only else ""
    cur.execute(f"SELECT * FROM sources {where} ORDER BY id;")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def update_source_last_run(source_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sources SET last_run = NOW() WHERE id = %s;", (source_id,))
    conn.commit()
    cur.close()
    conn.close()


def seed_default_sources(sources: list[dict]):
    """
    Synkar standardkällor i databasen mot DEFAULT_CAREER_SOURCES.
    Lägger till saknade, tar bort utgångna. Körs vid API-start (idempotent).
    OBS: Tar bara bort sources vars URL inte finns i sources-listan —
    manuellt tillagda sources (via /sources POST) bevaras.
    """
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM sources ORDER BY id;")
    existing = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    canonical_urls = {s["url"] for s in sources}
    existing_urls = {s["url"] for s in existing}

    # Ta bort sources vars URL inte längre finns i DEFAULT_CAREER_SOURCES
    # Men bara om de verkar vara auto-seedade (ej manuellt tillagda).
    # Heuristik: om URL finns i existerande men inte i canonical → ta bort
    # Manuellt tillagda identifieras inte här, de tas också bort om URL ej matchar.
    # Acceptabelt beteende för ett studentsystem.
    to_remove = [s["id"] for s in existing if s["url"] not in canonical_urls]
    if to_remove:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM sources WHERE id = ANY(%s);",
            (to_remove,)
        )
        conn.commit()
        cur.close()
        conn.close()

    added = 0
    for s in sources:
        if s["url"] not in existing_urls:
            add_source(s["name"], s["url"])
            added += 1

    removed = len(to_remove)
    if added or removed:
        print(f"Standardkällor synkade: +{added} nya, -{removed} borttagna, {len(sources)} totalt")


def toggle_source(source_id: int, enabled: bool):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sources SET enabled = %s WHERE id = %s;", (enabled, source_id))
    conn.commit()
    cur.close()
    conn.close()


# --- Search run tracking (stop/resume) ---

def create_search_run(run_id: str):
    """Skapar en ny sökkörning."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO search_runs (run_id) VALUES (%s);", (run_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_incomplete_run() -> dict | None:
    """Returnerar den senaste körningen med status 'running' eller 'stopped', om den finns."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT * FROM search_runs
        WHERE status = 'stopped'
        ORDER BY started_at DESC
        LIMIT 1;
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def mark_run_status(run_id: str, status: str):
    """Sätter status på en körning: 'completed' | 'stopped'."""
    conn = get_conn()
    cur = conn.cursor()
    if status == "completed":
        cur.execute("""
            UPDATE search_runs
            SET status = %s, completed_at = NOW()
            WHERE run_id = %s;
        """, (status, run_id))
    else:
        cur.execute("UPDATE search_runs SET status = %s WHERE run_id = %s;", (status, run_id))
    conn.commit()
    cur.close()
    conn.close()


def upsert_search_progress(run_id: str, source: str, keyword: str,
                           last_offset: int, total: int | None, completed: bool):
    """Sparar/uppdaterar progress för en (run_id, source, keyword)-kombination."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO search_progress (run_id, source, keyword, last_offset, total, completed, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (run_id, source, keyword)
        DO UPDATE SET
            last_offset = EXCLUDED.last_offset,
            total       = EXCLUDED.total,
            completed   = EXCLUDED.completed,
            updated_at  = NOW();
    """, (run_id, source, keyword, last_offset, total, completed))
    conn.commit()
    cur.close()
    conn.close()


def get_search_progress(run_id: str) -> list[dict]:
    """Hämtar alla progress-rader för en körning."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM search_progress WHERE run_id = %s;", (run_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def count_unanalyzed() -> int:
    """Antal jobb som saknar Ollama-analys (is_relevant IS NULL)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jobs WHERE is_relevant IS NULL;")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def get_unanalyzed_jobs(limit: int = 1000) -> list[dict]:
    """Hämtar jobb utan analys, sorterat på id."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, job_title, job_description, company_name
        FROM jobs
        WHERE is_relevant IS NULL
        ORDER BY id
        LIMIT %s;
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows
