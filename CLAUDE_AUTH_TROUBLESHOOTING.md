# Claude Code Auth Troubleshooting — VM (code-server) Setup

**Audience:** Claude running on Will's local Mac. Will is trying to log Claude Code back into his Max subscription on the remote VM (`fields-orchestrator-vm`, IP `34.40.230.132`) and it's broken again.

**Your job:** Diagnose from the Mac side, give Will the exact commands. You do NOT have shell access to the VM — Will does, via the code-server UI at `https://vm.fieldsestate.com.au` or via `ssh fields@34.40.230.132`. Get him to run commands and paste output.

---

## The Setup (so you understand what's going on)

- VM runs **code-server** (browser-based VS Code) bound to `127.0.0.1:8080`, fronted by a reverse proxy at `vm.fieldsestate.com.au`. This is NOT local VS Code + Remote-SSH — there is **no automatic port forwarding** between the Mac browser and the VM.
- The Claude Code **extension** runs inside code-server on the VM. It authenticates via OAuth stored in `~/.claude.json` on the VM (`oauthAccount` block, `organizationType: claude_max`, no `primaryApiKey`, no `customApiKeyResponses`).
- The Mac is just the device displaying code-server in a Chrome tab. The OAuth callback URL is the friction point — see below.

---

## What Went Wrong (history, 2026-05-26)

Two separate problems were conflated in earlier sessions:

### Problem A — Browser ERR_CONNECTION_REFUSED on OAuth callback

When Will clicks "Claude.ai Subscription" in the extension panel:

1. Extension opens a listener on a **random high port on the VM** (e.g. 39227, 43071).
2. Will is sent to `claude.ai/oauth/...` which, after sign-in, redirects his Mac browser to `http://localhost:<port>/callback?code=...`.
3. The Mac browser tries to connect to `localhost:<port>` **on the Mac** — nothing is listening there (the listener is on the VM). Chrome shows `ERR_CONNECTION_REFUSED`.
4. The OAuth `code` is single-use and has already been issued to that dead endpoint. Pasting it into the extension's "paste code" fallback typically 400s because Anthropic's auth server sees a replay.

**This is unrelated to any state inside `.claude.json`.** It's a network-path problem caused by code-server-in-browser instead of Remote-SSH.

### Problem B — `ANTHROPIC_API_KEY` overriding the OAuth session

Inside the VM:
- `/home/fields/Fields_Orchestrator/.env` contains `ANTHROPIC_API_KEY=sk-ant-...` (intentionally kept — some scripts like the AI editorial pipeline need it).
- `/home/projects/.bashrc` line 119 auto-sources that `.env` into **every interactive shell**.
- Result: any `claude` CLI launched from a code-server integrated terminal inherits `ANTHROPIC_API_KEY` and silently prefers API-key billing over the Max subscription. This isn't the cause of the browser error, but it confuses diagnosis (sessions appear "logged in" but burn API credit) and historically led people to clear OAuth state thinking auth was broken.

---

## What We Fixed (2026-05-26)

1. **`/home/projects/.bashrc`** — added `unset ANTHROPIC_API_KEY` immediately after the `.env` auto-source. Scripts that explicitly `source .env` still get the key; interactive shells and any `claude` CLI launched from them no longer see it. Verified: `bash -ic 'echo $ANTHROPIC_API_KEY'` prints empty.
2. **`.env`** — left intact (line 125 `ANTHROPIC_API_KEY=...`). Don't delete it; scripts need it.
3. **`~/.claude.json`** on the VM — confirmed clean OAuth state: `oauthAccount.emailAddress: will.simpson@blueoceans.com.au`, `organizationType: claude_max`, no `primaryApiKey`, no `customApiKeyResponses`.
4. Logged at `logs/fix-history/2026-05-26.md`, problem ID `[CLAUDE-AUTH-LEAK]`. Pushed in commit `18d7890`.

---

## Diagnostic Playbook (when Will says it's broken again)

**Step 1 — Distinguish the two failure modes.** Ask Will:
- "When you click Claude.ai Subscription, does the browser show ERR_CONNECTION_REFUSED on a `localhost:<port>` URL?" → **Problem A** (network path).
- "Does the extension say you're signed in but `claude` in a terminal says you need to log in, or behaves like it's using API key?" → **Problem B** (key leak) regression.
- "Does the extension show wrong account, or fail with HTTP 400/401 errors mid-session?" → **State corruption** in `~/.claude.json`. Rare.

### Problem A — Browser ERR_CONNECTION_REFUSED

The OAuth callback port is **chosen freshly every login attempt** by the extension. To make `localhost:<port>` on the Mac actually reach the extension's listener on the VM, you need a reactive SSH port-forward:

1. Tell Will: **click "Claude.ai Subscription" in the extension, but do NOT open the URL yet.** Have him copy the URL and paste it to you (or read the port from it — the `redirect_uri=http://localhost:<PORT>/callback` parameter).
2. Tell Will to run on his Mac (in a Terminal window — replace `<PORT>` with the number from the URL):
   ```bash
   ssh -N -L <PORT>:127.0.0.1:<PORT> fields@34.40.230.132
   ```
   Leave it running. No output is expected on success.
3. **Then** tell Will to open the OAuth URL in his Mac browser. After the Claude.ai sign-in, the redirect to `localhost:<PORT>` will now travel through the tunnel to the extension on the VM.
4. Once the extension confirms it's signed in, Will can Ctrl-C the SSH command.

**If the OAuth URL has already been opened and ERR_CONNECTION_REFUSED was already shown**, the code is burned — Will must click "Claude.ai Subscription" again to get a new URL with a new port. Don't try to recover the old code.

**Durable fix (recommend once):** Switch from code-server-in-browser to **local VS Code on the Mac + Remote-SSH** to the VM. VS Code's Remote-SSH auto-forwards extension-requested ports, so this problem disappears entirely. The extension runs in the same place (on the VM), just with a different host UI.

### Problem B — `ANTHROPIC_API_KEY` is back in interactive shells

Have Will run in a VM terminal:
```bash
env | grep ANTHROPIC_API_KEY
```
Expected: empty. If it prints a value, the `~/.bashrc` fix has regressed. Have him check:
```bash
grep -n ANTHROPIC /home/projects/.bashrc
```
Should show an `unset ANTHROPIC_API_KEY` line right after `source /home/fields/Fields_Orchestrator/.env 2>/dev/null` (around line 119-123). If missing, re-add it:
```bash
sed -i '/source \/home\/fields\/Fields_Orchestrator\/\.env/a unset ANTHROPIC_API_KEY' /home/projects/.bashrc
```
Then open a fresh terminal — existing terminals retain the old env.

Also check the extension-host process specifically (only matters if the extension itself is broken, not just CLI):
```bash
EH_PID=$(pgrep -f "extensionHost" | head -1)
tr '\0' '\n' < /proc/$EH_PID/environ | grep ANTHROPIC
```
Should print nothing. If it prints `ANTHROPIC_API_KEY=...`, the extension host was started by a shell that had the key — Will needs to fully restart code-server:
```bash
sudo systemctl restart code-server@projects
```
(Service name may differ — `systemctl list-units | grep code-server` to find it.)

### State corruption in `~/.claude.json`

Inspect (on the VM):
```bash
jq '{oauth: .oauthAccount.emailAddress, org: .oauthAccount.organizationType, primaryApiKey: (.primaryApiKey // "absent"), customApiKeyResponses: (.customApiKeyResponses // "absent")}' ~/.claude.json
```
Healthy output:
```json
{
  "oauth": "will.simpson@blueoceans.com.au",
  "org": "claude_max",
  "primaryApiKey": "absent",
  "customApiKeyResponses": "absent"
}
```
If `primaryApiKey` is present or `customApiKeyResponses` is non-empty, the extension was forced into API-key mode at some point. Back up the file first, then strip those keys with `jq`:
```bash
cp ~/.claude.json ~/.claude.json.bak.$(date +%Y%m%d_%H%M%S)
jq 'del(.primaryApiKey) | del(.customApiKeyResponses)' ~/.claude.json > /tmp/claude.json && mv /tmp/claude.json ~/.claude.json
```
Then restart code-server and re-do the OAuth flow with the SSH tunnel from Problem A.

---

## What Not To Do

- **Don't delete `ANTHROPIC_API_KEY` from `.env`.** Editorial generation and other scripts need it. The bashrc `unset` is the correct surgical fix.
- **Don't `git push`** anything from the VM (it hangs on this host). Use `gh api` PUT to the contents endpoint. The CLAUDE.md at repo root has the exact pattern.
- **Don't paste the OAuth code into the extension** if the browser showed ERR_CONNECTION_REFUSED. The code is already burned — start a fresh "Claude.ai Subscription" click.
- **Don't try to fix the localhost-callback issue by editing nginx/reverse-proxy config.** The callback port is random per-login and chosen by the extension; you can't pre-configure it. SSH tunnel or Remote-SSH are the only sane options.

---

## Quick-Reference Commands (give these to Will verbatim)

```bash
# Healthy auth state check (run on VM)
env | grep ANTHROPIC_API_KEY    # should be empty
jq '.oauthAccount.emailAddress, .oauthAccount.organizationType' ~/.claude.json
grep -n "unset ANTHROPIC_API_KEY" /home/projects/.bashrc

# Reactive SSH tunnel for OAuth callback (run on Mac, replace <PORT>)
ssh -N -L <PORT>:127.0.0.1:<PORT> fields@34.40.230.132

# Restart code-server if extension host has stale env
sudo systemctl list-units | grep code-server
sudo systemctl restart <code-server-unit-name>
```

---

## Background Refs

- Fix history entry: `logs/fix-history/2026-05-26.md` (problem ID `CLAUDE-AUTH-LEAK`)
- VM CLAUDE.md (repo root) — overall ops context
- Persistent memory note on the VM: `memory/claude_oauth_auth_setup.md` (linked from `MEMORY.md`)
