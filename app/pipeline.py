"""Orchestration: the three stages wired together.

Variations are independent scenes, so they are planned and rendered
concurrently. Within a scene the canonical render must exist before the other
viewpoints, which the renderer handles.
"""
import concurrent.futures as futures

from . import config, planner, renderer


def _one_variation(room, style, palette, index, viewpoints, quality):
    spec = planner.plan(room, style=style, palette=palette,
                        temperature=None if index == 0 else 1.0,
                        variation_index=index)
    renders = renderer.render(spec, viewpoints=viewpoints, quality=quality)
    spec["renders"] = renders
    planner.save(spec)
    return spec


def generate(room, style="scandinavian", palette="warm neutral",
             viewpoints=None, variations=None, quality=None, parallel=True):
    """Plan and render N design variations of one room."""
    n = variations or config.DEFAULT_VARIATIONS
    n = max(1, min(int(n), config.MAX_VARIATIONS))

    args = [(room, style, palette, i, viewpoints, quality) for i in range(n)]
    if parallel and n > 1:
        with futures.ThreadPoolExecutor(max_workers=n) as ex:
            specs = list(ex.map(lambda a: _one_variation(*a), args))
    else:
        specs = [_one_variation(*a) for a in args]

    return {
        "room": specs[0].get("room"),
        "style": style,
        "palette": palette,
        "image_model": config.image_model(quality),
        "variations": [summarise(s) for s in specs],
    }


def regenerate(scene_id, changes=None, viewpoints=None, quality=None):
    """Re-render a stored scene.

    With no `changes` the stored spec is re-rendered verbatim, so the scene is
    preserved by construction. With `changes`, the spec is amended first and the
    diff is reported, so it is visible exactly what moved and what did not.
    """
    spec = planner.load(scene_id)
    diff = None
    if changes:
        before = {p["catalog_id"]: p.get("position") for p in spec["placements"]}
        spec = planner.amend(spec, changes)
        after = {p["catalog_id"]: p.get("position") for p in spec["placements"]}
        diff = {
            "added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "moved": sorted(k for k in set(before) & set(after)
                            if before[k] != after[k]),
            "unchanged": sorted(k for k in set(before) & set(after)
                                if before[k] == after[k]),
        }
    spec["renders"] = renderer.render(spec, viewpoints=viewpoints, quality=quality)
    planner.save(spec)
    out = summarise(spec)
    out["changes_applied"] = diff
    return out


def summarise(spec):
    """The public shape of a generated scene."""
    products, total = [], 0.0
    for p in spec.get("placements") or []:
        products.append({
            "catalog_id": p["catalog_id"], "name": p["name"],
            "supplier": p["supplier"], "qty": p["qty"],
            "unit_price": p["unit_price"], "line_total": p["line_total"],
            "currency": p.get("currency", "GEL"), "url": p.get("url"),
            "position": p.get("position"),
        })
        total += p["line_total"] or 0

    finishes = []
    for key in ("floor", "walls"):
        block = spec.get(key) or {}
        for id_field in ("catalog_id", "pigment_id"):
            if block.get(id_field):
                price = block.get(f"{id_field}_price") or 0
                finishes.append({
                    "role": key, "catalog_id": block[id_field],
                    "name": block.get(f"{id_field}_name"),
                    "unit_price": price, "url": block.get(f"{id_field}_url"),
                })
                total += price

    return {
        "scene_id": spec["scene_id"],
        "variation_index": spec.get("variation_index", 0),
        "summary": spec.get("room_summary"),
        "renders": spec.get("renders") or [],
        "products": products,
        "finishes": finishes,
        "styling_only": spec.get("styling_only") or [],
        "estimated_total": round(total, 2),
        "currency": "GEL",
    }
