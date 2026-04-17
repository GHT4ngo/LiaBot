# LiaBot

**Automatisk LIA-sökning för Data Engineering-studenter**

LiaBot söker automatiskt igenom svenska jobbsajter och karriärsidor efter LIA-praktikplatser (Lärande i Arbete), analyserar annonserna med en lokal AI-modell och presenterar resultaten i ett webbaserat dashboard.

---

## Vad den gör

- Söker JobTech API (Arbetsförmedlingen/Platsbanken — täcker 200+ svenska jobbsajter)
- Skrapar karriärsidor hos 30+ svenska techbolag och konsultfirmor
- Analyserar varje annons med Ollama (lokal AI — din data lämnar aldrig datorn)
- Visar resultaten i ett webbdashboard med kanban-pipeline, sökordsgenerator och systemlogg
- Låter dig starta/stoppa/starta om allt från webbläsaren

---

## Krav

| Verktyg | Version | Länk |
|---------|---------|------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| PostgreSQL | 14+ | [postgresql.org](https://www.postgresql.org/download/) |
| Ollama | senaste | [ollama.com](https://ollama.com/) |
| Git | senaste | [git-scm.com](https://git-scm.com/) |

> **Windows:** PowerShell 5.1+ (medföljer Windows 10/11)

---

## Installation

### 1. Klona repot

```powershell
git clone https://github.com/DITT-ANVÄNDARNAMN/LiaBot.git
cd LiaBot
```

### 2. Skapa en virtuell miljö och installera paket

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Skapa databasen i PostgreSQL

Öppna `psql` eller pgAdmin och kör:

```sql
CREATE DATABASE liabot;
```

Standard PostgreSQL-inloggning är `postgres` / det lösenord du satte vid installation.

### 4. Ladda ned AI-modellen

```powershell
ollama pull llama3.2
```

Modellen är ~2 GB. Kräver Ollama installerat och igång (`ollama serve`).

### 5. Konfigurera `.env`

Kopiera exempelfilen och fyll i dina uppgifter:

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env`-filen ser ut så här:

```env
# PostgreSQL
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=liabot
PG_USER=postgres
PG_PASSWORD=ditt-lösenord-här

# Ollama
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434

# API-server
API_HOST=0.0.0.0
API_PORT=8002
```

### 6. Starta

**Alternativ A — Dubbelklicka `LiaBot.vbs`**
Startar allt i bakgrunden och öppnar dashboardet i webbläsaren. Ingen terminal behövs.

**Alternativ B — PowerShell**
```powershell
.\run.ps1
```

---

## Första gången

Öppna `http://localhost:5173` (eller det Lovable-URL du använder) i webbläsaren.

1. Gå till **Inställningar** — kontrollera att PostgreSQL, Ollama och Git visar grönt
2. Gå till **Sökord** — klicka "Generera med AI" för att skapa relevanta sökord
3. Gå till **Dashboard** — klicka "Starta ny sökning"

Första sökningen tar 5–15 minuter beroende på din dator.

---

## Projektstruktur

```
LiaBot/
├── api.py              # FastAPI REST-API (port 8002)
├── analyzer.py         # Ollama AI-analys av annonser
├── database.py         # PostgreSQL-funktioner
├── launcher.py         # Lättviktig HTTP-server (port 8003) för API-start från browser
├── main.py             # CLI-kommandon (alternativ till API)
├── run.ps1             # Startar Ollama + Launcher + API
├── LiaBot.vbs          # Dubbelklick-startare (ingen terminal)
├── requirements.txt
├── .env                # Din konfiguration (skapas av dig, ingår ej i git)
├── .env.example        # Exempelfil
└── sources/
    ├── jobtech.py      # JobTech API (Arbetsförmedlingen)
    ├── web_scraper.py  # Skrapar karriärsidor
    └── job_boards.py   # Svenska jobbsajter + standardkällor
```

---

## Vanliga problem

### PostgreSQL ansluter inte

- Kontrollera att PostgreSQL-tjänsten kör: `services.msc` → PostgreSQL
- Kontrollera `PG_PASSWORD` i `.env` — lösenordet är det du satte vid installation
- Se till att databasen `liabot` finns: `psql -U postgres -c "\l"`

### Ollama hittas inte

- Starta Ollama: sök efter "Ollama" i Start-menyn, eller kör `ollama serve`
- Kontrollera att modellen finns: `ollama list`
- Ladda ned igen om den saknas: `ollama pull llama3.2`

### Körexekveringspolicyn blockerar run.ps1

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Porten 8002 är redan i bruk

Stoppa den gamla processen:
```powershell
netstat -ano | findstr :8002
taskkill /PID <PID-nummer> /F
```

---

## Uppdatera till senaste versionen

Gå till **Inställningar** i dashboardet och klicka **"Hämta senaste versionen"**.
Din `.env`-konfiguration påverkas aldrig av uppdateringar.

Eller manuellt:
```powershell
git pull
```

Starta sedan om API:t via Terminal-fliken i dashboardet.

---

## Teknisk stack

| Komponent | Teknik |
|-----------|--------|
| Backend | Python / FastAPI |
| Databas | PostgreSQL (psycopg2) |
| AI-analys | Ollama (llama3.2) |
| Jobbkälla | JobTech API + HTTP-scraping |
| Frontend | React / TypeScript / Tailwind / shadcn-ui |

---

## Bidra

Pull requests är välkomna! Speciellt:
- Fler karriärsidor i `sources/job_boards.py` → `DEFAULT_CAREER_SOURCES`
- Bättre AI-prompt i `analyzer.py`
- Stöd för fler jobbsajter

---

## Licens

MIT
