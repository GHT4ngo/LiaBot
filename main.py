"""
main.py — CLI för LiaBot med Rich terminal UI.

Kommandon:
  python main.py search              Hämta + analysera (med Ollama)
  python main.py search --no-ai      Hämta utan Ollama
  python main.py list                Visa relevanta jobb (Rich-tabell)
  python main.py list --all          Visa alla jobb
  python main.py add-source NAME URL Lägg till anpassad webbkälla
  python main.py sources             Lista sparade källor
  python main.py export FILE.csv     Exportera till CSV
  python main.py mark-emailed ID     Markera jobb som kontaktat
  python main.py init-db             Skapa databastabeller
"""

import os
import sys
import csv
import signal
import uuid
import argparse
from datetime import datetime

# Tvinga UTF-8 på Windows-terminaler som annars kör cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn
from rich.text import Text
from rich.rule import Rule
from rich import box

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

import database as db
from sources import jobtech
from sources import web_scraper
import analyzer

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

def _keywords() -> list[str]:
    raw = os.getenv(
        "SEARCH_KEYWORDS",
        "data engineer,data analyst,dataingenjör,BI-utvecklare,ETL"
    )
    return [k.strip() for k in raw.split(",") if k.strip()]


def _header(run_id: str = "", started: str = "") -> Panel:
    parts = ["[bold cyan]LiaBot[/] — LIA-sökning för Data Engineering"]
    if run_id:
        parts.append(f"  Körning [dim]{run_id[:8]}[/]  ·  Startad [dim]{started}[/]")
    return Panel("\n".join(parts), border_style="cyan", padding=(0, 2))


# ---------------------------------------------------------------------------
# cmd_init_db
# ---------------------------------------------------------------------------

def cmd_init_db():
    db.init_db()
    console.print("[green]✓[/] Databas initialiserad.")


# ---------------------------------------------------------------------------
# cmd_search
# ---------------------------------------------------------------------------

def cmd_search(use_ai: bool = True):
    db.init_db()
    keywords = _keywords()

    # --- Ollama-kontroll ---
    if use_ai:
        if not analyzer.check_ollama_available():
            model = os.getenv("OLLAMA_MODEL", "llama3.2")
            console.print(f"[yellow]Varning:[/] Ollama-modellen [bold]{model}[/] hittades inte.")
            console.print(f"  Kör: [cyan]ollama pull {model}[/]")
            console.print("  Fortsätter utan AI-analys.")
            use_ai = False

    # --- Resume? ---
    run_id = str(uuid.uuid4())
    resume_state: dict = {}
    incomplete = db.get_incomplete_run()

    if incomplete:
        ts = str(incomplete.get("started_at", ""))[:16]
        old_id = incomplete["run_id"][:8]
        console.print(
            f"\n[yellow]Ofullständig körning hittades[/] "
            f"([dim]{old_id}[/] startad {ts})"
        )
        answer = console.input("  Fortsätt där den slutade? [[bold]J[/]/n]: ").strip().lower()

        if answer in ("", "j", "ja", "y", "yes"):
            run_id = incomplete["run_id"]
            progress_rows = db.get_search_progress(run_id)
            for row in progress_rows:
                key = (row["keyword"], row["source"].replace("jobtech_", ""))
                resume_state[key] = row["last_offset"]
                if row["completed"] and row["total"]:
                    resume_state[f"total_{row['keyword']}_{row['source'].replace('jobtech_', '')}"] = row["total"]
            console.print(
                f"  [green]Fortsätter[/] körning [dim]{run_id[:8]}[/] "
                f"({len(progress_rows)} kombinationer sparade)"
            )
            db.mark_run_status(run_id, "running")
        else:
            db.mark_run_status(incomplete["run_id"], "stopped")
            console.print("  Startar ny sökning.")

    db.create_search_run(run_id)
    started_str = datetime.now().strftime("%H:%M:%S")

    # --- Stop-flag för Ctrl+C ---
    stop_flag = [False]

    def _on_sigint(sig, frame):
        stop_flag[0] = True

    signal.signal(signal.SIGINT, _on_sigint)

    # --- State för Live-tabellen ---
    # rows: list of dicts med keyword, location, status, pages, found, total_pages
    combinations = [(kw, loc) for kw in keywords for loc in ("stockholm", "remote")]
    row_state: dict[tuple, dict] = {}
    for kw, loc in combinations:
        resumed_offset = resume_state.get((kw, loc), 0)
        row_state[(kw, loc)] = {
            "keyword":   kw,
            "location":  loc,
            "status":    "skip" if resume_state.get(f"total_{kw}_{loc}") else "wait",
            "page":      (resumed_offset // 100) + 1 if resumed_offset else 1,
            "total_pages": "?",
            "found":     0,
            "error":     None,
        }

    saved_count = [0]
    dupe_count = [0]
    current_combo = [("", "")]

    def _build_fetch_table() -> Table:
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        t.add_column("", width=2)
        t.add_column("Nyckelord", style="white", min_width=22)
        t.add_column("Plats", width=10)
        t.add_column("Sida", width=8)
        t.add_column("Hittade", width=8, justify="right")
        t.add_column("Status", width=14)

        for kw, loc in combinations:
            s = row_state[(kw, loc)]
            st = s["status"]

            if st == "skip":
                icon = "[dim]–[/]"
                page_str = "—"
                found_str = f"[dim]{s['found']}[/]"
                status_str = "[dim]hoppad (klar)[/]"
            elif st == "done":
                icon = "[green]✓[/]"
                page_str = f"{s['page'] - 1}/{s['total_pages']}"
                found_str = f"[green]{s['found']}[/]"
                status_str = "[green]klar[/]"
            elif st == "running":
                icon = "[cyan]⠸[/]"
                page_str = f"{s['page']}/{s['total_pages']}"
                found_str = str(s["found"])
                status_str = f"[cyan]sida {s['page']}...[/]"
            elif st == "error":
                icon = "[red]✗[/]"
                page_str = "—"
                found_str = str(s["found"])
                status_str = f"[red]{str(s['error'])[:18]}[/]"
            else:  # wait
                icon = "[dim]○[/]"
                page_str = "—"
                found_str = "—"
                status_str = "[dim]väntar[/]"

            loc_label = "Stockholm" if loc == "stockholm" else "Distans"
            t.add_row(icon, kw, loc_label, page_str, found_str, status_str)

        return t

    def _footer_text() -> Text:
        txt = Text()
        txt.append(f"  Sparade: ", style="dim")
        txt.append(f"{saved_count[0]} nya", style="green bold")
        txt.append("  ·  Dubbletter: ", style="dim")
        txt.append(f"{dupe_count[0]}", style="dim")
        txt.append("  ·  ", style="dim")
        txt.append("Ctrl+C = pausa och spara", style="dim italic")
        return txt

    def _build_live_renderable():
        from rich.console import Group
        return Group(
            _header(run_id, started_str),
            Rule(" JOBTECH API  (Arbetsförmedlingen / Platsbanken)", style="cyan", align="left"),
            _build_fetch_table(),
            _footer_text(),
        )

    def on_page(keyword, location, page_num, total_pages, new_jobs, error=None):
        s = row_state[(keyword, location)]
        if error:
            s["status"] = "error"
            s["error"] = error
            return

        s["status"] = "running"
        s["page"] = page_num + 1
        s["total_pages"] = total_pages
        s["found"] += len(new_jobs)
        current_combo[0] = (keyword, location)

        # Spara till DB direkt (per sida)
        for job in new_jobs:
            job_id = db.upsert_job(job)
            if job_id:
                saved_count[0] += 1
            else:
                dupe_count[0] += 1

        # Uppdatera search_progress
        completed = (page_num >= total_pages)
        db.upsert_search_progress(
            run_id=run_id,
            source=f"jobtech_{location}",
            keyword=keyword,
            last_offset=page_num * 100,
            total=total_pages * 100,
            completed=completed,
        )
        if completed:
            s["status"] = "done"

    # --- FETCH-fas med Live ---
    console.print()
    with Live(_build_live_renderable(), console=console, refresh_per_second=4) as live:
        def on_page_live(keyword, location, page_num, total_pages, new_jobs, error=None):
            on_page(keyword, location, page_num, total_pages, new_jobs, error)
            live.update(_build_live_renderable())

        jobtech.fetch_all(
            keywords=keywords,
            resume_state=resume_state,
            on_page=on_page_live,
            stop_flag=stop_flag,
        )

        # Markera alla "running" som done när fetch är klar
        for kw, loc in combinations:
            if row_state[(kw, loc)]["status"] == "running":
                row_state[(kw, loc)]["status"] = "done"
        live.update(_build_live_renderable())

    # --- Stoppad? ---
    if stop_flag[0]:
        db.mark_run_status(run_id, "stopped")
        console.print()
        console.print(Panel(
            f"[yellow]Sökning pausad.[/]\n"
            f"  Sparade [bold]{saved_count[0]}[/] nya annonser.\n"
            f"  Kör [cyan]python main.py search[/] för att fortsätta.",
            border_style="yellow"
        ))
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        return

    # --- Anpassade webb-källor ---
    custom_sources = db.list_sources(enabled_only=True)
    if custom_sources:
        console.print(f"\n [bold]ANPASSADE KÄLLOR[/]  ({len(custom_sources)} st)")
        for src in custom_sources:
            with console.status(f"  Skrapar [cyan]{src['name']}[/]..."):
                job = web_scraper.scrape_url(src["url"], source_name=src["name"])
                if job:
                    job_id = db.upsert_job(job)
                    status = "[green]sparad[/]" if job_id else "[dim]dublett[/]"
                    console.print(f"  ✓ {src['name']}  {status}")
                else:
                    console.print(f"  [red]✗[/] {src['name']}  ingen data")
            db.update_source_last_run(src["id"])
    else:
        console.print(
            "\n [dim]Inga anpassade källor. "
            "Lägg till: [cyan]python main.py add-source \"Namn\" URL[/][/]"
        )

    # --- OLLAMA-analys ---
    if use_ai:
        unanalyzed = db.get_unanalyzed_jobs(limit=2000)
        if unanalyzed:
            console.print()
            model = os.getenv("OLLAMA_MODEL", "llama3.2")
            console.print(f" [bold]OLLAMA ANALYS[/]  ({model})")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=30),
                MofNCompleteColumn(),
                TextColumn("[dim]{task.fields[company]}[/]"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "  Analyserar",
                    total=len(unanalyzed),
                    company="",
                )

                for job_row in unanalyzed:
                    if stop_flag[0]:
                        break

                    company = job_row.get("company_name") or ""
                    progress.update(task, company=company[:30])

                    analyzed = analyzer.analyze_job(job_row)
                    db.update_job_analysis(
                        job_id=job_row["id"],
                        is_relevant=analyzed["is_relevant"],
                        relevance_note=analyzed["relevance_note"],
                        contact_person=analyzed["contact_person"],
                        contact_email=analyzed["contact_email"],
                    )
                    progress.advance(task)

    # --- Klar ---
    db.mark_run_status(run_id, "completed")
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    total_relevant = db.count_jobs(relevant_only=True)
    uncontacted = db.count_jobs(relevant_only=True, uncontacted_only=True)

    console.print()
    console.print(Panel(
        f"[green]✓ Sökning klar![/]\n"
        f"  Nya annonser sparade: [bold]{saved_count[0]}[/]\n"
        f"  Relevanta (totalt): [bold]{total_relevant}[/]\n"
        f"  Ej kontaktade: [bold]{uncontacted}[/]\n\n"
        f"  Visa lista: [cyan]python main.py list[/]",
        border_style="green"
    ))


# ---------------------------------------------------------------------------
# cmd_list
# ---------------------------------------------------------------------------

def cmd_list(show_all: bool = False):
    jobs = db.list_jobs(
        relevant_only=not show_all,
        uncontacted_only=False,
        limit=500,
    )

    if not jobs:
        msg = "Inga jobb hittades." if show_all else \
              "Inga relevanta jobb. Prova: [cyan]python main.py list --all[/]"
        console.print(f"\n[yellow]{msg}[/]")
        return

    label = "ALLA JOBB" if show_all else "RELEVANTA JOBB"
    t = Table(
        title=f"{label} — {len(jobs)} st",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    t.add_column("ID",      width=5,  justify="right", style="dim")
    t.add_column("Företag", min_width=20, max_width=28)
    t.add_column("Titel",   min_width=22, max_width=32)
    t.add_column("Plats",   width=12)
    t.add_column("Kontakt", min_width=18, max_width=25)
    t.add_column("Status",  width=14)

    for j in jobs:
        is_rel = j.get("is_relevant")
        emailed = j.get("emailed_at")

        if is_rel is True:
            status_str = "[green]✓ Relevant[/]"
            row_style = ""
        elif is_rel is False:
            status_str = "[red]✗ Ej relevant[/]"
            row_style = "dim"
        else:
            status_str = "[yellow]? Ej analyserad[/]"
            row_style = ""

        if emailed:
            status_str = "[dim]✉ Skickat[/]"
            row_style = "dim"

        company = j.get("company_name") or "—"
        title = j.get("job_title") or "—"
        loc = j.get("location") or ("Distans" if j.get("is_remote") else "—")
        contact = j.get("contact_email") or j.get("contact_person") or "—"

        t.add_row(
            str(j["id"]),
            company,
            title,
            loc,
            contact,
            status_str,
            style=row_style,
        )

    console.print()
    console.print(t)
    console.print(
        f"\n  [dim]Visa detalj: [cyan]python main.py list --all[/]  ·  "
        f"Markera kontaktat: [cyan]python main.py mark-emailed ID[/][/]"
    )


# ---------------------------------------------------------------------------
# cmd_add_source / cmd_sources
# ---------------------------------------------------------------------------

def cmd_add_source(name: str, url: str):
    source_id = db.add_source(name, url)
    console.print(f"[green]✓[/] Källa tillagd (ID {source_id}): [bold]{name}[/] — {url}")


def cmd_sources():
    sources = db.list_sources(enabled_only=False)
    if not sources:
        console.print(
            "\n[yellow]Inga anpassade källor.[/] "
            "Lägg till: [cyan]python main.py add-source \"Namn\" URL[/]"
        )
        return

    t = Table(title=f"Anpassade källor — {len(sources)} st", box=box.ROUNDED,
              header_style="bold cyan")
    t.add_column("ID",     width=4, justify="right", style="dim")
    t.add_column("Namn",   min_width=20)
    t.add_column("URL",    min_width=30)
    t.add_column("Status", width=9)
    t.add_column("Senast körde", width=18)

    for s in sources:
        enabled = "[green]aktiv[/]" if s.get("enabled") else "[dim]inaktiv[/]"
        last = str(s.get("last_run") or "—")[:16]
        t.add_row(str(s["id"]), s["name"], s["url"], enabled, last)

    console.print()
    console.print(t)


# ---------------------------------------------------------------------------
# cmd_export
# ---------------------------------------------------------------------------

def cmd_export(filepath: str):
    jobs = db.list_jobs(relevant_only=False, uncontacted_only=False, limit=5000)
    if not jobs:
        console.print("[yellow]Inga jobb att exportera.[/]")
        return

    fieldnames = [
        "id", "company_name", "company_url", "job_title", "location",
        "is_remote", "contact_person", "contact_email", "source_url",
        "is_relevant", "relevance_note", "emailed_at", "scraped_at"
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)

    console.print(f"[green]✓[/] {len(jobs)} jobb exporterade till [cyan]{filepath}[/]")


# ---------------------------------------------------------------------------
# cmd_mark_emailed
# ---------------------------------------------------------------------------

def cmd_mark_emailed(job_id: int):
    job = db.get_job(job_id)
    if not job:
        console.print(f"[red]Inget jobb med ID {job_id}.[/]")
        return
    db.mark_emailed(job_id)
    console.print(
        f"[green]✓[/] Jobb {job_id} "
        f"([bold]{job.get('company_name') or 'okänt'}[/]) markerat som kontaktat."
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="LiaBot — hitta LIA-praktikplatser för Data Engineering"
    )
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="Hämta nya annonser och analysera")
    p_search.add_argument("--no-ai", action="store_true",
                          help="Skippa Ollama-analys")

    p_list = sub.add_parser("list", help="Visa sparade jobb")
    p_list.add_argument("--all", action="store_true", dest="show_all",
                        help="Visa alla jobb, inte bara relevanta")

    p_src = sub.add_parser("add-source", help="Lägg till anpassad webbkälla")
    p_src.add_argument("name")
    p_src.add_argument("url")

    sub.add_parser("sources",      help="Lista anpassade källor")
    sub.add_parser("init-db",      help="Skapa databastabeller")

    p_exp = sub.add_parser("export", help="Exportera jobb till CSV")
    p_exp.add_argument("file")

    p_mark = sub.add_parser("mark-emailed", help="Markera jobb som kontaktat")
    p_mark.add_argument("id", type=int)

    args = parser.parse_args()

    if args.command == "search":
        cmd_search(use_ai=not args.no_ai)
    elif args.command == "list":
        cmd_list(show_all=args.show_all)
    elif args.command == "add-source":
        db.init_db()
        cmd_add_source(args.name, args.url)
    elif args.command == "sources":
        db.init_db()
        cmd_sources()
    elif args.command == "export":
        cmd_export(args.file)
    elif args.command == "mark-emailed":
        cmd_mark_emailed(args.id)
    elif args.command == "init-db":
        cmd_init_db()
    else:
        # Visa hjälp med Rich-panel
        console.print(Panel(
            "[bold cyan]LiaBot[/] — hitta LIA-praktikplatser för Data Engineering\n\n"
            "  [cyan]python main.py search[/]              Hämta + analysera\n"
            "  [cyan]python main.py search --no-ai[/]      Hämta utan Ollama\n"
            "  [cyan]python main.py list[/]                Visa relevanta jobb\n"
            "  [cyan]python main.py list --all[/]          Visa alla jobb\n"
            "  [cyan]python main.py add-source Namn URL[/] Lägg till källa\n"
            "  [cyan]python main.py sources[/]             Lista källor\n"
            "  [cyan]python main.py export jobb.csv[/]     Exportera till CSV\n"
            "  [cyan]python main.py mark-emailed ID[/]     Markera kontaktat",
            title="Kommandon",
            border_style="cyan",
        ))


if __name__ == "__main__":
    main()
