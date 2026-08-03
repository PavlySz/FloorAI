"""Score every scraped Gorgia candidate on data completeness.

Selection is inverted from the first pass: instead of choosing per category and
accepting whatever attributes came with the product, every candidate's spec table
is read and scored, and only fully-documented products are eligible for the
catalog. Categories are a consequence of the data, not the driver.
"""
import json, re, time
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ka-GE,ka;q=0.9"})

LABELS = {"სიგრძე": "length", "სიგანე": "width", "სიმაღლე": "height",
          "წონა": "weight", "ფერი": "color", "ბრენდი": "brand",
          "ქვეყანა": "country", "მასალა": "material"}

# indoor, render-relevant subcategories only
SKIP = {"tap", "toilet", "kitchen_sink", "washbasin"}

def features(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for el in soup.select(".ty-product-feature"):
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        for ka, en in LABELS.items():
            if txt.startswith(ka):
                out[en] = txt[len(ka):].strip()
    return out

def dim(v):
    m = re.search(r"([\d.]+)", v or "")
    try:
        f = float(m.group(1)) if m else None
    except ValueError:
        return None
    return f if f and f > 0 else None

def score(rec):
    try:
        f = features(S.get(rec["url"], timeout=25).text)
    except Exception:
        return None
    L, W, H = dim(f.get("length")), dim(f.get("width")), dim(f.get("height"))
    dims_ok = all(x is not None for x in (L, W, H))
    rec = dict(rec)
    rec["_f"] = f
    rec["_dims"] = [L, W, H]
    rec["_score"] = sum([
        dims_ok * 3,
        bool(f.get("color")) * 2,
        bool(f.get("material")) * 2,
        bool(f.get("brand")),
        bool(f.get("country")),
    ])
    rec["_complete"] = dims_ok and bool(f.get("color")) and bool(f.get("material"))
    return rec

# gather every candidate seen so far
cands, seen = [], set()
for fn in ("gorgia_targeted.json", "gorgia_extra.json", "gorgia_gaps.json"):
    for sub, rows in json.load(open(fn, encoding="utf-8")).items():
        if sub in SKIP or sub == "ceiling_light":   # ceiling_light was bulbs
            continue
        for r in rows:
            if r.get("url") and r["url"] not in seen and r.get("price"):
                seen.add(r["url"])
                r["subcategory"] = sub
                cands.append(r)

print(f"scanning {len(cands)} candidates...")
t0 = time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    scored = [r for r in ex.map(score, cands) if r]
print(f"scanned in {time.time()-t0:.0f}s")

complete = [r for r in scored if r["_complete"]]
json.dump(scored, open("gorgia_scored.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

from collections import Counter
print(f"\nfully complete (dims+colour+material): {len(complete)}/{len(scored)}")
c = Counter(r["subcategory"] for r in complete)
for k, v in c.most_common():
    print(f"   {k:18s} {v}")
