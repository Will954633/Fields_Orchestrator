# YouTube → Brain 1 ingestion

**Built:** 2026-08-08 · **Code:** `scripts/samantha/youtube_brain_ingest.py` ·
**Config:** `config/youtube_channels.yaml` · **State:** `system_monitor.youtube_videos` ·
**Corpus dir:** `/home/fields/brain1_yt/`

Standing pipeline that turns a YouTube channel into Brain 1 units. Built for this
direct-mail project but not specific to it — add a channel to the config and it is picked up.

---

## 1. Why this was not trivial, and what the fix was

Three separate blocks had to be got past. Recording them because each one costs an hour to
rediscover.

| Route | Result from this VM | Why |
|---|---|---|
| `youtube-transcript-api` direct | `RequestBlocked` | YouTube blocks GCP datacentre IPs outright |
| `yt-dlp` on a **watch** URL | *"Sign in to confirm you're not a bot"* | same, at the player layer |
| `yt-dlp` on a **channel tab** | ✅ works | tab listings are not behind the player bot-check |
| Bright Data **Web Unlocker API** (`/request`) → watch page | ✅ returns `captionTracks` | — |
| …then fetching that `baseUrl` | **HTTP 200, zero bytes** | ← the trap |
| Bright Data Web Unlocker **proxy interface**, sticky session | ✅ **works** | ← the fix |

**The trap is worth understanding.** The timedtext URL embedded in the watch page is signed with
an `ei`/`expire` pair bound to the session that issued it. The Web Unlocker *API* rotates its exit
IP per request, so the second call arrives from a different identity and YouTube answers `200` with
an empty body — a success status carrying nothing. Fetching the watch page and the captions
through **one sticky proxy session** (`-session-<tag>` on the proxy username) makes both calls
share an identity and the captions come back.

Two dead ends also ruled out, so nobody retries them:
- The `gold_coast_agency_level` residential zone tunnels fine to other hosts but returns
  **403 Forbidden** for `youtube.com` — it is domain-restricted.
- InnerTube (`/youtubei/v1/player`) with ANDROID and TVHTML5 clients through Web Unlocker returns
  `playabilityStatus: ERROR` and no caption tracks.

TLS note: the proxy interface terminates TLS with Bright Data's own CA, so the session runs with
`verify=False`. That is stated in the code with its reasoning — the payload is public caption text,
no credentials cross it, and a corrupted body is caught by the word-count gate.

---

## 2. Stages

```bash
source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a

python3 scripts/samantha/youtube_brain_ingest.py discover                 # channel tabs -> registry
python3 scripts/samantha/youtube_brain_ingest.py transcribe --limit 400 --workers 8
python3 scripts/samantha/youtube_brain_ingest.py chunk                    # -> Brain 1 batch files
python3 scripts/samantha/youtube_brain_ingest.py status
```

Each stage is resumable and idempotent. `status` walks
`pending → transcribed → chunked`, with `skipped_short` for anything under 150 words and a
3-attempt cap on failures. Videos are transcribed **longest first** — a 60-minute training session
carries far more method than a 40-second clip.

Then annotate and fold into the graph:

```bash
python3 scripts/samantha/brain1_annotate.py --base /home/fields/brain1_yt
python3 scripts/samantha/brain1_graph.py \
    --in /home/fields/brain1_build/annotations.jsonl \
    --merge /home/fields/brain1_yt/annotations.jsonl \
    --outdir /home/fields/brain1_build
```

`brain1_annotate.py` gained a `--base` flag for this (it was hard-wired to one build dir). The
YouTube units annotate into their **own** `annotations.jsonl` and are merged only at graph time, so
a bad ingestion run can be thrown away without touching the original corpus.

**Unit ids start at `u900000`.** The `u` prefix is deliberate, not cosmetic: `brain1_deep.py`'s
citation regex only recognises `u`/`k`/`i` ids, so a `y`-prefixed namespace would make every
YouTube citation invisible to the quote verifier. 900000 sits far above the original corpus's
~3,071 units, so the namespaces cannot collide.

---

## 3. Channels

**Status: ✅ INGESTED.** 325 of 331 videos transcribed (**2,537,053 words**), chunked to 2,278 units,
**2,264 annotated (99.4%)** and merged into the Brain 1 graph on 2026-08-08. The graph went
**6,400 → 8,664 units**. Verified queryable in isolation:
`brain1_deep.py "…" --library "BLAC SALT (AU)"` returns 88 relevant units from 199 candidates.

⚠ The merged `package.json` is now **25.3 MB / ~6.3M tokens** and the graph builder warns it exceeds
the ~900k budget for a single Opus context. `brain1_deep.py` is unaffected — it retrieves per facet
and Haiku-judges before synthesis — but anything that tries to load the whole package at once will
not fit.

| Library | Channel | Videos | Units in graph | Why it is in the corpus |
|---|---|---|---|---|
| **BLAC SALT (AU)** | `@BLAC_SALT` (`UCuygO2H0YAvCn1i8h3p3Htw`) | 81 | **674** | Australian training (Agents'Agency, Manos Findikakis). Long-form virtual sessions, ~17–22k words each. **This is the point of the exercise** — Brain 1 outside Tom Panos is US-weighted, and mail economics, consumer behaviour and regulation do not read across from the US. |
| **eXp Realty (US)** | `@eXpRealty` (`UC43frD2HapVKMMaQM5Cf5qw`) | 250 | **1,590** | Large US brokerage. Expect a low signal-to-noise ratio — much of the channel is agent-attraction and revenue-share, not prospecting method. |

**⚠ The market suffix is load-bearing, not cosmetic.** The rest of Brain 1 is US-weighted, and
postage, consumer behaviour, regulation and even the seasons do not read across — one eXp blueprint
anchors its whole six-mailer calendar to "spring = March, fall = October", which inverts here. The
market is also stamped into every unit header (`Market: Australia`), because the annotator sees only
the header and the text.

⚠ **Both channels are self-published marketing by organisations selling training or recruitment.**
Nothing in them is measured, controlled or independently verified. Treat every number as an
assertion by an interested party — the same standing as the rest of the coaching corpus, and a
weaker standing than anything in `../02_Web/`. This corpus is for *method and language*, not for
deciding whether a channel works.

---

## 4. Self-monitoring

Wrapped in `job_run("youtube_brain_ingest", cadence_hours=168)` per CLAUDE.md Rule 7, with the
Rule 7b outcome assertion: **if the run attempts videos and transcribes zero, it raises.** That is
the exact failure this pipeline is prone to — the empty-body trap above returns HTTP 200, so a
broken run would otherwise complete cleanly having written nothing. An empty queue is success;
an empty result where input existed is not.

`--no-heartbeat` skips the beat for ad-hoc runs so manual experiments don't pollute the registry.

---

## 5. What is in this folder

| Path | What |
|---|---|
| `shards/shard_*.md` | Keyword-windowed passages (letterbox, direct mail, postcard, farming, follow-up, database, newsletter, CMA, just listed/sold, touches) extracted from every transcript, sharded for analysis |
| `_extract_raw.json` | The same extraction, machine-readable |
| `YT-FINDINGS.md` | What the two channels actually say about posted material, with verbatim quotes and video URLs |

⚠ The transcripts are **auto-captions**: no reliable punctuation, and names are frequently mangled.
Fine for retrieval and method-mining; clean anything before quoting it publicly.

⚠ The extraction is keyword-driven, so it is **recall-biased toward the words we thought of**. It is
a shortcut to usable findings while the full annotate-and-merge runs; it is not a substitute for
querying the merged graph.
