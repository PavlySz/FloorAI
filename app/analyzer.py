"""Stage 1: floor plan -> structured rooms.

Accepts PNG/JPG/JPEG/PDF. PDFs are rasterised first. One vision call returns a
strict JSON description of the layout; no CV model is involved.
"""
import io
import json

from .llm import claude

SUPPORTED = {".png", ".jpg", ".jpeg", ".pdf"}

PROMPT = """You are reading an architectural floor plan. Return a JSON description of it.

{
 "unit_label": "the overall unit name/number if printed, else null",
 "total_area_m2": number or null,
 "scale_available": true if any linear dimensions (mm/cm/m) are printed, else false,
 "rooms": [
   {
     "id": "room-1",
     "name": "short label, printed if present else inferred (e.g. 'Living / Kitchen')",
     "type": "one of living|kitchen|living_kitchen|bedroom|bathroom|wc|hall|balcony|storage|office",
     "area_m2": number or null,
     "approx_dimensions_m": {"w": number|null, "l": number|null},
     "dimensions_source": "printed" | "derived_from_area" | null,
     "windows": integer count visible on this room's walls,
     "doors": integer count,
     "existing_fixtures": ["items drawn in this room, e.g. double bed, sofa, kitchen counter"],
     "notes": "anything relevant, e.g. open-plan, en-suite, access via balcony"
   }
 ],
 "warnings": ["anything ambiguous or unreadable"]
}

Rules:
- Read printed area figures exactly as shown (e.g. "25.2 m²").
- Only set approx_dimensions_m from printed linear dimensions. If none are
  printed, estimate from the area and the drawn aspect ratio and set
  dimensions_source to "derived_from_area".
- A balcony or terrace is a room with type "balcony".
- Do not invent rooms that are not drawn. Return ONLY the JSON object.
"""


def _pdf_first_page_png(data, dpi=200):
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


def _largest_embedded_image(data, min_px=300):
    """A plan supplied as a PDF is often one embedded raster; prefer it."""
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    best = None
    for pno in range(len(doc)):
        for img in doc[pno].get_images(full=True):
            pix = fitz.Pixmap(doc, img[0])
            if pix.width < min_px or pix.height < min_px:
                continue
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if best is None or pix.width * pix.height > best[0]:
                best = (pix.width * pix.height, pix.tobytes("png"))
    return best[1] if best else None


def to_png(path_or_bytes, suffix=None):
    """Normalise any supported input to PNG bytes."""
    if isinstance(path_or_bytes, (str,)):
        from pathlib import Path
        p = Path(path_or_bytes)
        suffix = p.suffix.lower()
        data = p.read_bytes()
    else:
        data = path_or_bytes
        suffix = (suffix or "").lower()

    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported format {suffix!r}; expected {sorted(SUPPORTED)}")

    if suffix == ".pdf":
        return _largest_embedded_image(data) or _pdf_first_page_png(data)

    if suffix in (".jpg", ".jpeg"):
        from PIL import Image
        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buf, format="PNG")
        return buf.getvalue()

    return data


def _check_geometry(result, tolerance=0.35):
    """Cross-check each room's width x length against its stated area.

    A vision model can misread a dimension label (a 5.1m bedroom read as 9.0m)
    and the error is invisible downstream -- it silently becomes wrong furniture
    proportions in the render. Area is usually printed in large type and read
    reliably, so it is used as the check. Dimensions that disagree with it are
    rescaled to match the area, keeping the aspect ratio, and the correction is
    recorded rather than applied silently.
    """
    warnings = result.setdefault("warnings", [])
    for r in result.get("rooms") or []:
        area = r.get("area_m2")
        dm = r.get("approx_dimensions_m") or {}
        w, l = dm.get("w"), dm.get("l")
        if not area or not w or not l:
            continue
        implied = w * l
        if implied <= 0:
            continue
        drift = abs(implied - area) / area
        if drift <= tolerance:
            continue
        # keep the aspect ratio, scale both sides so w*l == area
        factor = (area / implied) ** 0.5
        dm["w"], dm["l"] = round(w * factor, 2), round(l * factor, 2)
        r["dimensions_source"] = "corrected_to_area"
        warnings.append(
            f"{r.get('id')}: printed dimensions {w}x{l}m imply {implied:.1f} m2 but "
            f"area reads {area} m2; rescaled to {dm['w']}x{dm['l']}m")
    return result


def analyze(path_or_bytes, suffix=None):
    """Return the structured layout for a floor plan."""
    png = to_png(path_or_bytes, suffix)
    result = claude(PROMPT, image_bytes=png)

    rooms = result.get("rooms") or []
    for i, r in enumerate(rooms, 1):
        r.setdefault("id", f"room-{i}")
    _check_geometry(result)
    # biggest habitable room is the default render target
    habitable = [r for r in rooms if r.get("type") != "balcony"]
    target = max(habitable or rooms, key=lambda r: r.get("area_m2") or 0, default=None)
    result["default_room_id"] = target["id"] if target else None
    return result


if __name__ == "__main__":
    import sys
    out = analyze(sys.argv[1])
    print(json.dumps(out, indent=1, ensure_ascii=False))
