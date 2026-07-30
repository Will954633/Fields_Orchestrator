"""
shared/claude_vision.py — Claude (Anthropic) vision helper.

Single place for the OpenAI→Claude vision migration. Every former
`client.chat.completions.create(model="gpt-*", ... image_url ...)` call routes
through `vision_text()` here: fetch image bytes → base64 → Anthropic Messages
call → return the text. Chosen over GPT for lower hallucination and stronger
structured extraction (the property pipeline's dominant requirement); see the
model-choice analysis in fix-history 2026-06-08.

Model tiers (override per call, or globally via env):
  CLASSIFY  — cheap binary/label calls (was gpt-4o-mini)      → Haiku 4.5
  ANALYZE   — default workhorse extraction/analysis (gpt-4o)  → Sonnet 4.6
  SPATIAL   — high-res spatial reasoning (satellite, gpt-5.4) → Opus 4.8

Determinism: the old calls passed temperature=0. Claude doesn't need it and
Opus 4.7/4.8 reject sampling params, so temperature is intentionally not sent.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, List, Optional, Tuple, Union

import requests

logger = logging.getLogger(__name__)

MODEL_CLASSIFY = os.environ.get("CLAUDE_VISION_CLASSIFY_MODEL", "claude-haiku-4-5")
MODEL_ANALYZE = os.environ.get("CLAUDE_VISION_MODEL", "claude-sonnet-4-6")
MODEL_SPATIAL = os.environ.get("CLAUDE_VISION_SPATIAL_MODEL", "claude-opus-4-8")

_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_CLIENT = None


def _sniff_media(content: bytes, header_ctype: str = "") -> str:
    """Detect image media type from magic bytes — Domain/CDN responses sometimes
    mislabel the content-type (e.g. a GIF served as image/jpeg), which Anthropic
    rejects with a 400. Magic bytes are authoritative; fall back to the header."""
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return header_ctype if header_ctype in _MEDIA_TYPES else "image/jpeg"

ImageSource = Union[str, dict, Tuple[str, str]]  # url | data-uri | {"url":..} | (media_type, b64)


def _client():
    global _CLIENT
    if _CLIENT is None:
        import anthropic
        # Direct ANTHROPIC_API_KEY billing has been dead since 2026-07 (AU Visa
        # intl decline on top-up) — any call on that path 400s with "credit
        # balance too low". OpenRouter exposes a genuine native Anthropic
        # /v1/messages passthrough (same request/response shape, images
        # supported), so the real anthropic SDK works unmodified just pointed
        # at a different base_url. Set ANTHROPIC_BACKEND=openrouter to use it.
        if os.environ.get("ANTHROPIC_BACKEND", "").strip().lower() == "openrouter":
            _CLIENT = anthropic.Anthropic(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url="https://openrouter.ai/api",
            )
        else:
            _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _CLIENT


def _resolve_model(model: str) -> str:
    """OpenRouter model ids are namespaced 'anthropic/<model>'."""
    if os.environ.get("ANTHROPIC_BACKEND", "").strip().lower() == "openrouter" and not model.startswith("anthropic/"):
        return f"anthropic/{model}"
    return model


def _image_bytes(src: ImageSource) -> Tuple[str, str]:
    """Return (media_type, base64_data) for any supported image source — URL,
    data-URI, (media_type, base64) tuple, or {"url"/"data_uri": ...} dict. HTTP
    URLs are fetched and base64'd here — Domain bucket URLs aren't reliably
    fetchable by the provider, so we proxy the bytes ourselves. Shared by both
    the Anthropic block builder and the Gemini inline_data builder."""
    if isinstance(src, dict):
        src = src.get("url") or src.get("data_uri") or src.get("image_url") or ""
        if isinstance(src, dict):
            src = src.get("url") or ""
    if isinstance(src, tuple) and len(src) == 2:
        media = src[0] if src[0] in _MEDIA_TYPES else "image/jpeg"
        return media, src[1]
    if isinstance(src, str) and src.startswith("data:"):
        head, _, data = src.partition(",")
        media = head.split(":", 1)[1].split(";", 1)[0]
        media = media if media in _MEDIA_TYPES else "image/jpeg"
        return media, data
    # Plain HTTP(S) URL — fetch + base64.
    r = requests.get(src, timeout=30)
    r.raise_for_status()
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    media = _sniff_media(r.content, ctype)
    return media, base64.standard_b64encode(r.content).decode()


def _image_block(src: ImageSource) -> dict:
    """Build an Anthropic image content block from any supported source."""
    media, data = _image_bytes(src)
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def _normalise_images(images) -> List[ImageSource]:
    if images is None:
        return []
    # A single (media_type, b64) tuple, a single dict, or a single str → wrap.
    if isinstance(images, (str, dict)):
        return [images]
    if isinstance(images, tuple) and len(images) == 2 and isinstance(images[0], str):
        return [images]
    return list(images)


# ---------------------------------------------------------------------------
# Gemini-via-Vertex backend (VISION_BACKEND=gemini_vertex)
#
# Why this exists: Claude vision can't run on the Max CLI (text-only), and every
# metered Claude path is dead — direct Anthropic (card decline), OpenRouter
# (credit dry), OpenAI (quota), AND Claude-on-Vertex (Anthropic DENIED the quota
# 2026-07-20). Gemini via Vertex bills to the GCP `fields-estate` account (which
# is healthy) and needs no Anthropic approval. The direct AI-Studio Gemini key
# is ALSO out of prepayment credit, so we go through Vertex, not
# generativelanguage.googleapis.com. See memory [[claude_via_vertex_gcp]].
# ---------------------------------------------------------------------------
_VERTEX_CREDS = None


def _vertex_token() -> str:
    global _VERTEX_CREDS
    from google.auth.transport.requests import Request as _GARequest
    if _VERTEX_CREDS is None:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        keyfile = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "/home/fields/.gcp-vertex-key.json"
        if os.path.exists(keyfile):
            from google.oauth2 import service_account
            _VERTEX_CREDS = service_account.Credentials.from_service_account_file(keyfile, scopes=scopes)
        else:  # fall back to Application Default Credentials (VM metadata SA)
            import google.auth
            _VERTEX_CREDS, _ = google.auth.default(scopes=scopes)
    if not _VERTEX_CREDS.valid:
        _VERTEX_CREDS.refresh(_GARequest())
    return _VERTEX_CREDS.token


def _gemini_model(claude_model: Optional[str]) -> str:
    """Map the caller's Claude tier to a Gemini model. Default flash (cheap/fast,
    A/B-verified adequate even on the hardest satellite step); the SPATIAL/Opus
    tier can be bumped to pro via GEMINI_VISION_SPATIAL_MODEL if precision needed."""
    default = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
    spatial = os.environ.get("GEMINI_VISION_SPATIAL_MODEL", default)
    return spatial if (claude_model and "opus" in claude_model.lower()) else default


def _gemini_vertex_text(prompt, images, model, max_tokens, system) -> Optional[str]:
    proj = os.environ.get("VERTEX_PROJECT_ID", "fields-estate")
    region = os.environ.get("VERTEX_REGION", "global")
    host = "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
    gmodel = _gemini_model(model)
    parts: List[dict] = []
    for s in _normalise_images(images):
        try:
            media, data = _image_bytes(s)
            parts.append({"inline_data": {"mime_type": media, "data": data}})
        except Exception as e:
            logger.warning(f"claude_vision(gemini): image fetch/encode failed: {e}")
    parts.append({"text": prompt})
    gen = {"maxOutputTokens": max_tokens, "temperature": 0}
    if "flash" in gmodel:  # pro rejects thinkingBudget=0; flash lets us skip thinking for structured extraction
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    url = (f"https://{host}/v1/projects/{proj}/locations/{region}"
           f"/publishers/google/models/{gmodel}:generateContent")
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {_vertex_token()}",
                                        "Content-Type": "application/json"}, json=body, timeout=120)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        detail = getattr(getattr(e, "response", None), "text", "") or ""
        logger.warning(f"claude_vision(gemini): generateContent failed: {e} {detail[:200]}")
        return None
    cand = (data.get("candidates") or [{}])[0]
    if cand.get("finishReason") == "MAX_TOKENS":
        logger.warning(f"claude_vision(gemini): response truncated at max_tokens={max_tokens}")
    return "".join(p.get("text", "") for p in (cand.get("content", {}).get("parts") or [])) or ""


def vision_text(
    prompt: str,
    images=None,
    *,
    model: Optional[str] = None,
    max_tokens: int = 1500,
    system: Optional[str] = None,
    **_ignored: Any,
) -> Optional[str]:
    """Run a vision (or text-only) prompt and return the response text. `images`
    may be a single source or a list. Returns "" on an empty response, None on
    hard failure. Extra kwargs (e.g. legacy `temperature`, `detail`) are accepted
    and ignored for drop-in compatibility. Backend is Gemini-via-Vertex when
    VISION_BACKEND=gemini_vertex (default for the mini-site), else Anthropic."""
    if os.environ.get("VISION_BACKEND", "").strip().lower() in ("gemini_vertex", "gemini", "vertex"):
        return _gemini_vertex_text(prompt, images, model, max_tokens, system)
    content: List[dict] = []
    for s in _normalise_images(images):
        try:
            content.append(_image_block(s))
        except Exception as e:
            logger.warning(f"claude_vision: image fetch/encode failed: {e}")
    content.append({"type": "text", "text": prompt})
    kwargs = {
        "model": _resolve_model(model or MODEL_ANALYZE),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        kwargs["system"] = system
    try:
        resp = _client().messages.create(**kwargs)
    except Exception as e:
        logger.warning(f"claude_vision: messages.create failed: {e}")
        return None
    return "".join(b.text for b in (resp.content or []) if getattr(b, "type", None) == "text") or ""
