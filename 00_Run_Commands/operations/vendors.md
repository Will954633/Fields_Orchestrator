# Vendor Accounts

Every paid or free service Fields Estate depends on. When you cancel or migrate, update this file in the same change.

**Owner login (unless otherwise noted):** `will@fieldsestate.com.au` or `will.simpson@blueoceans.com.au`. Secrets live in `.env` files on the VM — never in this document.

## Active

| Vendor | Purpose | Plan | Approx cost/mo | Credentials | Notes |
|--------|---------|------|----------------|-------------|-------|
| **Google Cloud (GCP)** | 2x VMs + GCS bucket | Compute + Nearline storage | ~$60 | Console login | Project `fields-estate`. Sole infra host post-Azure. |
| **Netlify** | Website hosting + serverless functions | Pro? | ~$20 | Netlify dashboard | `fieldsestate.com.au`. Deploy hook: `https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d` |
| **GitHub** | Code repos + automation | Free | $0 | `gh` CLI under `Will954633` | All code mirrored here. PAT in `GH_CONFIG_DIR=/home/projects/.config/gh`. |
| **Anthropic** | Claude API (Opus 4.7 across CEO agents, voice agent, AI editorial) | API + Max subscription | ~$200 | `ANTHROPIC_API_KEY` in `.env`, `/etc/environment`, `~/.bashrc` | Max sub used for all `claude` CLI calls. |
| **OpenAI** | GPT-4 vision (steps 105, 106, 108, 117 — photo/floorplan/satellite analysis) | API | TBD | `OPENAI_API_KEY` in `.env` | |
| **Domain.com.au** | Property listings source | Free scraping (no API contract) | $0 | — | curl_cffi with `chrome120` impersonation. No login. |
| **Meta (Facebook Ads + Pages)** | Paid + organic FB | Pay per ad | ~$variable | `FACEBOOK_ADS_TOKEN` in `.env` (expires ~60d) | Ad Account `act_1463563608441065`, Page `889412530933297`. Token last renewed 2026-03-05. |
| **Google Ads** | Paid search | Pay per ad, $50/day caps | ~$variable | `GOOGLE_ADS_DEVELOPER_TOKEN` in `.env`, client secret JSON | MCC `127-641-8198`, Ad Account `997-572-4211`. |
| **PostHog** | Product analytics | Free tier | $0 | API key `phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs` | US cloud. Replaced custom CRM 2026-03-19. |
| **Telegram (@WillFieldsBot)** | Notifications + CEO agent bridge | Free | $0 | Bot token in `.env` | |
| **Let's Encrypt** | TLS certs for `vm.` and `blobs.` subdomains | Free | $0 | Certbot on VM | Auto-renew via systemd timer. |

## Deprecated / Cancelled

| Vendor | What it did | Cancelled | Migration target |
|--------|-------------|-----------|------------------|
| **Azure** | Cosmos DB + Blob Storage | 2026-05-28 | MongoDB on VM + GCS Nearline |
| **Ghost CMS** | Article hosting | ~early 2026 | Self-hosted in `system_monitor.content_articles` |
| **Custom CRM tracker** | Analytics | 2026-03-19 | PostHog |

## TODO — verify and document
- Cloudflare account (if used for DNS — confirm)
- Domain registrar for `fieldsestate.com.au` (Crazy Domains? GoDaddy? Confirm)
- Contentsquare account (mentioned as still kept alongside PostHog)
- Bright Data (folder `00_Run_Commands/Bright_Data/` exists — what is it used for?)
- Wise (mentioned in grind backlog as needing API integration)
- Samantha / accounting Blob (in `Will954633/samantha-accounting`)

## Cancellation Process Reference

When cancelling a vendor:
1. Search codebase for the vendor token / API name (`grep -rE "VENDOR_KEY" .env scripts/ src/`)
2. Migrate or remove every dependency
3. Verify nothing in production calls it (check service logs for 24h)
4. Cancel in vendor portal
5. Remove from `.env`, remove from this table (move to "Deprecated" section)
6. Update CLAUDE.md if it referenced the vendor
7. Log to fix-history
