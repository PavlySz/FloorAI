"""Add the kitchen + dining products the open-plan demo room needs.

Same rule as the main build: candidates are scored on how complete their spec
data is, and only the best-documented ones are kept.
"""
import json, os, re, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CAT = str(Path(__file__).resolve().parent.parent / "catalog")
MODEL = "claude-sonnet-4-5-20250929"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session(); S.headers.update({"User-Agent": UA})

LABELS = {"სიგრძე": "length", "სიგანე": "width", "სიმაღლე": "height",
          "ფერი": "color", "ბრენდი": "brand", "ქვეყანა": "country",
          "მასალა": "material"}

def g_features(url):
    try:
        soup = BeautifulSoup(S.get(url, timeout=25).text, "html.parser")
    except Exception:
        return {}
    out = {}
    for el in soup.select(".ty-product-feature"):
        t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        for ka, en in LABELS.items():
            if t.startswith(ka):
                out[en] = t[len(ka):].strip()
    return out

def dim(v):
    m = re.search(r"([\d.]+)", v or "")
    try:
        f = float(m.group(1)) if m else None
    except ValueError:
        return None
    return f if f and f > 0 else None

def to_cm(vals):
    got = [v for v in vals if v]
    if not got:
        return [None, None, None]
    s = 100.0 if max(got) < 5 else 1.0
    return [round(v * s, 1) if v else None for v in vals]

# ---------- Gorgia kitchen ----------
gaps = json.load(open("gorgia_gaps.json", encoding="utf-8"))
cands = gaps.get("kitchen_unit", []) + gaps.get("kitchen_sink", [])
with ThreadPoolExecutor(max_workers=8) as ex:
    feats = list(ex.map(lambda r: g_features(r["url"]), cands))
scored = []
for r, f in zip(cands, feats):
    L, W, H = to_cm([dim(f.get("length")), dim(f.get("width")), dim(f.get("height"))])
    sc = sum([all(x is not None for x in (L, W, H)) * 3, bool(f.get("color")) * 2,
              bool(f.get("material")) * 2, bool(f.get("brand"))])
    scored.append({**r, "_f": f, "_cm": {"w": L, "d": W, "h": H}, "_score": sc})

def top(sub, n):
    rows = [r for r in scored if r["subcategory"] == sub and all(r["_cm"].values())]
    return sorted(rows, key=lambda r: -r["_score"])[:n]

g_pick = top("kitchen_unit", 2) + top("kitchen_sink", 1)
print("gorgia kitchen picks:", [(r["subcategory"], r["_score"]) for r in g_pick])

# ---------- Comforter dining ----------
craw = json.load(open("comforter_raw.json", encoding="utf-8"))
def c_specs(url):
    try:
        h = S.get(url, timeout=25).text
    except Exception:
        return {}
    m = re.search(r'name="description"[^>]*content="([^"]{0,400})"', h)
    if not m:
        return {}
    d, out = m.group(1), {}
    for lab, key in (("Length", "w"), ("Width", "w"), ("Depth", "d"), ("Height", "h")):
        mm = re.search(rf"{lab}\s*-\s*(\d+(?:\.\d+)?)\s*cm", d, re.I)
        if mm and key not in out:
            out[key] = float(mm.group(1))
    mm = re.search(r"Material:\s*([A-Za-z /]+)", d)
    if mm: out["material"] = mm.group(1).strip()
    mm = re.search(r"Manufacture:\s*([A-Za-z ]+)", d)
    if mm: out["country"] = mm.group(1).strip()
    return out

c_cands = craw.get("table", [])[:10] + craw.get("skami", [])[:10]
with ThreadPoolExecutor(max_workers=8) as ex:
    cspecs = list(ex.map(lambda r: c_specs(r["url"]), c_cands))
c_scored = [{**r, "_s": s, "_n": sum(1 for k in ("w", "d", "h") if s.get(k))}
            for r, s in zip(c_cands, cspecs)]
c_pick = (sorted([r for r in c_scored if r["subcategory"] == "table"],
                 key=lambda r: -r["_n"])[:1]
          + sorted([r for r in c_scored if r["subcategory"] == "skami"],
                   key=lambda r: -r["_n"])[:2])
print("comforter dining picks:", [(r["name"], r["_n"]) for r in c_pick])

# ---------- translate ----------
listing = ([{"idx": i, "name": r["name_ka"], "sub": r["subcategory"],
             "color_ka": r["_f"].get("color"), "material_ka": r["_f"].get("material")}
            for i, r in enumerate(g_pick)]
           + [{"idx": 100 + i, "name": r["name"], "sub": r["subcategory"],
               "color_ka": None, "material_ka": r["_s"].get("material")}
              for i, r in enumerate(c_pick)])
P = """Real products from Georgian retailers. For each return:
 "idx", "name" (concise English; translate Georgian, keep model codes),
 "color" (English or null), "material" (English or null),
 "category": furniture|kitchen,
 "subcategory": kitchen_unit|kitchen_sink|dining_table|dining_chair,
 "style_tags": 1-3 of [scandinavian,nordic,japandi,modern,contemporary,minimalist,industrial,classic,luxury,rustic,bohemian]
Return ONLY a JSON array.

"""
body = json.dumps({"model": MODEL, "max_tokens": 4000, "messages": [
    {"role": "user", "content": P + json.dumps(listing, ensure_ascii=False)}]}).encode()
req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
    "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
    "anthropic-version": "2023-06-01"})
with urllib.request.urlopen(req, timeout=300) as resp:
    txt = json.load(resp)["content"][0]["text"].strip()
meta = {o["idx"]: o for o in json.loads(re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip())}

# ---------- append ----------
# drop what a previous run added, so re-running does not duplicate the picks
grows = [r for r in json.load(open(f"{CAT}/gorgia.json", encoding="utf-8"))
         if r.get("subcategory") not in ("kitchen_unit", "kitchen_sink")]
start = max((int(r["id"].split("-")[1]) for r in grows), default=0) + 1
for i, r in enumerate(g_pick):
    m = meta.get(i, {}); f = r["_f"]
    grows.append({
        "id": f"GRG-{start+i:03d}", "supplier": "Gorgia",
        "name": m.get("name") or r["name_ka"], "name_original": r["name_ka"],
        "category": m.get("category") or "kitchen", "subcategory": m.get("subcategory") or r["subcategory"],
        "style_tags": m.get("style_tags") or [], "color": m.get("color"),
        "material": m.get("material"), "dimensions_cm": r["_cm"],
        "dimensions_source": "feature table (validated)",
        "brand": f.get("brand"), "country_of_manufacture": f.get("country"),
        "price": r["price"], "currency": "GEL", "url": r["url"],
        "image_url": r.get("image_url"), "source": "scraped",
        "derived_fields": ["style_tags"]})
    print(f"  + {grows[-1]['id']} {grows[-1]['name'][:46]:48s} {grows[-1]['price']:>8} GEL")
json.dump(grows, open(f"{CAT}/gorgia.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

crows = [r for r in json.load(open(f"{CAT}/comforter.json", encoding="utf-8"))
         if r.get("subcategory") not in ("dining_table", "dining_chair")]
cstart = max((int(r["id"].split("-")[1]) for r in crows), default=0) + 1
for i, r in enumerate(c_pick):
    m = meta.get(100 + i, {}); s = r["_s"]
    crows.append({
        "id": f"CMF-{cstart+i:03d}", "supplier": "Comforter",
        "name": m.get("name") or r["name"], "name_original": r["name"],
        "category": "furniture", "subcategory": m.get("subcategory") or r["subcategory"],
        "style_tags": m.get("style_tags") or [], "color": m.get("color"),
        "material": m.get("material") or s.get("material"),
        "dimensions_cm": {"w": s.get("w"), "d": s.get("d"), "h": s.get("h")},
        "dimensions_source": "meta description", "brand": None,
        "country_of_manufacture": s.get("country"), "price": r["price"],
        "currency": "GEL", "url": r["url"], "image_url": r.get("image_url"),
        "source": "scraped", "derived_fields": ["style_tags"]})
    print(f"  + {crows[-1]['id']} {crows[-1]['name'][:46]:48s} {crows[-1]['price']:>8} GEL")
json.dump(crows, open(f"{CAT}/comforter.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"gorgia {len(grows)}  comforter {len(crows)}")
