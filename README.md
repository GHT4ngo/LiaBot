# LiaBot

**Automatisk LIA-sökning för Data Engineering-studenter**

LiaBot söker automatiskt igenom svenska jobbsajter och karriärsidor efter LIA-praktikplatser (Lärande i Arbete), analyserar annonserna med en lokal AI-modell och presenterar resultaten i ett webbaserat dashboard.

---

## Vad den gör

- Söker JobTech API (Arbetsförmedlingen/Platsbanken — täcker 200+ svenska jobbsajter)
- Skrapar karriärsidor hos 30+ svenska techbolag och konsultfirmor
- Analyserar varje annons med Ollama (lokal AI — din data lämnar aldrig datorn)
- Visar resultaten i ett webbdashboard med uppföljningslistor, sökordsgenerator och systemlogg
- Låter dig starta/stoppa/starta om allt från webbläsaren

---

## Krav

| Verktyg | Version | Länk |
|---------|---------|------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| PostgreSQL | 14+ | [postgresql.org](https://www.postgresql.org/download/) |
| DBeaver (rekommenderat) | senaste | [dbeaver.io/download](https://dbeaver.io/download/) |
| Ollama | senaste | [ollama.com](https://ollama.com/) |
| Git | senaste | [git-scm.com](https://git-scm.com/) |

> **Windows:** PowerShell 5.1+ (medföljer Windows 10/11)

---

## Installation

### 1. Klona repot

```powershell
git clone https://github.com/GHT4ngo/LiaBot.git
cd LiaBot
```

### 2. Skapa en virtuell miljö och installera paket

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Skapa databasen i PostgreSQL

Du behöver skapa en tom databas som heter `liabot`. Det enklaste sättet är via **DBeaver** — ett gratis grafiskt databasverktyg.

**Ladda ned DBeaver:** [dbeaver.io/download](https://dbeaver.io/download/) → välj *Community Edition*

**Anslut till PostgreSQL i DBeaver:**

1. Öppna DBeaver och klicka på **"New Database Connection"** (pluggikonen uppe till vänster)
2. Välj **PostgreSQL** och klicka *Next*
3. Fyll i anslutningsuppgifterna:

   | Fält | Värde |
   |------|-------|
   | Host | `localhost` |
   | Port | `5432` |
   | Database | `postgres` |
   | Username | `postgres` |
   | Password | Det lösenord du satte när du installerade PostgreSQL |

4. Klicka **Test Connection** — du ska se *Connected*. Klicka sedan *Finish*

**Skapa databasen:**

5. Expandera anslutningen i vänsterpanelen → högerklicka på **Databases** → **Create New Database**
6. Skriv `liabot` som namn → klicka *OK*

Klart! Databasen `liabot` är nu skapad och redo att användas.

> **Alternativ (för den som föredrar terminalen):** Öppna PowerShell och kör:
> ```powershell
> psql -U postgres -c "CREATE DATABASE liabot;"
> ```

### 4. Installera och starta Ollama

Ladda ned Ollama från [ollama.com](https://ollama.com/) eller installera direkt via PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Starta sedan Ollama (visas i systemfältet) och ladda ned AI-modellen (~2 GB):

```powershell
ollama pull llama3.2
```

### 5. Konfigurera inställningar (`.env`)

Repot innehåller en fil som heter `.env.example` — det är en mall med alla inställningar.
Du behöver skapa en kopia av den som heter `.env` och fylla i ditt PostgreSQL-lösenord.

**Steg för steg:**

```powershell
# 1. Kopiera mallen
Copy-Item .env.example .env

# 2. Öppna filen i Anteckningar
notepad .env
```

Du ser då den här filen. **Ändra bara raden med `PG_PASSWORD`** — sätt det lösenord du valde när du installerade PostgreSQL. Allt annat kan lämnas som det är om du körde standardinstallationen.

```env
# PostgreSQL
PG_HOST=localhost        # ändra ej
PG_PORT=5432             # ändra ej
PG_DATABASE=liabot       # ändra ej
PG_USER=postgres         # ändra ej
PG_PASSWORD=DITT-LÖSENORD-HÄR   # <--- ändra detta

# Ollama
OLLAMA_MODEL=llama3.2         # ändra ej
OLLAMA_BASE_URL=http://localhost:11434  # ändra ej

# API-server
API_HOST=0.0.0.0   # ändra ej
API_PORT=8002      # ändra ej
```

Spara och stäng filen.

### 6. Starta

**Alternativ A — Dubbelklicka `LiaBot.vbs`**
Startar allt i bakgrunden och öppnar dashboardet i webbläsaren. Ingen terminal behövs.

**Alternativ B — PowerShell**
```powershell
.\run.ps1
```

---

## Kom igång

1. Dubbelklicka `LiaBot.vbs` (eller kör `.\run.ps1`)
2. Öppna [lia-tracker.lovable.app](https://lia-tracker.lovable.app)
3. Gå till **Inställningar** — kontrollera att alla tre tjänster visar grönt
4. Gå till **Sökord** — klicka "Generera med AI"
5. Gå till **Dashboard** — klicka "Starta ny sökning"

Första sökningen tar 5–20 minuter. En detaljerad guide finns i **[USAGE.md](USAGE.md)** — eller direkt i dashboardet under **Guide**-fliken.

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
- Verifiera att databasen `liabot` finns — öppna DBeaver, expandera anslutningen och titta under *Databases*
- Alternativt via terminal: `psql -U postgres -c "\l"`

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
