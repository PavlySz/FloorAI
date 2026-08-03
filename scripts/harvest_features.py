"""Harvest Gorgia's product feature table, with validation.

Gorgia publishes dimensions for nearly every product, but the field is not
trustworthy as-is:
  * units are inconsistent -- most rows are metres, some are centimetres
    ("80 40 80" for a coffee table)
  * some rows are junk (a 55kg sofa listed as 0.04 x 0.05 x 0.05 m)
  * some rows are off by 10x versus the size stated in the product name

So values are normalised to cm by magnitude, sanity-checked against a plausible
range for the category, and cross-checked against any dimension already parsed
from the product name. The name wins on conflict -- it is literal text, not a
logistics field. Anything that fails validation is left null and recorded in
`rejected_features` rather than silently dropped.
"""
import json, re, sys, time
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ka-GE,ka;q=0.9"})

LABELS = {"სიგრძე": "length", "სიგანე": "width", "სიმაღლე": "height",
          "წონა": "weight", "ფერი": "color", "ბრენდი": "brand",
          "ქვეყანა": "country", "მასალა": "material"}

# plausible cm ranges per subcategory: (min_any_dim, max_any_dim)
RANGE = {
    "sofa": (40, 450), "armchair": (30, 160), "coffee_table": (25, 200),
    "shelf": (15, 250), "wardrobe": (30, 300), "commode": (25, 250),
    "pendant_light": (8, 200), "wall_sconce": (5, 200),
    "laminate": (0.5, 250), "tile": (0.5, 150), "paint": (5, 100),
    "door": (2, 260), "bed": (50, 300),
}

def features(html):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for el in soup.select(".ty-product-feature"):
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        for ka, en in LABELS.items():
            if txt.startswith(ka):
                out[en] = txt[len(ka):].strip()
    return out

def num(v):
    m = re.search(r"([\d.]+)", v or "")
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None

def to_cm(vals):
    """Values arrive in metres or centimetres. Decide by magnitude."""
    present = [v for v in vals if v]
    if not present:
        return [None, None, None]
    # if the largest value is under 5 it is metres; otherwise already cm
    scale = 100.0 if max(present) < 5 else 1.0
    return [round(v * scale, 1) if v else None for v in vals]

def plausible(dims, sub):
    lo, hi = RANGE.get(sub, (1, 400))
    present = [d for d in dims if d]
    return bool(present) and all(lo <= d <= hi for d in present)

def main(path):
    rows = json.load(open(path, encoding="utf-8"))
    stats = {"kept": 0, "rejected": 0, "name_wins": 0, "brand": 0, "color": 0}
    for r in rows:
        try:
            f = features(S.get(r["url"], timeout=30).text)
        except Exception as e:
            print(f"  !! {r['id']}: {e}")
            continue

        # --- non-dimensional attributes are reliable, take them ---
        if f.get("brand"):
            r["brand"] = f["brand"]
            stats["brand"] += 1
        if f.get("country"):
            r["country_of_manufacture"] = f["country"]
        for key in ("color", "material"):
            if f.get(key) and not r.get(key):
                r[key] = f[key]
                r["derived_fields"] = [x for x in r.get("derived_fields", []) if x != key]
                if key == "color":
                    stats["color"] += 1

        # --- dimensions need validating ---
        raw = [num(f.get("length")), num(f.get("width")), num(f.get("height"))]
        cm = to_cm(raw)
        # Gorgia's "length" is the long horizontal dimension, which is the schema's
        # width; its "width" is the depth. Mapping them the other way round yields
        # 240cm-deep sofas.
        cand = {"w": cm[0], "d": cm[1], "h": cm[2]}
        existing = r.get("dimensions_cm") or {}
        has_name_dims = any(existing.get(k) for k in "wdh")

        if not plausible([cand["w"], cand["d"], cand["h"]], r["subcategory"]):
            r.setdefault("rejected_features", {})["dimensions"] = {
                "raw_metres": raw, "reason": "outside plausible range for subcategory"}
            stats["rejected"] += 1
            continue

        if has_name_dims:
            # A door's name states height*width ("215*70"); the feature table's
            # "length" is that same height, so gap-filling depth from it produces a
            # 215cm-deep door. For flat goods the name is complete -- leave it alone.
            if r["subcategory"] in ("door", "tile", "laminate"):
                stats["name_wins"] += 1
                time.sleep(0.6)
                continue
            # name text is literal; only fill gaps the name did not state
            merged = dict(existing)
            for k in "wdh":
                if not merged.get(k) and cand.get(k):
                    merged[k] = cand[k]
            if merged != existing:
                r["dimensions_cm"] = merged
                r["dimensions_source"] = (
                    f"{r.get('dimensions_source') or 'name'} + feature table (gaps)")
            stats["name_wins"] += 1
        else:
            r["dimensions_cm"] = cand
            r["dimensions_source"] = "feature table (validated)"
            r["derived_fields"] = [x for x in r.get("derived_fields", [])
                                   if x != "dimensions_cm"]
            stats["kept"] += 1
        time.sleep(0.6)

    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    have = sum(1 for r in rows if any(v for v in r["dimensions_cm"].values()))
    print(f"dimensions: {have}/{len(rows)}  (feature-table {stats['kept']}, "
          f"name-led {stats['name_wins']}, rejected {stats['rejected']})")
    print(f"brand: {stats['brand']}/{len(rows)}   new colours: {stats['color']}")

if __name__ == "__main__":
    main(sys.argv[1])
