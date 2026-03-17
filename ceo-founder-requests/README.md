# CEO Founder Requests

This folder is the durable handoff channel between Will and the remote CEO team.

Use it for:
- longer concerns that do not fit Telegram cleanly
- new recurring checks or routines the CEO team should adopt
- open investigations that must persist across daily runs
- clarifications that should stay attached to the original issue

Use Telegram for:
- urgent questions
- short back-and-forth
- time-sensitive clarifications

## Folder Structure

- `open/` — active founder request threads written by Will
- `responses/` — CEO-team replies keyed to the same filename
- `closed/` — resolved items kept for reference if needed

## Workflow

1. Create one markdown file in `open/` per issue or instruction.
2. Use the same filename for the CEO team's reply in `responses/`.
3. If the CEO team asks a question, answer by appending a new dated section to the original file in `open/`.
4. The CEO team should append their updates to the paired file in `responses/`.
5. When the thread is fully complete, move the file to `closed/` or delete it.

## Ownership

- `open/*.md` = founder-owned thread
- `responses/*.md` = CEO-team-owned thread

Do not mix both sides into one block of text. Keep each side in its own file.

## Naming

Use filenames like:

- `2026-03-18-growth-bot-traffic.md`
- `2026-03-18-product-new-daily-checks.md`
- `2026-03-18-engineering-ceo-routine-updates.md`

## Expectations For The CEO Team

- Read every file in `open/` during daily runs.
- Revisit unresolved items in future runs until they are resolved, blocked, or waiting on founder input.
- Ask questions in Telegram when needed, but also log them in the matching file under `responses/`.
- They may improve their own CEO sandbox code, prompts, and routines if it helps them do their job better.
- They must not directly modify production systems, ads, cron, or databases without explicit approval.
