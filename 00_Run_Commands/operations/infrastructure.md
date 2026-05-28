# Infrastructure

## VMs

### fields-orchestrator-vm (primary)
- **GCP project:** `fields-estate`
- **Zone:** `australia-southeast1-b`
- **Machine type:** `e2-standard-2`
- **External IP:** `34.40.230.132`
- **Disk:** 100GB boot (`/dev/root`, 53% used, holds `/data/blobs/` = 249GB — **disk is the bottleneck**)
- **Service account:** `419034603899-compute@developer.gserviceaccount.com` (default GCE SA, scope `devstorage.read_only` — gotcha noted in [backups.md](backups.md))
- **Runs:** Orchestrator pipeline, MongoDB, watchdog, voice agent, nginx (blobs + vm shell), all `fields-*` systemd services

### property-scraper VM (secondary)
- **External IP:** `35.201.6.222`
- **SSH:** `ssh fields-orchestrator-vm@35.201.6.222`
- **Disk:** 30GB total, 11GB free — too small for blob mirroring
- **Runs:** Backup scrapers (SearXNG + agency sites), CEO agent Codex CLI

## DNS & Domains

- **Domain registrar:** TBD — verify and document
- **Production records** (Cloudflare? Netlify DNS? Confirm and document):
  - `fieldsestate.com.au` → Netlify (website)
  - `vm.fieldsestate.com.au` → fields-orchestrator-vm (Claude Code terminal)
  - `blobs.fieldsestate.com.au` → fields-orchestrator-vm (image CDN)
- **Certs:** Let's Encrypt via Certbot on nginx, auto-renewing
  - Check renewal: `sudo certbot certificates`
  - Affected configs: `/etc/nginx/sites-available/{blobs,fields-vm}`

## GCP Project

- **Project ID:** `fields-estate`
- **Billing owner:** `will.simpson@blueoceans.com.au`
- **Key services in use:**
  - Compute Engine (2 VMs)
  - Cloud Storage (`gs://fields-blob-backup` — Nearline, 300GB cap-ish)
  - (Add: Anthropic API, OpenAI API usage tracked separately)

## Network

- nginx on fields-orchestrator-vm fronts:
  - `vm.fieldsestate.com.au` → code-server (Claude Code in browser)
  - `blobs.fieldsestate.com.au` → `/data/blobs/` static serve
- Inbound 443 only (Certbot redirects 80 → 443)

## TODO — fill in when verified
- DNS registrar + login
- Exact Cloudflare/Netlify DNS records
- GCP project quotas + budget alerts
- Backup of nginx configs + certbot state to GCS (currently VM-only)
