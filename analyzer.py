"""
analyzer.py — Ollama-integration för relevansbedömning och kontaktextraktion.

Ett enda LLM-anrop per jobb täcker:
  - is_relevant:    direkt LIA/praktik-roll
  - cold_contact:   företag med datateam som troligen tar emot praktikant (ej konsult)
  - reason, ai_highlight, prerequisites, contact_person, contact_email,
    relevant_period, start_date
"""

import os
import json
import re
from datetime import datetime
import ollama
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def _call_ollama(prompt: str) -> str:
    client = ollama.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    response = client.generate(model=MODEL, prompt=prompt)
    return response.response.strip()


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _safe_date(raw) -> str | None:
    """Returnerar YYYY-MM-DD om raw är ett giltigt datum, annars None."""
    if not raw:
        return None
    try:
        datetime.strptime(str(raw).strip(), "%Y-%m-%d")
        return str(raw).strip()
    except ValueError:
        return None


def analyze_job(job: dict) -> dict:
    """
    Kör ett enda Ollama-anrop som täcker all analys:
      - Relevansbedömning (direkt LIA-roll)
      - Cold-contact-bedömning (företag med datateam, ej konsultbolag)
      - AI-highlight, prerequisites, kontaktinfo, period, startdatum
    """
    title = job.get("job_title", "")
    description = (job.get("job_description") or "")[:2500]

    prompt = f"""Du bedömer en jobbannons för en Data Engineering-student som söker LIA-praktik
(6 månader, december–maj) i Stockholm eller på distans.
Studenten kan: SQL, Python, dbt, Airflow, PostgreSQL, grundläggande ML, BI-verktyg.

Jobbtitel: {title}
Annonstext:
{description}

Svara ENBART med ett JSON-objekt:
{{
  "relevant": true/false,
  "cold_contact": true/false,
  "reason": "Max 2 meningar på svenska om varför relevant eller ej.",
  "ai_highlight": "De 2-3 meningar ur annonsen som bäst motiverar relevansen, eller null om ej relevant.",
  "prerequisites": "Krav/förkunskaper från annonsen, max 5, separerade med semikolon. Null om inga.",
  "contact_person": "Namn Efternamn eller null",
  "contact_email": "email@exempel.se eller null",
  "relevant_period": "T.ex. 'Dec 2025 – Maj 2026' eller null",
  "start_date": "YYYY-MM-DD eller null"
}}

REGLER för relevant:
- true om: Data Engineer, Data Analyst, BI-utvecklare, Analytics Engineer, ETL/ELT, datapipeline, praktikant/trainee inom data.
- false om: mjukvaruutvecklare utan datafokus, säljare, ekonom, HR, kundtjänst.

REGLER för cold_contact (oberoende av relevant):
- true om: företaget har ett eget datateam och TROLIGEN kan ta emot en 6-månaders praktikant.
  Tecken: nämner internt datateam, data platform, warehouse, dashboards som egna produkter.
- false om: konsultbolag som rekryterar åt okänd kund, inget datateam nämns,
  eller rollen kräver 5+ år erfarenhet utan junior-spår."""

    try:
        response = _call_ollama(prompt)
        data = _extract_json(response)

        email = data.get("contact_email") or None
        if email and "@" not in email:
            email = None

        return {
            **job,
            "is_relevant":    bool(data.get("relevant", False)),
            "cold_contact":   bool(data.get("cold_contact", False)),
            "relevance_note": data.get("reason") or "",
            "ai_highlight":   data.get("ai_highlight") or None,
            "prerequisites":  data.get("prerequisites") or None,
            "contact_person": data.get("contact_person") or job.get("contact_person"),
            "contact_email":  email or job.get("contact_email"),
            "relevant_period": data.get("relevant_period") or job.get("relevant_period"),
            "start_date":     _safe_date(data.get("start_date")) or job.get("start_date"),
        }
    except Exception as e:
        return {
            **job,
            "is_relevant":  False,
            "cold_contact": False,
            "relevance_note": f"Analysfel: {e}",
        }


def check_ollama_available() -> bool:
    try:
        client = ollama.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        models = client.list()
        model_names = [m.model for m in models.models]
        return any(MODEL in name for name in model_names)
    except Exception:
        return False
