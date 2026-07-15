# Brexis × Claude Code — Purple Horizon

This is the brexis-app repository. Claude Code works here as the execution layer under Brexis Embervex's direction.

## At the start of every session

Check for pending tasks from Brexis before doing anything else. The pipeline lives on
Purple Horizon (source: purple-horizon-web, `app/pipeline/routes.py`):

```
GET https://web-production-815bd.up.railway.app/pipeline/queue
Authorization: Bearer <claude_api_key>
```

Polling the queue with the claude key **atomically claims** any ready task (approved +
queued) — it flips to in-progress and is yours. Work through the brief. Do not start
unrequested work. Task IDs are plain integers (e.g. `14`), never `TASK-XXXX` strings —
if Brexis quotes a `TASK-XXXX` id, the submission never actually reached the pipeline
(usually a stale-chat relay miss); ask for a fresh submit.

Check any task's detail and audit log with:

```
GET https://web-production-815bd.up.railway.app/pipeline/status/<task_id>
```

## When a build is complete

POST the completion report back:

```
POST https://web-production-815bd.up.railway.app/pipeline/complete
Authorization: Bearer <claude_api_key>
Content-Type: application/json

{
  "task_id": 14,
  "outcome": "success",            // success | failed | partial
  "files_changed": "app.py, database.py",
  "notes": "anything Brexis should pay attention to in review",
  "tokens_used": 12345
}
```

`partial` routes the task to review status; `failed` records `notes` as the error
reason. Do not consider a task done until Brexis approves it.

## Auth

Two separate Bearer tokens, stored in Purple Horizon's `pipeline_config` DB table
(single row), not in .env:

- `claude_api_key` — used by Claude Code (queue, status, complete). Stored in Claude
  Code memory (reference: brexis-api-token).
- `brexis_api_key` — used by Brexis (submit, status, queue). Configured on the Brexis
  side in /settings.

Set or regenerate either at Purple Horizon → /settings → "Claude Code Pipeline" card
(a blank field on save auto-generates a fresh token).

## The rules (from the spec)

1. Never start a task without a Brexis brief
2. Small = auto. Medium = Nate confirmed. Major = Nate explicit approval.
3. Brexis reviews before anything ships
4. Protected files require Nate approval: .env, railway.toml, gateway.py, SYSTEM_PROMPT block, auth/billing modules
5. Every task gets logged
6. Stop and flag if scope is creeping or protected files are in play
7. Execute within the brief — no product decisions

## Stack

- Python / Flask
- PostgreSQL on Railway (SQLite locally)
- All external calls through gateway.py
- Credentials in brexis_config DB via db.get_config() — never os.environ for user-set keys
- Railway deployment — push to main branch triggers deploy

## Repos

- brexis-app: C:/Users/nnagl/Claude/Projects/Saturday Morning PJs/brexis-app
- brexis-relay: C:/Users/nnagl/Claude/Projects/Saturday Morning PJs/brexis-relay
