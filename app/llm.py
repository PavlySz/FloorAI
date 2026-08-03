"""Thin clients for the two providers. Kept deliberately small."""
import base64
import json
import re
import time

import requests

from . import config


class LLMError(RuntimeError):
    pass


def _extract_json(text):
    """Models occasionally wrap JSON in prose or fences; take the payload."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    if text.startswith(("{", "[")):
        return json.loads(text)
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if not m:
        raise LLMError(f"no JSON in model response: {text[:200]}")
    return json.loads(m.group(1))


def claude(prompt, image_bytes=None, image_mime="image/png",
           max_tokens=8000, temperature=None, as_json=True):
    """One Claude call. Optionally multimodal."""
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY is not set")

    content = []
    if image_bytes:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": image_mime,
            "data": base64.b64encode(image_bytes).decode()}})
    content.append({"type": "text", "text": prompt})

    payload = {"model": config.TEXT_MODEL, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": content}]}
    if temperature is not None:
        payload["temperature"] = temperature

    r = requests.post(config.ANTHROPIC_URL, json=payload, timeout=300, headers={
        "content-type": "application/json",
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"})
    if r.status_code != 200:
        raise LLMError(f"Claude {r.status_code}: {r.text[:300]}")
    text = r.json()["content"][0]["text"]
    return _extract_json(text) if as_json else text


def gemini_image(prompt, reference_png=None, model=None, retries=2):
    """Generate one image. `reference_png` conditions the render on a prior view."""
    if not config.GOOGLE_API_KEY:
        raise LLMError("GOOGLE_API_KEY is not set")

    parts = []
    if reference_png:
        parts.append({"inlineData": {"mimeType": "image/png",
                                     "data": base64.b64encode(reference_png).decode()}})
    parts.append({"text": prompt})

    url = config.GEMINI_URL.format(model=model or config.IMAGE_MODEL)
    last = None
    for attempt in range(retries + 1):
        r = requests.post(f"{url}?key={config.GOOGLE_API_KEY}",
                          json={"contents": [{"parts": parts}]}, timeout=300)
        if r.status_code == 200:
            for p in r.json()["candidates"][0]["content"]["parts"]:
                if "inlineData" in p:
                    return base64.b64decode(p["inlineData"]["data"])
            last = "response contained no image"
        else:
            last = f"{r.status_code}: {r.text[:200]}"
        if attempt < retries:
            time.sleep(2 * (attempt + 1))
    raise LLMError(f"image generation failed: {last}")
