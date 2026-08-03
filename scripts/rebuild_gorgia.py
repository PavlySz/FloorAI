"""Rebuild the Gorgia catalog, selecting on data completeness.

Every candidate was scored in scan_complete.py. Here each subcategory takes its
highest-scoring products, and a product with no usable dimensions is never
eligible. That inverts the first pass, which chose by category and accepted
whatever attributes came along.
"""
import json, os, re, sys, urllib.request

MODEL = "claude-sonnet-4-5-20250929"

# subcategory -> how many. Kept to what a living/dining render actually needs.
WANT = [
    ("sofa", 3), ("armchair", 2), ("pouf", 1), ("coffee_table", 2),
    ("shelf", 2), ("commode", 1), ("wardrobe", 1),
    ("pendant_light", 1), ("wall_sconce", 1),
    ("laminate_floor", 2), ("floor_tile", 1), ("porcelain_tile", 1),
    ("door", 1),
]
RANGE = {"sofa": (40, 450), "armchair": (30, 160), "pouf": (20, 150),
         "coffee_table": (25, 200), "shelf": (15, 250), "wardrobe": (30, 300),
         "commode": (25, 250), "pendant_light": (8, 200), "wall_sconce": (5, 200),
         "laminate_floor": (0.5, 250), "floor_tile": (0.5, 150),
         "porcelain_tile": (0.5, 150), "door": (2, 260)}

def to_cm(vals):
    present = [v for v in vals if v]
    if not present:
        return [None, None, None]
    scale = 100.0 if max(present) < 5 else 1.0
    return [round(v * scale, 1) if v else None for v in vals]

def plausible(dims, sub):
    lo, hi = RANGE.get(sub, (1, 400))
    got = [d for d in dims if d]
    return bool(got) and all(lo <= d <= hi for d in got)

scored = json.load(open("gorgia_scored.json", encoding="utf-8"))
by_sub = {}
for r in scored:
    L, W, H = to_cm(r["_dims"])
    # Gorgia "length" is the long horizontal dimension -> schema width
    if not plausible([L, W, H], r["subcategory"]):
        continue
    r["_cm"] = {"w": L, "d": W, "h": H}
    by_sub.setdefault(r["subcategory"], []).append(r)

picked = []
for sub, n in WANT:
    rows = sorted(by_sub.get(sub, []), key=lambda r: -r["_score"])
    if not rows:
        print(f"  ! {sub}: no product with usable data - dropped")
        continue
    picked.extend(rows[:n])
    got = rows[:n]
    print(f"  {sub:16s} {len(got)}/{n}  score {[r['_score'] for r in got]}")

# ---- translate names / assign style tags in one call ----
listing = [{"idx": i, "name": r["name_ka"], "sub": r["subcategory"],
            "color_ka": r["_f"].get("color"), "material_ka": r["_f"].get("material")}
           for i, r in enumerate(picked)]
PROMPT = """These are real products from Gorgia, a Georgian retailer. For each return:
 "idx": input index
 "name": concise English name (translate Georgian, keep model codes/brands verbatim)
 "color": the colour in English, translated from color_ka (null if absent)
 "material": the material in English, translated from material_ka (null if absent)
 "category": one of furniture|lighting|flooring|wall_finish|door
 "style_tags": 1-3 of [scandinavian,nordic,japandi,modern,contemporary,minimalist,industrial,classic,luxury,rustic,bohemian]
Return ONLY a JSON array.

PRODUCTS:
"""
body = json.dumps({"model": MODEL, "max_tokens": 8000,
                   "messages": [{"role": "user",
                                 "content": PROMPT + json.dumps(listing, ensure_ascii=False)}]}).encode()
req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                             headers={"content-type": "application/json",
                                      "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                      "anthropic-version": "2023-06-01"})
with urllib.request.urlopen(req, timeout=300) as resp:
    txt = json.load(resp)["content"][0]["text"].strip()
meta = {o["idx"]: o for o in json.loads(re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip())}

out = []
for i, r in enumerate(picked):
    m = meta.get(i, {})
    f = r["_f"]
    out.append({
        "id": f"GRG-{i+1:03d}", "supplier": "Gorgia",
        "name": m.get("name") or r["name_ka"], "name_original": r["name_ka"],
        "category": m.get("category") or "furniture", "subcategory": r["subcategory"],
        "style_tags": m.get("style_tags") or [], "color": m.get("color"),
        "material": m.get("material"),
        "dimensions_cm": r["_cm"], "dimensions_source": "feature table (validated)",
        "brand": f.get("brand"), "country_of_manufacture": f.get("country"),
        "price": r["price"], "currency": "GEL",
        "url": r["url"], "image_url": r.get("image_url"),
        "source": "scraped", "derived_fields": ["style_tags"],
    })

dest = sys.argv[1]
json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
full = sum(1 for x in out if all(x["dimensions_cm"].values()) and x["color"])
print(f"\n{len(out)} products -> {dest}   dims+colour complete: {full}/{len(out)}")
