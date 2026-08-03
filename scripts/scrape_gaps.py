"""Close the category gaps against the brief's own descriptions of each supplier.

Brief: Gorgia carries "... bathroom and kitchen products"; Comforter carries
"... wardrobes, office furniture, mattresses, textiles and home accessories".
Those categories were missing from the first curation pass.
"""
import json, re, time
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ka-GE,ka;q=0.9,en;q=0.8"})

GORGIA = {
    "bathroom_vanity": "https://gorgia.ge/ka/santeqnika/saabazanos-aveji/",
    "toilet":          "https://gorgia.ge/ka/santeqnika/unitazi-da-makompleqteblebi/",
    "washbasin":       "https://gorgia.ge/ka/santeqnika/xelsabani-da-aqsesuarebi/",
    "bathtub":         "https://gorgia.ge/ka/santeqnika/abazana-da-sashxape-kabina/",
    "tap":             "https://gorgia.ge/ka/santeqnika/onkanebi-da-sashxape-sistemebi/",
    "kitchen_unit":    "https://gorgia.ge/ka/aveji/samzareulos-aveji/samzareulos-garnituri/",
    "kitchen_sink":    "https://gorgia.ge/ka/aveji/samzareulos-aveji/samzareulos-nijara/",
}
COMFORTER_TOP = ["office", "mattress", "textile"]
BASE = "https://comforter.ge"

def money_ka(t):
    m = re.search(r"[\d\s]+[.,]?\d*", t.replace(" ", " "))
    return float(m.group(0).replace(" ", "").replace(",", ".")) if m else None

def parse_gorgia(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for it in soup.select("div.ut2-gl__item, div.ut2-gl__body"):
        a = it.select_one("a.product-title") or it.select_one(".ut2-gl__name a")
        p = it.select_one(".ty-price-num")
        img = it.select_one("img")
        if not a or not p:
            continue
        out.append({"name_ka": a.get_text(strip=True), "url": a.get("href"),
                    "price": money_ka(p.get_text()),
                    "image_url": (img.get("data-src") or img.get("src")) if img else None})
    return out

def parse_comforter(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a.catSlideItem"):
        name = a.select_one(".favItmModel")
        typ = a.select_one(".favItmType")
        prices = [p for p in (re.search(r"\d[\d\s,]*", x.get_text()) for x in
                              a.select(".favItmPrice")) if p]
        prices = [float(p.group(0).replace(" ", "").replace(",", "")) for p in prices]
        if not name or not prices:
            continue
        img = a.select_one(".catSlImg .img")
        iu = None
        if img and img.get("style"):
            m = re.search(r"url\('?([^')]+)'?\)", img["style"])
            if m:
                iu = m.group(1)
                iu = iu if iu.startswith("http") else f"{BASE}/{iu.lstrip('/')}"
        out.append({"name": name.get_text(strip=True),
                    "type": typ.get_text(strip=True) if typ else None,
                    "price": min(prices), "url": a.get("href"), "image_url": iu})
    return out

res = {}
for key, url in GORGIA.items():
    try:
        rows = [r for r in parse_gorgia(S.get(url, timeout=30).text) if r["price"]]
    except Exception as e:
        print(f"!! {key}: {e}"); rows = []
    seen, uniq = set(), []
    for r in rows:
        if r["url"] not in seen:
            seen.add(r["url"]); r["subcategory"] = key; uniq.append(r)
    res[key] = uniq
    print(f"gorgia  {key:18s} {len(uniq):3d}")
    time.sleep(0.9)
json.dump(res, open("gorgia_gaps.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

cres = {}
for top in COMFORTER_TOP:
    try:
        soup = BeautifulSoup(S.get(f"{BASE}/en/products/{top}", timeout=30).text, "html.parser")
        subs = {a.get("href") for a in soup.select("a.findAll") if a.get("href")}
    except Exception as e:
        print(f"!! {top}: {e}"); subs = set()
    for su in subs:
        key = su.rstrip("/").split("/")[-1]
        try:
            rows = parse_comforter(S.get(su, timeout=30).text)
        except Exception as e:
            print(f"!! {key}: {e}"); rows = []
        for r in rows:
            r["subcategory"] = key; r["top_category"] = top
        cres[key] = rows
        print(f"comfort {key:18s} {len(rows):3d}")
        time.sleep(0.9)
json.dump(cres, open("comforter_gaps.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
