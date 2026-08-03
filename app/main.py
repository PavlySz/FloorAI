"""REST API + minimal web interface."""
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import analyzer, catalog, config, pipeline, planner, renderer

app = FastAPI(title="FloorAI",
              description="Floor plan to catalog-backed photorealistic renders",
              version="1.0")

STATIC = config.ROOT / "static"
# /renders is mounted separately so generated images keep stable public URLs
# even though they live inside the static directory.
app.mount("/renders", StaticFiles(directory=config.RENDERS_DIR), name="renders")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
# so the UI can offer the bundled floor plans as one-click examples
app.mount("/samples", StaticFiles(directory=config.SAMPLES_DIR), name="samples")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/options")
def options():
    """Everything the UI needs to build its form."""
    return {
        "styles": planner.STYLES,
        "palettes": list(planner.PALETTES),
        "viewpoints": [{"id": v["id"], "label": v["label"]}
                       for v in renderer.VIEWPOINTS],
        "quality_levels": list(config.IMAGE_MODELS),
        "default_quality": config.DEFAULT_IMAGE_QUALITY,
        "max_viewpoints": config.MAX_VIEWPOINTS,
        "max_variations": config.MAX_VARIATIONS,
        "suppliers": catalog.suppliers(),
        "catalog_size": len(catalog.load_catalogs()),
    }


@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in analyzer.SUPPORTED:
        raise HTTPException(400, f"unsupported format {suffix!r}; "
                                 f"expected {sorted(analyzer.SUPPORTED)}")
    try:
        return analyzer.analyze(await file.read(), suffix=suffix)
    except Exception as e:
        raise HTTPException(500, f"analysis failed: {e}") from e


@app.post("/api/generate")
async def api_generate(
    file: UploadFile = File(None),
    room_json: str = Form(None),
    room_id: str = Form(None),
    style: str = Form("scandinavian"),
    palette: str = Form("warm neutral"),
    viewpoints: int = Form(config.DEFAULT_VIEWPOINTS),
    variations: int = Form(config.DEFAULT_VARIATIONS),
    quality: str = Form(None),
):
    """Generate renders. Supply either a floor plan file or a room_json blob.

    Passing room_json back from /api/analyze avoids re-running the vision call
    when the user only changes style or palette.
    """
    import json as _json

    if room_json:
        room = _json.loads(room_json)
    elif file is not None:
        suffix = Path(file.filename or "").suffix.lower()
        layout = analyzer.analyze(await file.read(), suffix=suffix)
        rooms = layout.get("rooms") or []
        target = room_id or layout.get("default_room_id")
        room = next((r for r in rooms if r["id"] == target), rooms[0] if rooms else None)
        if room is None:
            raise HTTPException(422, "no rooms detected in that floor plan")
    else:
        raise HTTPException(400, "provide either a floor plan file or room_json")

    try:
        return pipeline.generate(room, style=style, palette=palette,
                                 viewpoints=viewpoints, variations=variations,
                                 quality=quality)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"generation failed: {e}") from e


@app.post("/api/regenerate")
async def api_regenerate(
    scene_id: str = Form(...),
    changes: str = Form(None),
    viewpoints: int = Form(config.DEFAULT_VIEWPOINTS),
    quality: str = Form(None),
):
    """Re-render a stored scene, optionally applying a change request."""
    try:
        return pipeline.regenerate(scene_id, changes=changes or None,
                                   viewpoints=viewpoints, quality=quality)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"regeneration failed: {e}") from e


@app.get("/api/scene/{scene_id}")
def api_scene(scene_id: str):
    try:
        return planner.load(scene_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/catalog/search")
def api_catalog_search(
    category: str = None, subcategory: str = None, style: str = None,
    color: str = None, material: str = None, supplier: str = None,
    min_price: float = None, max_price: float = None,
    min_width_cm: float = None, max_width_cm: float = None,
    q: str = None, limit: int = 50,
):
    """Search the merged catalog by any combination of attributes."""
    results = catalog.search(
        category=category, subcategory=subcategory, style=style, color=color,
        material=material, supplier=supplier, min_price=min_price,
        max_price=max_price, min_width_cm=min_width_cm,
        max_width_cm=max_width_cm, query=q, limit=limit)
    return {"count": len(results), "results": results}


@app.exception_handler(404)
def not_found(_request, exc):
    return JSONResponse({"error": str(exc.detail) if hasattr(exc, "detail")
                         else "not found"}, status_code=404)
