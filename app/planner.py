"""Stage 2: room + style + catalog -> scene spec.

The scene spec is the durable artifact of the whole system. It fixes every
object, its catalog id and its position *before* any image exists, which is what
lets consistency, variations and regeneration all fall out of one mechanism.
"""
import json
import uuid

from . import catalog, config
from .llm import claude

STYLES = ["scandinavian", "nordic", "japanese", "japandi", "modern",
          "contemporary", "minimalist", "industrial", "classic", "luxury",
          "rustic", "bohemian"]

PALETTES = {
    "warm neutral": "warm whites, oatmeal, camel, pale oak",
    "cool neutral": "cool white, soft grey, pale concrete, black accents",
    "earth": "terracotta, clay, olive, warm brown",
    "monochrome": "white, charcoal, black, silver",
    "green": "sage and forest green with natural oak",
    "blue": "dusty and navy blue with warm wood",
}

PROMPT = """You are an interior designer furnishing ONE room. Return a JSON scene spec.

ROOM
{room}

STYLE: {style}
PALETTE: {palette} ({palette_desc})

CATALOG - you may ONLY place items from this list, by id:
{items}

Return this exact JSON:
{{
 "room_summary": "one sentence describing the finished room",
 "floor": {{"catalog_id": "id or null", "description": "what the floor looks like"}},
 "walls": {{"catalog_id": "id or null", "pigment_id": "id or null",
            "description": "wall colour and finish"}},
 "placements": [
   {{"catalog_id": "GRG-001", "name": "...", "qty": 1,
     "position": "against the west wall, centred, facing east",
     "facing": "east",
     "notes": "anything about how it reads in the room"}}
 ],
 "styling_only": [
   {{"item": "rug", "description": "large flat-weave jute rug, 200x300cm, natural beige",
     "position": "under the coffee table, centred on the seating group"}}
 ],
 "lighting": "how the room is lit, day and artificial",
 "camera_anchor": "the most natural corner to photograph the room from, and what is visible"
}}

RULES
- Every entry in "placements" MUST use a real catalog_id from the list above.
- Respect the room's dimensions: total furniture footprint must fit. Use the
  w/d/h given for each item (centimetres).
- "styling_only" is for things NEITHER supplier sells - rug, curtains, plants,
  artwork, cushions. Describe them precisely; they are rendered but never priced.
- Give every placement an unambiguous position relative to walls and other
  objects. Another designer must be able to lay the room out from this text alone.
- Use compass directions (north/south/east/west wall) consistently.
- Do not place more than fits comfortably. A believable room beats a full one.
Return ONLY the JSON object.
"""


def _room_block(room):
    d = room.get("approx_dimensions_m") or {}
    return json.dumps({
        "name": room.get("name"), "type": room.get("type"),
        "area_m2": room.get("area_m2"),
        "width_m": d.get("w"), "length_m": d.get("l"),
        "windows": room.get("windows"), "doors": room.get("doors"),
        "existing_fixtures": room.get("existing_fixtures"),
        "notes": room.get("notes"),
    }, ensure_ascii=False, indent=1)


def plan(room, style="scandinavian", palette="warm neutral", temperature=None,
         variation_index=0):
    """Produce one scene spec for one room."""
    style = (style or "scandinavian").lower()
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")
    palette_desc = PALETTES.get(palette, palette)

    items = catalog.for_room(room.get("type") or "living", style)
    prompt = PROMPT.format(
        room=_room_block(room), style=style, palette=palette,
        palette_desc=palette_desc,
        items=json.dumps(catalog.compact(items), ensure_ascii=False, indent=1))
    if variation_index:
        prompt += (f"\nThis is design variation #{variation_index + 1}. Make it "
                   "meaningfully different from an obvious first choice: different "
                   "hero furniture, a different layout, a different accent colour "
                   "within the same palette.")

    spec = claude(prompt, temperature=temperature, max_tokens=6000)
    return _validate(spec, room, style, palette, variation_index)


def _validate(spec, room, style, palette, variation_index):
    """Drop hallucinated ids and attach costed catalog data."""
    dropped = []
    placements = []
    for p in spec.get("placements") or []:
        item = catalog.by_id(p.get("catalog_id"))
        if not item:
            dropped.append(p.get("catalog_id"))
            continue
        qty = int(p.get("qty") or 1)
        placements.append({
            "catalog_id": item["id"], "name": item["name"], "supplier": item["supplier"],
            "subcategory": item.get("subcategory"), "qty": qty,
            "unit_price": item.get("price"), "currency": item.get("currency", "GEL"),
            "line_total": round((item.get("price") or 0) * qty, 2),
            "url": item.get("url"), "dimensions_cm": item.get("dimensions_cm"),
            "color": item.get("color"), "material": item.get("material"),
            "position": p.get("position"), "facing": p.get("facing"),
            "notes": p.get("notes"),
        })
    spec["placements"] = placements

    # floor and walls are catalog-linked too, and are costed if present
    for key in ("floor", "walls"):
        block = spec.get(key) or {}
        for id_field in ("catalog_id", "pigment_id"):
            item = catalog.by_id(block.get(id_field))
            if item:
                block[f"{id_field}_name"] = item["name"]
                block[f"{id_field}_price"] = item.get("price")
                block[f"{id_field}_url"] = item.get("url")
            elif block.get(id_field):
                dropped.append(block[id_field])
                block[id_field] = None
        spec[key] = block

    spec["scene_id"] = uuid.uuid4().hex[:12]
    spec["room"] = {k: room.get(k) for k in
                    ("id", "name", "type", "area_m2", "approx_dimensions_m")}
    spec["style"] = style
    spec["palette"] = palette
    spec["variation_index"] = variation_index
    spec["hallucinated_ids_dropped"] = dropped
    spec["estimated_total"] = round(
        sum(p["line_total"] for p in placements)
        + sum(v for k in ("floor", "walls") for kk, v in (spec.get(k) or {}).items()
              if kk.endswith("_price") and isinstance(v, (int, float))), 2)
    return spec


AMEND_PROMPT = """You are amending an existing interior scene spec.

CURRENT SCENE
{spec}

CATALOG - you may only introduce items from this list, by id:
{items}

REQUESTED CHANGE
{changes}

Apply ONLY what was asked. Every placement the user did not mention must be
returned byte-for-byte unchanged: same catalog_id, same qty, same position text.
Do not re-word, re-order or "improve" untouched entries.

Return the COMPLETE amended spec in the same JSON shape as the current scene
(room_summary, floor, walls, placements, styling_only, lighting, camera_anchor).
Return ONLY the JSON object.
"""


def amend(spec, changes):
    """Apply a change request to a stored spec, preserving everything else."""
    room = spec.get("room") or {}
    items = catalog.for_room(room.get("type") or "living", spec.get("style"))
    trimmed = {k: spec.get(k) for k in
               ("room_summary", "floor", "walls", "placements", "styling_only",
                "lighting", "camera_anchor")}
    amended = claude(
        AMEND_PROMPT.format(
            spec=json.dumps(trimmed, ensure_ascii=False, indent=1),
            items=json.dumps(catalog.compact(items), ensure_ascii=False, indent=1),
            changes=changes),
        max_tokens=6000)

    out = _validate(amended, room, spec.get("style"), spec.get("palette"),
                    spec.get("variation_index", 0))
    # regeneration keeps the same scene identity
    out["scene_id"] = spec["scene_id"]
    out["amended_from"] = changes
    return out


def save(spec):
    path = config.SCENES_DIR / f"{spec['scene_id']}.json"
    path.write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load(scene_id):
    path = config.SCENES_DIR / f"{scene_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown scene_id {scene_id}")
    return json.loads(path.read_text(encoding="utf-8"))
