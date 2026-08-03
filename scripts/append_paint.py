"""Replace the placeholder paint record with a real wall-paint system.

Gorgia sells interior wall paint only as a white base; colour comes from a
separate tinting pigment (Kolorex, 4.75 GEL / 100ml). So the catalog carries the
base and the pigments as distinct SKUs, and a chosen palette resolves to a real
pigment product rather than a prompt-only colour word.
"""
import json, re, sys

CATALOG = ("d:/upwork_and_other_projects/upwork_floor_ai/assessment/"
           "floorai/catalog/gorgia.json")

WANT_BASE = "ინტერიერის წყალემულსია Plus 7.5ლტ თეთრი"
WANT_PIGMENTS = ["# 41", "# 40", "# 11"]

def find(pool, needle):
    for r in pool:
        if needle in r["name_ka"]:
            return r
    return None

paints = json.load(open("paint_pool.json", encoding="utf-8"))
pigments = json.load(open("pigment_pool.json", encoding="utf-8"))
rows = json.load(open(CATALOG, encoding="utf-8"))

# drop the placeholder ceramic paint picked by the generic scrape
rows = [r for r in rows if "კერამიკის საღებავი" not in (r.get("name_original") or "")]

new = []
base = find(paints, WANT_BASE)
if base:
    new.append((base, {
        "name": "Interior water emulsion paint Plus 7.5L white",
        "category": "wall_finish", "subcategory": "wall_paint",
        "color": "white", "material": "water-based emulsion",
        "style_tags": ["modern", "minimalist", "scandinavian"],
        "dimensions_cm": {"w": None, "d": None, "h": None},
        "coverage_note": "7.5 L base; tint with a pigment below",
    }))

seen = set()
for want in WANT_PIGMENTS:
    p = next((r for r in pigments if want in r["name_ka"] and r["url"] not in seen), None)
    if not p:
        continue
    seen.add(p["url"])
    ka = p["name_ka"]
    color = ("green" if "მწვანე" in ka and "ღია" not in ka else
             "light green" if "ღია მწვანე" in ka else
             "lemon" if "ლიმნის" in ka else None)
    num = re.search(r"#\s*(\d+)", ka)
    new.append((p, {
        "name": f"Kolorex tinting pigment #{num.group(1) if num else '?'} 100ml"
                + (f" ({color})" if color else ""),
        "category": "wall_finish", "subcategory": "paint_pigment",
        "color": color, "material": "pigment concentrate",
        "style_tags": ["modern", "contemporary"],
        "dimensions_cm": {"w": None, "d": None, "h": None},
        "coverage_note": "tints white base emulsion",
    }))

start = max(int(r["id"].split("-")[1]) for r in rows) + 1
for i, (raw, meta) in enumerate(new):
    rec = {
        "id": f"GRG-{start+i:03d}", "supplier": "Gorgia",
        "name": meta["name"], "name_original": raw["name_ka"],
        "category": meta["category"], "subcategory": meta["subcategory"],
        "style_tags": meta["style_tags"], "color": meta["color"],
        "material": meta["material"], "dimensions_cm": meta["dimensions_cm"],
        "dimensions_source": None, "price": raw["price"], "currency": "GEL",
        "url": raw["url"], "image_url": None, "source": "scraped",
        "derived_fields": ["style_tags"], "coverage_note": meta["coverage_note"],
    }
    rows.append(rec)
    print(f"  + {rec['id']} {rec['name'][:52]:54s} {rec['price']:>7} GEL")

json.dump(rows, open(CATALOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"gorgia.json now {len(rows)} products")
