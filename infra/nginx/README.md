# nginx configs (disaster recovery copies)

Live configs live in `/etc/nginx/sites-enabled/` on `fields-orchestrator-vm`.
These are mirrored here so they survive VM loss.

> NOTE: `sites-enabled/fields-vm` is a **standalone regular file**, NOT a symlink
> to `sites-available/`. Edit the file under `sites-enabled/` directly, then
> `sudo nginx -t && sudo systemctl reload nginx`. Keep backups OUT of
> `sites-enabled/` (it is globbed by `include sites-enabled/*`).

## fields-vm — vm.fieldsestate.com.au
- `location /`        → ttyd terminal `https://127.0.0.1:7681`
- `location /code/`   → code-server `http://127.0.0.1:8080`
- `location /audio/`  → static MP3 library
- `location /track/`  → email/appraisal tracking server `http://127.0.0.1:3051`
                        (Flask `tracking-server/server.py`; trailing slash strips `/track` prefix)
