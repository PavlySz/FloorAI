"""Scrape comforter.ge: discover subcategory pages, then parse product cards."""
import json, re, time
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
BASE = "https://comforter.ge"

TOP = ["upholstered-furniture", "living-room-furniture", "bedroom-furniture",
       "table-chair", "bathroom-furniture"]

def money(t):
    m = re.search(r"\d[\d\s,]*", t)
    return float(m.group(0).replace(" ", "").replace(",", "")) if m else None

def parse_cards(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a.catSlideItem"):
        name = a.select_one(".favItmModel")
        typ = a.select_one(".favItmType")
        prices = [money(p.get_text()) for p in a.select(".favItmPrice")]
        prices = [p for p in prices if p]
        img = a.select_one(".catSlImg .img")
        img_url = None
        if img and img.get("style"):
            m = re.search(r"url\('?([^')]+)'?\)", img["style"])
            if m:
                img_url = m.group(1)
                if not img_url.startswith("http"):
                    img_url = f"{BASE}/{img_url.lstrip('/')}"
        if not name or not prices:
            continue
        out.append({
            "name": name.get_text(strip=True),
            "type": typ.get_text(strip=True) if typ else None,
            # when discounted the first price is the sale price, second the original
            "price": min(prices),
            "price_original": max(prices) if len(prices) > 1 else None,
            "url": a.get("href"),
            "image_url": img_url,
        })
    return out

def main():
    subcats = {}
    for top in TOP:
        try:
            r = S.get(f"{BASE}/en/products/{top}", timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a.findAll"):
                href = a.get("href")
                if href and "/products/" in href:
                    subcats[href] = top
        except Exception as e:
            print(f"!! {top}: {e}")
        time.sleep(0.8)
    print(f"discovered {len(subcats)} subcategory pages")

    result, seen = {}, set()
    for url, top in subcats.items():
        key = url.rstrip("/").split("/")[-1]
        try:
            r = S.get(url, timeout=30)
            rows = [x for x in parse_cards(r.text)
                    if x["url"] and x["url"] not in seen and not seen.add(x["url"])]
        except Exception as e:
            print(f"!! {key}: {e}")
            rows = []
        for x in rows:
            x["top_category"] = top
            x["subcategory"] = key
        result[key] = rows
        print(f"  {key:26s} {len(rows):3d}")
        time.sleep(0.8)

    with open("comforter_raw.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("total", sum(len(v) for v in result.values()), "-> comforter_raw.json")

if __name__ == "__main__":
    main()
