"""Add Gorgia's wall-paint system to the catalog.

Gorgia sells interior wall paint only as a white base; colour comes from a
separate tinting pigment (Kolorex, 4.75 GEL / 100ml). So the catalog carries the
base and the pigments as distinct SKUs, and a chosen palette resolves to a real
pigment product rather than a prompt-only colour word.

Self-contained: scrapes the two categories it needs, then appends.

    python append_paint.py
"""
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CATALOG = Path(__file__).resolve().parent.parent / "catalog" / "gorgia.json"

WALL_PAINT = ("https://gorgia.ge/ka/remonti/laq-sagebavebi/sagebavi/"
              "kedlis-da-cheris-sagebavi/")
PIGMENT = ("https://gorgia.ge/ka/remonti/laq-sagebavebi/sagebavi/"
           "sagebavis-pigmenti/")

WANT_BASE = "ინტერიერის წყალემულსია Plus 7.5ლტ თეთრი"
WANT_PIGMENTS = ["# 41", "# 40", "# 11"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ka-GE,ka;q=0.9"})


def scrape(url):
    rows, seen = [], set()
    soup = BeautifulSoup(S.get(url, timeout=30).text, "html.parser")
    for it in soup.select("div.ut2-gl__item, div.ut2-gl__body"):
        a = it.select_one("a.product-title") or it.select_one(".ut2-gl__name a")
        p = it.select_one(".ty-price-num")
        if not a or not p or a.get("href") in seen:
            continue
        seen.add(a.get("href"))
        m = re.search(r"[\d\s]+[.,]?\d*", p.get_text().replace(" ", " "))
        price = float(m.group(0).replace(" ", "").replace(",", ".")) if m else None
        if price:
            rows.append({"name_ka": a.get_text(strip=True),
                         "url": a.get("href"), "price": price})
    return rows


def find(pool, needle):
    return next((r for r in pool if needle in r["name_ka"]), None)


def main():
    print("scraping wall paint and pigment categories...")
    paints = scrape(WALL_PAINT)
    time.sleep(1)
    pigments = scrape(PIGMENT)
    print(f"  {len(paints)} wall paints, {len(pigments)} pigments")

    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    # drop what a previous run added, so this is safe to re-run
    rows = [r for r in rows
            if r.get("subcategory") not in ("wall_paint", "paint_pigment")]

    new = []
    base = find(paints, WANT_BASE) or (paints[0] if paints else None)
    if base:
        new.append((base, {
            "name": "Interior water emulsion paint Plus 7.5L white",
            "subcategory": "wall_paint", "color": "white",
            "material": "water-based emulsion",
            "style_tags": ["modern", "minimalist", "scandinavian"],
            "note": "7.5 L white base; tint with a pigment below",
        }))

    seen = set()
    for want in WANT_PIGMENTS:
        p = next((r for r in pigments
                  if want in r["name_ka"] and r["url"] not in seen), None)
        if not p:
            continue
        seen.add(p["url"])
        ka = p["name_ka"]
        color = ("light green" if "ღია მწვანე" in ka else
                 "green" if "მწვანე" in ka else
                 "lemon" if "ლიმნის" in ka else None)
        num = re.search(r"#\s*(\d+)", ka)
        new.append((p, {
            "name": f"Kolorex tinting pigment #{num.group(1) if num else '?'} 100ml"
                    + (f" ({color})" if color else ""),
            "subcategory": "paint_pigment", "color": color,
            "material": "pigment concentrate",
            "style_tags": ["modern", "contemporary"],
            "note": "tints white base emulsion",
        }))

    start = max((int(r["id"].split("-")[1]) for r in rows), default=0) + 1
    for i, (raw, meta) in enumerate(new):
        rows.append({
            "id": f"GRG-{start+i:03d}", "supplier": "Gorgia",
            "name": meta["name"], "name_original": raw["name_ka"],
            "category": "wall_finish", "subcategory": meta["subcategory"],
            "style_tags": meta["style_tags"], "color": meta["color"],
            "material": meta["material"],
            "dimensions_cm": {"w": None, "d": None, "h": None},
            "dimensions_source": None, "price": raw["price"], "currency": "GEL",
            "url": raw["url"], "image_url": None, "source": "scraped",
            "derived_fields": ["style_tags"], "coverage_note": meta["note"],
        })
        print(f"  + {rows[-1]['id']} {rows[-1]['name'][:48]:50s} "
              f"{rows[-1]['price']:>7} GEL")

    CATALOG.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"gorgia.json now {len(rows)} products")


if __name__ == "__main__":
    main()
