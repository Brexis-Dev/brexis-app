# Brexis × Claude Code — Purple Horizon

This is the brexis-app repository. Claude Code works here as the execution layer under Brexis Embervex's direction.

## At the start of every session

Check for pending tasks from Brexis before doing anything else:

```
GET https://purple-horizon-production.up.railway.app/api/code-tasks/pending
Authorization: Bearer <CLAUDE_CODE_API_TOKEN>
```

If tasks are returned, pick up the first queued one and work through the brief. Do not start unrequested work.

## When a build is complete

POST the completion report back:

```
POST https://purple-horizon-production.up.railway.app/api/code-tasks/<id>/result
Authorization: Bearer <CLAUDE_CODE_API_TOKEN>
Content-Type: application/json

{
  "completion_report": "...",
  "files_changed": "app.py, database.py",
  "dependencies_added": "none",
  "notes": "anything Brexis should pay attention to in review"
}
```

Brexis gets a Discord ping in #brexis-alerts and reviews. Do not consider a task done until Brexis approves it.

## Auth token

The CLAUDE_CODE_API_TOKEN is stored in Claude Code memory (reference: brexis_api_token). It must match the value set in Purple Horizon /settings → Claude Code Integration.

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
