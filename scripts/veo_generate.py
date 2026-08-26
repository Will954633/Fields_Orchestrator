#!/usr/bin/env python3
"""
veo_generate.py — generate short vertical b-roll / talking-head clips with
Google Veo 3 on Vertex AI, for the Reels campaign (03_Facebook/Reels).

Auth mirrors shared/claude_vision.py: a service-account key at
GOOGLE_APPLICATION_CREDENTIALS or /home/fields/.gcp-vertex-key.json, else ADC.
Output is written to a GCS bucket (Veo requirement) and then downloaded locally.

This is a MANUAL, on-demand tool (not a scheduled process) — no job_status
heartbeat needed. It spends real GCP/Vertex credits per render, so it prints an
estimated cost and supports --dry-run to inspect the request without sending.

Usage:
  # single prompt
  python3 scripts/veo_generate.py --prompt "..." --out /tmp/clip.mp4 [--fast] [--dry-run]

  # a named beat from the prompt pack (03_Facebook/Reels/veo_prompts.json)
  python3 scripts/veo_generate.py --pack 03_Facebook/Reels/veo_prompts.json --beat reel3_hook --out cards/reel3_hook.mp4

  # every beat in a pack
  python3 scripts/veo_generate.py --pack 03_Facebook/Reels/veo_prompts.json --all --outdir 03_Facebook/Reels/renders
"""
import argparse
import json
import os
import sys
import time
import subprocess
from pathlib import Path

import requests

# --- env -------------------------------------------------------------------
def load_env():
    """Load the orchestrator .env if present (don't trust the caller — Rule 7 §3)."""
    env_path = Path("/home/fields/Fields_Orchestrator/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# --- vertex auth (mirrors shared/claude_vision.py) -------------------------
_CREDS = None
def vertex_token() -> str:
    global _CREDS
    from google.auth.transport.requests import Request as GARequest
    if _CREDS is None:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        keyfile = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "/home/fields/.gcp-vertex-key.json"
        if os.path.exists(keyfile):
            from google.oauth2 import service_account
            _CREDS = service_account.Credentials.from_service_account_file(keyfile, scopes=scopes)
        else:
            import google.auth
            _CREDS, _ = google.auth.default(scopes=scopes)
    if not _CREDS.valid:
        _CREDS.refresh(GARequest())
    return _CREDS.token

# --- config ----------------------------------------------------------------
PROJECT = os.environ.get("VERTEX_PROJECT_ID", "fields-estate")
# Veo 3 GA lives in us-central1 (NOT the australia-southeast1 default used elsewhere).
REGION = os.environ.get("VEO_REGION", "us-central1")
MODEL_FULL = "veo-3.0-generate-001"
MODEL_FAST = "veo-3.0-fast-generate-001"
DEFAULT_BUCKET = os.environ.get("VEO_BUCKET", "gs://fields-property-images/reels_veo")
# rough public list price, USD/second (full ~$0.40, fast ~$0.15); for the cost note only
COST_PER_SEC = {MODEL_FULL: 0.40, MODEL_FAST: 0.15}


def host() -> str:
    return f"{REGION}-aiplatform.googleapis.com"


def build_request(prompt, aspect="9:16", duration=8, audio=True, negative=None,
                  person="allow_adult", storage_uri=None, count=1):
    params = {
        "aspectRatio": aspect,
        "durationSeconds": duration,
        "sampleCount": count,
        "personGeneration": person,
        "generateAudio": audio,
    }
    if storage_uri:
        params["storageUri"] = storage_uri if storage_uri.endswith("/") else storage_uri + "/"
    instance = {"prompt": prompt}
    if negative:
        instance["negativePrompt"] = negative
    return {"instances": [instance], "parameters": params}


def start_job(model, body):
    url = (f"https://{host()}/v1/projects/{PROJECT}/locations/{REGION}"
           f"/publishers/google/models/{model}:predictLongRunning")
    r = requests.post(url, headers={"Authorization": f"Bearer {vertex_token()}",
                                    "Content-Type": "application/json"}, json=body, timeout=60)
    if not r.ok:
        raise RuntimeError(f"start_job {r.status_code}: {r.text[:600]}")
    return r.json()["name"]


def poll_job(model, op_name, timeout=600, interval=15):
    url = (f"https://{host()}/v1/projects/{PROJECT}/locations/{REGION}"
           f"/publishers/google/models/{model}:fetchPredictOperation")
    waited = 0
    while waited <= timeout:
        r = requests.post(url, headers={"Authorization": f"Bearer {vertex_token()}",
                                        "Content-Type": "application/json"},
                          json={"operationName": op_name}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"poll {r.status_code}: {r.text[:400]}")
        data = r.json()
        if data.get("done"):
            if "error" in data:
                raise RuntimeError(f"Veo job error: {json.dumps(data['error'])[:600]}")
            return data.get("response", {})
        time.sleep(interval)
        waited += interval
        print(f"  ... {waited}s", file=sys.stderr)
    raise TimeoutError(f"Veo job did not finish within {timeout}s")


def extract_gcs_uris(response: dict):
    """Veo GA nests the outputs under one of a few keys depending on version."""
    for key in ("videos", "generatedSamples", "predictions", "raiMediaFilteredReasons"):
        if key in response:
            break
    vids = response.get("videos") or response.get("generatedSamples") or []
    uris = []
    for v in vids:
        uri = (v.get("gcsUri") or v.get("uri")
               or (v.get("video") or {}).get("uri")
               or (v.get("video") or {}).get("gcsUri"))
        if uri:
            uris.append(uri)
    filtered = response.get("raiMediaFilteredCount") or 0
    if not uris and filtered:
        raise RuntimeError(f"All {filtered} sample(s) were safety-filtered: "
                           f"{response.get('raiMediaFilteredReasons')}")
    return uris


def gsutil_cp(gcs_uri, local_path):
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gsutil", "cp", gcs_uri, str(local_path)], check=True)


def run_one(prompt, out, model, aspect, duration, audio, negative, bucket, dry_run):
    body = build_request(prompt, aspect=aspect, duration=duration, audio=audio,
                         negative=negative, storage_uri=bucket)
    est = COST_PER_SEC.get(model, 0.4) * duration
    print(f"→ model={model}  {aspect} {duration}s audio={audio}  est≈${est:.2f}")
    print(f"  prompt: {prompt[:140]}{'…' if len(prompt) > 140 else ''}")
    if dry_run:
        print("  [dry-run] request body:")
        print(json.dumps(body, indent=2))
        return None
    op = start_job(model, body)
    print(f"  job: {op}", file=sys.stderr)
    resp = poll_job(model, op)
    uris = extract_gcs_uris(resp)
    if not uris:
        raise RuntimeError(f"No video URI in response: {json.dumps(resp)[:500]}")
    gsutil_cp(uris[0], out)
    print(f"  ✓ {out}  ({uris[0]})")
    return out


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Generate Veo 3 clips on Vertex")
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--pack", help="JSON prompt pack")
    ap.add_argument("--beat", help="beat key within --pack")
    ap.add_argument("--all", action="store_true", help="render every beat in --pack")
    ap.add_argument("--out")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--fast", action="store_true", help="use veo-3.0-fast (cheaper)")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--duration", type=int, default=8)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--negative", default=None)
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    model = MODEL_FAST if args.fast else MODEL_FULL

    def opts_for(beat):
        return dict(model=model, aspect=beat.get("aspect", args.aspect),
                    duration=beat.get("duration", args.duration),
                    audio=beat.get("audio", not args.no_audio),
                    negative=beat.get("negative", args.negative),
                    bucket=args.bucket, dry_run=args.dry_run)

    if args.pack:
        pack = json.loads(Path(args.pack).read_text())
        beats = pack["beats"] if isinstance(pack, dict) else pack
        if args.all:
            for b in beats:
                out = Path(args.outdir) / f"{b['key']}.mp4"
                print(f"\n== {b['key']} ==")
                run_one(b["prompt"], out, **opts_for(b))
        else:
            if not args.beat:
                sys.exit("--pack needs --beat KEY or --all")
            b = next((x for x in beats if x["key"] == args.beat), None)
            if not b:
                sys.exit(f"no beat '{args.beat}' in pack (have: {[x['key'] for x in beats]})")
            out = args.out or str(Path(args.outdir) / f"{b['key']}.mp4")
            run_one(b["prompt"], out, **opts_for(b))
        return

    prompt = args.prompt or (Path(args.prompt_file).read_text().strip() if args.prompt_file else None)
    if not prompt:
        sys.exit("need --prompt, --prompt-file, or --pack")
    if not args.out and not args.dry_run:
        sys.exit("need --out")
    run_one(prompt, args.out or "/dev/null", model=model, aspect=args.aspect,
            duration=args.duration, audio=not args.no_audio, negative=args.negative,
            bucket=args.bucket, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
