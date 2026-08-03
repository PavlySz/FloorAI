"""Stage 3: scene spec -> photorealistic renders from several viewpoints.

Consistency mechanism (star topology): the canonical view is rendered first, then
every other viewpoint is generated from the SAME compiled scene description plus
the canonical image as reference. No view is ever conditioned on another
generated view, so there is no drift to accumulate.

Two measured constraints shape the viewpoint list (see README "Findings"):
  1. Telling the model "only the camera moves" makes it re-emit the reference
     image. Each viewpoint therefore describes its TARGET FRAME instead.
  2. Near-180 degree reversals hallucinate duplicate furniture, because the
     reference image is the only spatial anchor. Viewpoints stay within a safe
     arc and always keep a shared landmark in frame.
"""
import concurrent.futures as futures


from . import config
from .llm import gemini_image

# Camera positions, ordered. Each states where the camera is, what is behind it,
# and how the frame is composed -- never "rotate the camera by N degrees".
VIEWPOINTS = [
    {
        "id": "canonical",
        "label": "Wide establishing view",
        "frame": ("Wide-angle establishing shot from the corner that shows the most "
                  "of the room at once. The main seating group is centred in frame "
                  "with the window visible. Camera at standing eye height, 1.6m."),
    },
    {
        "id": "opposite_corner",
        "label": "Opposite corner",
        "frame": ("CAMERA POSITION: the adjacent corner, roughly 90 degrees around "
                  "the room from the establishing shot, still at 1.6m eye height.\n"
                  "FRAMING: the main seating group is now seen from its side rather "
                  "than head-on. The wall that was behind the camera in the "
                  "establishing shot is now visible in the background. At least one "
                  "large landmark object from the establishing shot stays clearly in "
                  "frame so the two photographs are recognisably the same room."),
    },
    {
        "id": "seating_detail",
        "label": "Seating detail",
        "frame": ("CAMERA POSITION: low and close, about 1.0m above the floor, a "
                  "couple of metres from the main seating group.\n"
                  "FRAMING: a tighter three-quarter detail shot. The coffee table or "
                  "low table fills the foreground, the main sofa fills the middle of "
                  "frame behind it, the floor covering is prominent in the lower "
                  "frame. Shallow depth of field, background softly out of focus."),
    },
    # Ordered by how far each sits from the establishing shot, because the first
    # N are what a default run uses. The doorway view is deliberately LAST of the
    # wide shots: the establishing shot is usually taken from near the doorway
    # already, so the two frames overlap and the render comes back near-identical.
    {
        "id": "window_side",
        "label": "From the window side",
        "frame": ("CAMERA POSITION: beside the window, angled back across the room "
                  "at about 45 degrees -- NOT directly facing away from the window.\n"
                  "FRAMING: daylight falls toward the camera across the furniture. "
                  "The main seating group and at least one tall item (shelf, wardrobe "
                  "or unit) are both in frame. Part of the window frame or curtain "
                  "stays visible at the edge as a shared landmark."),
    },
    {
        "id": "dining_or_secondary",
        "label": "Secondary zone",
        "frame": ("CAMERA POSITION: facing the room's secondary zone (dining table, "
                  "kitchen run, or desk if present; otherwise the tallest storage "
                  "piece), at 1.6m eye height.\n"
                  "FRAMING: that zone fills the middle of frame, with the main "
                  "seating group partly visible at the edge of frame to anchor the "
                  "two photographs as the same space."),
    },
    {
        "id": "doorway",
        "label": "From the doorway",
        "frame": ("CAMERA POSITION: standing in the room's main doorway looking in, "
                  "at 1.6m eye height, deliberately further back than the "
                  "establishing shot and offset to one side of it.\n"
                  "FRAMING: the natural 'walking in' view. The room reads in depth, "
                  "with the near edge of the floor covering in the lower frame and "
                  "the window wall furthest away. Furniture is seen at an angle, not "
                  "square-on. Keep the main seating group clearly visible."),
    },
]

# Render files are named by viewpoint id, so a duplicate would silently overwrite.
assert len({v["id"] for v in VIEWPOINTS}) == len(VIEWPOINTS), "duplicate viewpoint id"

BASE_RULES = (
    "Photorealistic architectural interior photograph. Natural daylight plus the "
    "room's own fixtures. Correct perspective, no fisheye distortion, verticals "
    "straight. No people, no text, no watermarks, no floor plans."
)


def compile_scene(spec):
    """Compile a scene spec into the scene description text.

    Pure function: the same spec always produces byte-identical text. Every
    viewpoint call reuses this exact block, which is what holds the scene stable.
    """
    room = spec.get("room") or {}
    dims = room.get("approx_dimensions_m") or {}
    lines = []

    size = ""
    if dims.get("w") and dims.get("l"):
        size = f", approximately {dims['w']}m by {dims['l']}m"
    lines.append(
        f"A {room.get('area_m2')} square metre {room.get('name') or 'room'}"
        f"{size}, styled {spec.get('style')} with a {spec.get('palette')} palette.")

    floor = spec.get("floor") or {}
    if floor.get("description"):
        lines.append(f"FLOOR: {floor['description']}")
    walls = spec.get("walls") or {}
    if walls.get("description"):
        lines.append(f"WALLS: {walls['description']}")

    lines.append("\nFURNITURE AND FIXTURES - fixed identity and fixed positions:")
    for p in spec.get("placements") or []:
        d = p.get("dimensions_cm") or {}
        size_txt = ""
        if d.get("w") and d.get("h"):
            size_txt = f" ({d['w']:g}cm wide, {d['h']:g}cm tall)"
        desc = ", ".join(x for x in (p.get("color"), p.get("material")) if x)
        qty = f"{p['qty']}x " if p.get("qty", 1) > 1 else ""
        lines.append(
            f"- {qty}{p['name']}{size_txt}"
            + (f" [{desc}]" if desc else "")
            + f": {p.get('position')}"
            + (f". {p['notes']}" if p.get("notes") else ""))

    styling = spec.get("styling_only") or []
    if styling:
        lines.append("\nSOFT FURNISHINGS AND DECOR - also fixed in place:")
        for s in styling:
            lines.append(f"- {s.get('item')}: {s.get('description')}"
                         + (f" Positioned {s['position']}." if s.get("position") else ""))

    if spec.get("lighting"):
        lines.append(f"\nLIGHTING: {spec['lighting']}")
    return "\n".join(lines)


def _canonical_prompt(scene_text, viewpoint):
    return (f"{scene_text}\n\nCAMERA: {viewpoint['frame']}\n\n{BASE_RULES}")


def _identity_checklist(spec):
    """Name the objects that must survive the camera move, and their count.

    The stronger model moves the camera properly but reinterprets objects -- a
    bookshelf becomes a sideboard, one artwork becomes another. Enumerating the
    inventory with explicit counts gives it something to check itself against,
    and the counts are what stop a single armchair becoming two.
    """
    lines = []
    for p in spec.get("placements") or []:
        qty = p.get("qty") or 1
        desc = ", ".join(x for x in (p.get("color"), p.get("material")) if x)
        lines.append(f"- exactly {qty} x {p['name']}" + (f" ({desc})" if desc else ""))
    for s in spec.get("styling_only") or []:
        lines.append(f"- {s.get('item')}: {s.get('description')}")
    return "\n".join(lines)


def _viewpoint_prompt(scene_text, viewpoint, spec):
    return (
        "The attached photograph is the GROUND TRUTH for this room.\n"
        "Where the photograph and the text below disagree, THE PHOTOGRAPH WINS.\n\n"
        "Your task is to photograph this same, already-furnished room from one "
        "different camera position. You are NOT redesigning it and NOT restyling "
        "it. Use the photograph for object identity only -- do not copy its "
        "framing.\n\n"
        f"{scene_text}\n\n"
        "OBJECT INVENTORY - every one of these must appear exactly as it does in "
        "the attached photograph, in the same place, at the same size, in the same "
        "colour and material, and in exactly this quantity:\n"
        f"{_identity_checklist(spec)}\n\n"
        "FORBIDDEN: adding a second copy of any object; substituting one piece of "
        "furniture for a different type (a tall shelf must not become a low "
        "sideboard); changing any artwork to a different picture; changing the "
        "shape, colour or mounting of the light fittings; restyling the room; "
        "altering walls, floor, ceiling, windows or doors. The ONLY difference "
        "from the attached photograph is where the photographer stands.\n\n"
        f"{viewpoint['frame']}\n\n"
        f"{BASE_RULES} It must read as a genuinely different photograph of the "
        "same unchanged room.")


def render(spec, viewpoints=None, quality=None, parallel=True):
    """Render a scene from several viewpoints.

    The canonical view is rendered first because every other view is conditioned
    on it. The rest are independent of each other, so they run concurrently.
    """
    n = viewpoints or config.DEFAULT_VIEWPOINTS
    n = max(1, min(int(n), config.MAX_VIEWPOINTS, len(VIEWPOINTS)))
    chosen = VIEWPOINTS[:n]
    model = config.image_model(quality)
    scene_text = compile_scene(spec)

    out_dir = config.RENDERS_DIR / spec["scene_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.txt").write_text(scene_text, encoding="utf-8")

    results = []
    canonical_vp = chosen[0]
    canonical_png = gemini_image(_canonical_prompt(scene_text, canonical_vp), model=model)
    (out_dir / f"{canonical_vp['id']}.png").write_bytes(canonical_png)
    results.append({"id": canonical_vp["id"], "label": canonical_vp["label"],
                    "url": f"/renders/{spec['scene_id']}/{canonical_vp['id']}.png",
                    "is_canonical": True})

    rest = chosen[1:]
    if not rest:
        return results

    def one(vp):
        png = gemini_image(_viewpoint_prompt(scene_text, vp, spec),
                           reference_png=canonical_png, model=model)
        (out_dir / f"{vp['id']}.png").write_bytes(png)
        return {"id": vp["id"], "label": vp["label"],
                "url": f"/renders/{spec['scene_id']}/{vp['id']}.png",
                "is_canonical": False}

    if parallel and len(rest) > 1:
        with futures.ThreadPoolExecutor(max_workers=len(rest)) as ex:
            done = list(ex.map(one, rest))
    else:
        done = [one(vp) for vp in rest]

    results.extend(done)
    return results
