"""Targeted Gorgia scrape: only subcategories visible in an interior render."""
import json, re, time
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8"})

SUBCATS = {
    "sofa":      "https://gorgia.ge/ka/aveji/rbili-aveji/divnebi/",
    "armchair":  "https://gorgia.ge/ka/aveji/skamebi/misagebi-otaxis-skami/",
    "pouf":      "https://gorgia.ge/ka/aveji/rbili-aveji/pufebi/",
    "coffee_table": "https://gorgia.ge/ka/aveji/magidebi-da-merxebi/yavis-magida/",
    "dining_chair": "https://gorgia.ge/ka/aveji/skamebi/samzareulos-skami-da-tabureti/",
    "shelf":     "https://gorgia.ge/ka/aveji/karadebi-da-taroebi/taro/",
    "wardrobe":  "https://gorgia.ge/ka/aveji/karadebi-da-taroebi/tansacmlis-karada/",
    "commode":   "https://gorgia.ge/ka/aveji/komodi-da-tumbo/komodi/",
    "ceiling_light": "https://gorgia.ge/ka/ganateba/shida-ganateba/natura/",
    "floor_tile":"https://gorgia.ge/ka/remonti/keramikuli-filebi/iatakis-fila/",
    "porcelain_tile":"https://gorgia.ge/ka/remonti/keramikuli-filebi/keramogranitis-fila/",
    "paint":     "https://gorgia.ge/ka/remonti/laq-sagebavebi/sagebavi/",
    "door":      "https://gorgia.ge/ka/remonti/kari/mdf-kari/",
}

def money(txt):
    m = re.search(r"[\d\s]+[.,]?\d*", txt.replace(" ", " "))
    return float(m.group(0).replace(" ", "").replace(",", ".")) if m else None

def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for item in soup.select("div.ut2-gl__item, div.ut2-gl__body"):
        a = item.select_one("a.product-title") or item.select_one(".ut2-gl__name a")
        if not a:
            continue
        p = item.select_one(".ty-price-num")
        img = item.select_one("img")
        out.append({
            "name_ka": a.get_text(strip=True),
            "url": a.get("href"),
            "price": money(p.get_text()) if p else None,
            "image_url": (img.get("data-src") or img.get("src")) if img else None,
        })
    return out

def main():
    result = {}
    for key, url in SUBCATS.items():
        rows, seen = [], set()
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                for row in parse(r.text):
                    if row["url"] and row["url"] not in seen and row["price"]:
                        seen.add(row["url"])
                        row["subcategory"] = key
                        rows.append(row)
        except Exception as e:
            print(f"  !! {key}: {e}")
        result[key] = rows
        print(f"{key:16s} {len(rows):3d}")
        time.sleep(1.0)
    with open("gorgia_targeted.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("total", sum(len(v) for v in result.values()), "-> gorgia_targeted.json")

if __name__ == "__main__":
    main()
