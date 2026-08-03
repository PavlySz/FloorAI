"""Small end-to-end exercise of the FloorAI API.

Runs five requests against a running instance and writes every response, and the
generated images, to api_outputs/.

    python api_client.py                          # against localhost:8000
    python api_client.py http://<host>:8000       # against a deployment

Kept deliberately small: one variation and two viewpoints, on the fast model, so
a full pass costs about a minute rather than several.
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
OUT = Path(__file__).parent / "api_outputs"
PLAN = Path(__file__).parent / "samples" / "plan_1.png"

OUT.mkdir(exist_ok=True)
results = []


def record(name, ok, detail, payload=None):
    results.append({"test": name, "ok": ok, "detail": detail})
    print(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
    if payload is not None:
        (OUT / f"{name}.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")


def save_images(variation, prefix):
    """Pull the rendered PNGs down so the outputs stand alone."""
    saved = []
    for r in variation.get("renders", []):
        try:
            img = requests.get(f"{BASE}{r['url']}", timeout=60)
            if img.status_code == 200:
                fn = OUT / f"{prefix}_{r['id']}.png"
                fn.write_bytes(img.content)
                saved.append(fn.name)
        except requests.RequestException:
            pass
    return saved


# 1 -------------------------------------------------------------------------
def test_options():
    r = requests.get(f"{BASE}/api/options", timeout=30)
    r.raise_for_status()
    d = r.json()
    record("1_options", True,
           f"{d['catalog_size']} products from {', '.join(d['suppliers'])}, "
           f"{len(d['styles'])} styles", d)
    return d


# 2 -------------------------------------------------------------------------
def test_catalog_search():
    params = {"subcategory": "sofa", "max_price": 3000, "limit": 10}
    r = requests.get(f"{BASE}/api/catalog/search", params=params, timeout=30)
    r.raise_for_status()
    d = r.json()
    names = [f"{x['id']} {x['name'][:28]} {x['price']}" for x in d["results"][:3]]
    record("2_catalog_search", d["count"] > 0,
           f"sofas under 3000 GEL: {d['count']} -> {names}", d)


# 3 -------------------------------------------------------------------------
def test_analyze():
    with open(PLAN, "rb") as fh:
        r = requests.post(f"{BASE}/api/analyze",
                          files={"file": (PLAN.name, fh, "image/png")}, timeout=180)
    r.raise_for_status()
    d = r.json()
    rooms = ", ".join(f"{x['name']} {x['area_m2']}m2" for x in d["rooms"])
    record("3_analyze", bool(d["rooms"]), f"{len(d['rooms'])} rooms: {rooms}", d)
    return d


# 4 -------------------------------------------------------------------------
def test_generate(layout):
    room = next(x for x in layout["rooms"] if x["id"] == layout["default_room_id"])
    data = {
        "room_json": json.dumps(room), "style": "scandinavian",
        "palette": "warm neutral", "viewpoints": 2, "variations": 1,
        "quality": "fast",
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/api/generate", data=data, timeout=600)
    r.raise_for_status()
    d = r.json()
    v = d["variations"][0]
    imgs = save_images(v, "4_generate")
    record("4_generate", bool(v["products"]),
           f"{len(v['renders'])} renders, {len(v['products'])} products, "
           f"{v['estimated_total']} {v['currency']}, {time.time()-t0:.0f}s, "
           f"saved {len(imgs)} images", d)
    return v["scene_id"]


# 5 -------------------------------------------------------------------------
def test_regenerate(scene_id):
    """Re-render the stored scene unchanged: the scene must be preserved."""
    data = {"scene_id": scene_id, "viewpoints": 2, "quality": "fast"}
    r = requests.post(f"{BASE}/api/regenerate", data=data, timeout=600)
    r.raise_for_status()
    d = r.json()
    imgs = save_images(d, "5_regenerate")
    same = d["scene_id"] == scene_id
    record("5_regenerate", same,
           f"scene_id preserved={same}, {len(d['products'])} products unchanged, "
           f"saved {len(imgs)} images", d)


def main():
    print(f"FloorAI API client -> {BASE}\n")
    try:
        test_options()
        test_catalog_search()
        layout = test_analyze()
        scene_id = test_generate(layout)
        test_regenerate(scene_id)
    except requests.RequestException as e:
        record("connection", False, f"{type(e).__name__}: {e}")
    except Exception as e:  # keep the summary useful even on an unexpected failure
        record("unexpected", False, f"{type(e).__name__}: {e}")

    summary = {"base_url": BASE, "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "passed": sum(1 for x in results if x["ok"]), "total": len(results),
               "results": results}
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{summary['passed']}/{summary['total']} passed -> {OUT}/")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
