"""Gorgia pass 3: lighting fixtures (not bulbs) + flooring."""
import json, re, time
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ka-GE,ka;q=0.9"})

SUBCATS = {
    "pendant_light": "https://gorgia.ge/ka/ganateba/shida-ganateba/cheris-sanati-chagi-sakidi/",
    "wall_sconce":   "https://gorgia.ge/ka/ganateba/shida-ganateba/kedlis-sanati-bra/",
    "table_lamp":    "https://gorgia.ge/ka/ganateba/shida-ganateba/abajuri-sanati/",
    "laminate_floor":"https://gorgia.ge/ka/remonti/iataki/laminirebuli-iataki/",
    "parquet_floor": "https://gorgia.ge/ka/remonti/iataki/parketi/",
    "vinyl_floor":   "https://gorgia.ge/ka/remonti/iataki/vinilis-iataki/",
    "carpet":        "https://gorgia.ge/ka/remonti/iataki/rbili-iataki/",
}

def money(t):
    m = re.search(r"[\d\s]+[.,]?\d*", t.replace(" ", " "))
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

result = {}
for key, url in SUBCATS.items():
    rows, seen = [], set()
    try:
        r = S.get(url, timeout=30)
        if r.status_code == 200:
            for row in parse(r.text):
                if row["url"] and row["price"] and row["url"] not in seen:
                    seen.add(row["url"])
                    row["subcategory"] = key
                    rows.append(row)
    except Exception as e:
        print(f"  !! {key}: {e}")
    result[key] = rows
    print(f"{key:16s} {len(rows):3d}")
    time.sleep(1.0)

json.dump(result, open("gorgia_extra.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("total", sum(len(v) for v in result.values()), "-> gorgia_extra.json")
