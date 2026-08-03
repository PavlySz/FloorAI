"""Derive Comforter product colours from their photographs.

Comforter publishes no colour field and no swatch selector -- their entire spec
block is country, dimensions and a generic "Fabric". The only colour information
that exists is the product photo, so it is read from there and recorded as a
DERIVED field, never presented as supplier data.
"""
import base64, json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

MODEL = "claude-sonnet-4-5-20250929"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session(); S.headers.update({"User-Agent": UA})

PROMPT = """This is a product photograph of a single piece of furniture.

Return JSON: {"color": "...", "secondary_color": "..." or null, "confident": true/false}

- "color" is the dominant colour of the PRODUCT ITSELF, not the background or
  the styling props. Use plain English ("beige", "dark grey", "walnut brown",
  "mustard", "cream").
- "secondary_color" only if the product is clearly two-tone (e.g. fabric seat on
  a wooden frame).
- "confident": false if the product is hard to see or the photo is ambiguous.
Return ONLY the JSON object."""


def fetch(url):
    try:
        r = S.get(url, timeout=25)
        if r.status_code == 200 and len(r.content) > 2000:
            ct = r.headers.get("content-type", "image/jpeg").split(";")[0]
            return r.content, ct
    except Exception:
        pass
    return None, None


def read_colour(item):
    url = item.get("image_url")
    if not url:
        return item["id"], None
    blob, mime = fetch(url)
    if not blob:
        return item["id"], None
    body = json.dumps({
        "model": MODEL, "max_tokens": 300,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": mime,
                                         "data": base64.b64encode(blob).decode()}},
            {"type": "text", "text": PROMPT}]}]}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json",
                 "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = json.load(r)["content"][0]["text"].strip()
        return item["id"], json.loads(re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip())
    except Exception as e:
        print(f"  !! {item['id']}: {e}")
        return item["id"], None


path = sys.argv[1]
rows = json.load(open(path, encoding="utf-8"))
targets = [r for r in rows if not r.get("color") and r.get("image_url")]
print(f"reading colour from {len(targets)} product photos...")

with ThreadPoolExecutor(max_workers=6) as ex:
    results = dict(ex.map(read_colour, targets))

n = 0
for r in rows:
    got = results.get(r["id"])
    if not got or not got.get("color"):
        continue
    if got.get("confident") is False:
        continue
    r["color"] = got["color"]
    if got.get("secondary_color"):
        r["secondary_color"] = got["secondary_color"]
    r["color_source"] = "derived from product photograph"
    if "color" not in r.get("derived_fields", []):
        r.setdefault("derived_fields", []).append("color")
    n += 1
    print(f"  {r['id']} {r['name'][:26]:28s} -> {got['color']}")

json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\ncolour now on {sum(1 for r in rows if r.get('color'))}/{len(rows)}")
