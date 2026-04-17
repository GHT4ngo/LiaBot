# Användningsguide — LiaBot

Öppna dashboardet i webbläsaren när LiaBot körs lokalt (vanligtvis http://localhost:5173).

En interaktiv version av den här guiden finns direkt i dashboardet under **Guide**-fliken.

---

## Förkrav — Sätt upp PostgreSQL-databasen

Innan du startar LiaBot första gången behöver du skapa en tom databas som heter `liabot`.

Det enklaste sättet är via **DBeaver** — ett gratis grafiskt databasverktyg.
Ladda ned det här: [dbeaver.io/download](https://dbeaver.io/download/) → välj *Community Edition*

**Anslut till PostgreSQL:**

1. Öppna DBeaver → klicka på **"New Database Connection"** (pluggikonen uppe till vänster)
2. Välj **PostgreSQL** → klicka *Next*
3. Fyll i:

   | Fält | Värde |
   |------|-------|
   | Host | `localhost` |
   | Port | `5432` |
   | Database | `postgres` |
   | Username | `postgres` |
   | Password | Lösenordet du satte vid installation av PostgreSQL |

4. Klicka **Test Connection** → du ska se *Connected* → klicka *Finish*

**Skapa databasen `liabot`:**

5. Expandera anslutningen i vänsterpanelen → högerklicka på **Databases** → **Create New Database**
6. Skriv `liabot` som namn → klicka *OK*

Klart! Nu kan du starta LiaBot.

> **Alternativ (terminal):** `psql -U postgres -c "CREATE DATABASE liabot;"`

---

## Steg 1 — Kontrollera att allt är igång (Inställningar)

Gå till **Inställningar** i sidomenyn och klicka **"Testa alla"**.

Du ska se tre gröna bockar:

| Tjänst | Vad det betyder om det är rött |
|--------|-------------------------------|
| PostgreSQL | Databasen körs inte, eller fel lösenord i .env |
| Ollama AI | Ollama är inte startat, eller modellen saknas |
| Git | Mappen är inte ett git-repo — klona om från GitHub |

Du kan ändra alla inställningar direkt på sidan utan att redigera .env manuellt.

---

## Steg 2 — Sätt upp sökord (Sökord)

Gå till **Sökord** och beskriv med egna ord vad du letar efter, t.ex:

> "Leta efter företag som troligen skulle kunna erbjuda en praktikplats
> som data engineer, data scientist eller data analytics"

Lägg till extra kontext om du vill, t.ex. "Helst i Stockholm" eller "Intresserad av fintech".

Klicka **"Generera sökord med AI"** — AI:n skapar 10–15 nyckelord anpassade till din beskrivning.
Du kan lägga till eller ta bort ord manuellt innan du sparar.

---

## Steg 3 — Kör en sökning (Dashboard)

Klicka **"Starta ny sökning"** på Dashboard-sidan.

LiaBot gör nu tre saker i följd:

1. **JobTech API** — Arbetsförmedlingens databas, täcker Platsbanken och 200+ svenska jobbsajter
2. **Karriärsidor** — Besöker karriärsidorna hos 30+ svenska techbolag och konsultfirmor
3. **AI-analys** — Varje annons bedöms av Ollama: är den LIA-relevant? Vilka kontaktuppgifter finns?

Du ser realtidsloggar i Systemloggen på Dashboard. Sökningen tar vanligtvis 5–20 minuter.
Du kan byta flik och göra annat — sökningen körs i bakgrunden.

---

## Steg 4 — Granska resultaten (Ansökningar)

Gå till **Ansökningar** för en fullständig lista över alla hittade jobb.

Klicka på en rad för att öppna detaljvyn där du kan:
- Läsa hela annonstexten och AI:ns analys
- Ändra status: Ny → Kontaktad → Intervju → Erbjudande
- Lägga till egna kommentarer och nästa steg
- Markera om du skickat ett mail

Klicka **Spara** för att spara och stänga detaljvyn.

Filtrera listan med knapparna högst upp — visa bara relevanta, en viss status, eller sök på företagsnamn.

---

## Steg 5 — Följ upp via Dashboard

På Dashboard visas två listor som hjälper dig hålla koll:

- **Att kontakta** — Relevanta jobb du ännu inte kontaktat, sorterade efter prioritet
- **Väntar på svar** — Jobb du kontaktat, sorterade efter skickningsdatum

Klicka på ett företag för att öppna detaljvyn direkt.

---

## Steg 6 — Lägg till egna källor (Källor)

Gå till **Källor** och klistra in URL:en till ett företags karriärsida.
Exempel: `https://careers.spotify.com/`

Sidan inkluderas automatiskt i nästa sökning.

---

## Uppdatera till senaste versionen

Gå till **Inställningar** och klicka **"Hämta senaste versionen"**.

- Din .env-konfiguration påverkas aldrig
- Dina sparade jobb och ansökningar påverkas aldrig

Starta sedan om API:t via Terminal-fliken i Systemloggen.
