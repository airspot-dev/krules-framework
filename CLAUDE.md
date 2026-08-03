# KRules Framework - Project Memory

## Project Overview
KRules Framework 3.2.1 — async-only event-driven framework for Python applications.

## Repository
- Main branch: `main`

## Project Structure
- `krules/` - Core framework code
- `docs/` - Documentation
- Tests: Skip by default unless explicitly requested

## Development Notes
- Python async-first framework
- Event-driven architecture
- Uses dependency-injector for IoC
- Pydantic-settings for configuration
- Redis storage backends supported
- PostgreSQL storage backend with JSONB support (recently added)

## Skill correlata: `krules-python-skill`

Questo repository **produce** la skill `krules-python`, montata come submodule in
`.claude/skills/krules-python` e distribuita dal repository `krules-python-skill`.

La skill è il framework **visto da chi ci costruisce sopra**: pattern del container,
registrazione degli handler, gestione delle proprietà dei Subject, tracciamento della
catena, integrazioni. Non descrive gli interni di questo repo — serve a chi usa il
framework a non doverlo leggere.

### Regola di co-evoluzione

Le modifiche qui che cambiano quanto la skill afferma vanno riflesse nella skill **nella
stessa attività**, non rimandate. Rendono la skill falsa i cambiamenti a:

- **API pubbliche di `Subject`** — firme, semantica di cache e persistenza, `use_cache`
- **eventi di proprietà** — quando sono emessi, cosa portano, quali filtri hanno senso
- **`origin_id`** — primitive di `krules_core.origin`, propagazione della catena,
  mappatura sull'estensione CloudEvent `originid` al confine di trasporto
- **backend di storage** — Redis, PostgreSQL, firme delle factory
- **container e IoC** — pattern di composizione, override, risorse
- **integrazioni** — Celery, FastAPI, Google Pub/Sub

### Il segnale è meccanico: usa il changelog

A differenza di altri progetti, qui non serve giudicare se il contratto è cambiato: **ogni
voce di `CHANGELOG.md` che descriva un comportamento osservabile è un candidato**, e il
numero di versione dichiarato nella skill (`SKILL.md` → `Framework Version`) deve
corrispondere a quello rilasciato.

Una release che alza la versione senza toccare la skill è un disallineamento verificabile,
non un'opinione.

**È già successo.** `origin_id` è entrato in 3.2.0 con la sua voce di changelog; la skill
ha continuato a dichiarare 3.0 e a non menzionare la feature per tre settimane, e nessuno
se ne è accorto perché i due vivevano in repository scollegati. Il submodule e questa
regola esistono perché non si ripeta.

*Nota storica:* la voce 3.1.0 del changelog cita `krules-claude-skill`, un repository oggi
dismesso. Resta com'è — è un record di quel momento. Da qui in avanti il riferimento
valido è `krules-python-skill`.

### Chiusura di un'attività che ha toccato la skill

1. Stesso nome di branch nei due repo.
2. Commit **e push** su `krules-python-skill` **prima** di aggiornare il puntatore qui: un
   puntatore verso uno SHA non pushato rende il submodule irrisolvibile a chi clona.
3. Se il tuo ambiente monta la skill anche altrove (un aggregatore, un checkout
   separato), aggiornarne il puntatore: `git submodule update --remote --merge`.

### Note operative sul submodule

Clonare con `--recurse-submodules`, o `git submodule update --init` dopo il clone.

Il submodule è checkoutato sul suo branch, ma alcuni comandi git lo staccano: verificare
con `cd .claude/skills/krules-python && git branch --show-current` prima di editare.

Passando a un branch che non monta il submodule, il `checkout` può fallire con *"untracked
working tree files would be overwritten"*: `git submodule deinit -f .claude/skills/krules-python`
prima dello switch, `git submodule update --init` dopo il merge.
