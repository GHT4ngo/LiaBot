# Användningsguide — LiaBot

Öppna dashboardet på https://lia-tracker.lovable.app i webbläsaren när LiaBot körs lokalt.

En interaktiv version av den här guiden finns direkt i dashboardet under Guide-fliken.

---

## Steg 1 — Kontrollera att allt är igång (Inställningar)

Gå till Inställningar i sidomenyn och klicka "Testa alla".

Du ska se tre gröna bockar:

| Tjänst | Vad det betyder om det är rött |
|--------|-------------------------------|
| PostgreSQL | Databasen körs inte, eller fel lösenord i .env |
| Ollama AI | Ollama är inte startat, eller modellen saknas |
| Git | Mappen är inte ett git-repo — klona om från GitHub |

Du kan ändra alla inställningar direkt på sidan utan att redigera .env manuellt.

---

## Steg 2 — Sätt upp sökord (Sökord)

Beskriv med egna ord vad du letar efter, t.ex:

  "Leta efter företag som troligen skulle kunna erbjuda en praktikplats
   som data engineer, data scientist eller data analytics"

Lägg till extra kontext om du vill: "Helst i Stockholm" eller "Intresserad av fintech".

Klicka "Generera sökord med AI" — AI:n skapar 10-15 nyckelord anpassat till din beskrivning.
Du kan lägga till eller ta bort ord manuellt innan du sparar.

---

## Steg 3 — Kör en sökning (Dashboard)

Klicka "Starta ny sökning" pa Dashboard-sidan.

LiaBot gor nu tre saker i foljd:

1. Soker JobTech API — Arbetsformedlingens databas, Platsbanken + 200+ svenska jobbsajter
2. Skrapar karriarsidor — 30+ svenska techbolag och konsultfirmor
3. AI-analys — Varje annons skickas till Ollama som bedomerpraktiklamplig och extraherar kontaktuppgifter

Du ser realtidsloggar i Systemloggen pa Dashboard. Sokningen tar 5-20 minuter.
Du kan byta flik och gora annat — sokningen kor i bakgrunden.

---

## Steg 4 — Granska resultaten (Ansokningar)

Ga till Ansokningar for en fullstandig lista over alla hittade jobb.

Klicka pa en rad for att oppna detaljvyn dar du kan:
- Lasa hela annonstexten och AI:ns analys
- Andra status: Ny > Kontaktad > Svar mottaget > Intervju > Erbjudande
- Lagga till egna kommentarer och nasta steg
- Markera om du skickat ett mail

---

## Steg 5 — Folj din pipeline (Dashboard)

Langst ned pa Dashboard finns en kanban-tavla per status:

  Ny > Kontaktad > Svar mottaget > Intervju > Erbjudande > Avbojt > Ej relevant

Klicka pa ett kort for att oppna och uppdatera status.

---

## Steg 6 — Lagg till egna kallor (Kallor)

Ga till Kallor och klista in URL:en till ett foretags jobbsida.
Exmpel: https://careers.spotify.com/
Sidan inkluderas automatiskt i nasta sokning.

---

## Uppdatera till senaste versionen

Ga till Installningar och klicka "Hamta senaste versionen".
Din .env och sparade jobb paverkas aldrig.
Starta sedan om API:t via Terminal-fliken i Systemloggen.
