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


def _image_block(src: ImageSource) -> dict:
    """Build an Anthropic image content block from a URL, data-URI,
    (media_type, base64) tuple, or {"url"/"data_uri": ...} dict. HTTP URLs are
    fetched and base64'd here — Domain bucket URLs aren't reliably fetchable by
    the provider, so we proxy the bytes ourselves."""
    if isinstance(src, dict):
        src = src.get("url") or src.get("data_uri") or src.get("image_url") or ""
        if isinstance(src, dict):
            src = src.get("url") or ""
    if isinstance(src, tuple) and len(src) == 2:
        media = src[0] if src[0] in _MEDIA_TYPES else "image/jpeg"
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": src[1]}}
    if isinstance(src, str) and src.startswith("data:"):
        head, _, data = src.partition(",")
        media = head.split(":", 1)[1].split(";", 1)[0]
        media = media if media in _MEDIA_TYPES else "image/jpeg"
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
    # Plain HTTP(S) URL — fetch + base64.
    r = requests.get(src, timeout=30)
    r.raise_for_status()
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    media = _sniff_media(r.content, ctype)
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.standard_b64encode(r.content).decode()}}


def _normalise_images(images) -> List[ImageSource]:
    if images is None:
        return []
    # A single (media_type, b64) tuple, a single dict, or a single str → wrap.
    if isinstance(images, (str, dict)):
        return [images]
    if isinstance(images, tuple) and len(images) == 2 and isinstance(images[0], str):
        return [images]
    return list(images)


def vision_text(
    prompt: str,
    images=None,
    *,
    model: Optional[str] = None,
    max_tokens: int = 1500,
    system: Optional[str] = None,
    **_ignored: Any,
) -> Optional[str]:
    """Run a vision (or text-only) prompt through Claude and return the response
    text. `images` may be a single source or a list of sources. Returns "" on an
    empty response, None on hard failure. Extra kwargs (e.g. legacy
    `temperature`, `detail`) are accepted and ignored for drop-in compatibility."""
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
