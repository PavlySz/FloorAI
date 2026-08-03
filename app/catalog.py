"""Catalog loading and search.

Every JSON file in catalog/ is a supplier. Adding one is a file copy: there is
no registry to update and no code change.
"""
import functools
import json

from . import config

# which subcategories are worth offering for a given room type
ROOM_RELEVANCE = {
    "living": ["sofa", "armchair", "pouf", "coffee_table", "shelf", "bookshelf",
               "commode", "console", "wall_unit", "showcase", "mirror",
               "pendant_light", "wall_sconce", "laminate_floor", "floor_tile",
               "porcelain_tile", "wall_paint", "paint_pigment", "door"],
    "bedroom": ["bed", "wardrobe", "commode", "nightstand", "armchair", "mirror",
                "pendant_light", "wall_sconce", "laminate_floor", "wall_paint",
                "paint_pigment", "door"],
    "kitchen": ["kitchen_unit", "kitchen_sink", "dining_table", "dining_chair",
                "pendant_light", "floor_tile", "porcelain_tile", "wall_paint",
                "paint_pigment"],
}
ROOM_RELEVANCE["living_kitchen"] = sorted(
    set(ROOM_RELEVANCE["living"]) | set(ROOM_RELEVANCE["kitchen"]))


@functools.lru_cache(maxsize=1)
def load_catalogs():
    """Merge every supplier file in the catalog directory."""
    items = []
    for path in sorted(config.CATALOG_DIR.glob("*.json")):
        items.extend(json.loads(path.read_text(encoding="utf-8")))
    return items


def suppliers():
    return sorted({i["supplier"] for i in load_catalogs()})


def _dims_ok(item, min_w=None, max_w=None):
    d = item.get("dimensions_cm") or {}
    w = d.get("w")
    if min_w is not None and (w is None or w < min_w):
        return False
    if max_w is not None and (w is None or w > max_w):
        return False
    return True


def search(category=None, subcategory=None, style=None, color=None,
           material=None, supplier=None, max_price=None, min_price=None,
           max_width_cm=None, min_width_cm=None, query=None, limit=None):
    """Filter the merged catalog. Every argument is optional."""
    out = []
    for it in load_catalogs():
        if category and it.get("category") != category:
            continue
        if subcategory and it.get("subcategory") != subcategory:
            continue
        if supplier and it.get("supplier") != supplier:
            continue
        if style and style.lower() not in [s.lower() for s in it.get("style_tags") or []]:
            continue
        if color and color.lower() not in (it.get("color") or "").lower():
            continue
        if material and material.lower() not in (it.get("material") or "").lower():
            continue
        price = it.get("price")
        if max_price is not None and (price is None or price > max_price):
            continue
        if min_price is not None and (price is None or price < min_price):
            continue
        if not _dims_ok(it, min_width_cm, max_width_cm):
            continue
        if query:
            hay = " ".join(str(it.get(k) or "") for k in
                           ("name", "name_original", "subcategory", "brand", "material"))
            if query.lower() not in hay.lower():
                continue
        out.append(it)
    out.sort(key=lambda i: (i.get("subcategory") or "", i.get("price") or 0))
    return out[:limit] if limit else out


def for_room(room_type, style=None):
    """The subset a planner should be offered for one room."""
    wanted = ROOM_RELEVANCE.get(room_type) or ROOM_RELEVANCE["living"]
    items = [i for i in load_catalogs() if i.get("subcategory") in wanted]
    if style:
        tagged = [i for i in items
                  if style.lower() in [s.lower() for s in i.get("style_tags") or []]]
        # never starve the planner: fall back to the full room set
        if len(tagged) >= 12:
            items = tagged
    return items


def by_id(catalog_id):
    for it in load_catalogs():
        if it["id"] == catalog_id:
            return it
    return None


def compact(items):
    """Trim to the fields a planner needs, to keep the prompt small."""
    out = []
    for i in items:
        d = i.get("dimensions_cm") or {}
        out.append({
            "id": i["id"], "name": i["name"], "subcategory": i.get("subcategory"),
            "color": i.get("color"), "material": i.get("material"),
            "w": d.get("w"), "d": d.get("d"), "h": d.get("h"),
            "price": i.get("price"), "supplier": i.get("supplier"),
        })
    return out
