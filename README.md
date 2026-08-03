# FloorAI

Takes a floor plan (PNG/JPG/JPEG/PDF), detects its rooms, furnishes one of them
using only products from real supplier catalogs, and renders it photorealistically
from several camera positions. Returns the exact products, quantities and cost
behind every render.

---

## Architecture

```
floor plan ──▶ analyzer ──▶ planner ──▶ renderer ──▶ renders + product list
               agent        agent        agent
             (Claude      (Claude,   (Nano Banana Pro)
              vision)   catalog-bound)
                             │
                       scene_spec.json
```

**Analyzer agent.** One vision call turns the plan into structured rooms (type,
area, dimensions, doors, windows, fixtures). PDFs are rasterised first. No CV
model. A validator cross-checks each room's `w × l` against its printed area and
rescales on mismatch, because a misread dimension label otherwise becomes wrong
furniture proportions downstream.

**Planner agent.** Receives the room, style, palette and the catalog subset for
that room type. Returns a scene spec: every placement as
`{catalog_id, qty, position, facing}`, plus floor, wall and lighting finishes.
Ids that are not in the catalog are dropped at validation.

**Renderer agent.** Compiles the spec into a prompt with one pure function,
renders the canonical image, then renders each further viewpoint from that same
text plus the canonical image as reference.

The scene spec is saved to `scenes/{id}.json`, and three requirements come from
that one file:

| Requirement | How |
|---|---|
| Scene consistency | the prompt is compiled from the spec, so it is identical across views |
| Design variations | the planner runs *N* times at higher temperature, giving *N* different specs |
| Regeneration | reload a spec and re-render; a change request is applied as a diff, and the response reports added / removed / moved / unchanged |

Variations are different scenes. Viewpoints are the same scene. Keeping those
separate is what makes the consistency guarantees mean anything.

Both parallelisable stages are parallel: variations are independent of each
other, and within a scene every viewpoint depends only on the canonical image.
Rendering 4 viewpoints drops from about 2 minutes sequential to about 40 seconds.

---

## Findings

Measured on the real models before and during the build. Reproducible with
[`experiments/`](experiments/).

**1. Anchoring every view to the canonical image preserves object identity.**
Each viewpoint is generated from the canonical render, never from the previous
view, so there is no chain for drift to accumulate along.

**2. Telling the model "only the camera moves" does not move the camera.** It
re-emits the reference image with a slight crop. Consistency is perfect and the
output is useless. Fix: describe the target frame instead, meaning where the
camera stands, what is behind it and therefore not visible, and where each object
sits in frame.

**3. Turning the camera about 180° produces duplicate furniture.** The reference
image is the only spatial anchor, so a frame sharing no landmark with it makes
the model invent the missing half of the room. Viewpoints stay within roughly a
45 to 120° arc and always keep one shared landmark in frame.

**4. The two image models fail in opposite ways.** Same spec, same prompts.
Nano Banana is `gemini-2.5-flash-image`, Nano Banana Pro is `gemini-3-pro-image`:

| | Nano Banana | Nano Banana Pro |
|---|---|---|
| 4 views, parallel | 19 s | 42 s |
| Photorealism | flat, 1:1 | strong, 16:9 |
| Camera movement | about 15°, views nearly identical | a genuine 90° |
| Object identity | held, but duplicated a chair | drifted, a shelf became a sideboard |

Drift responds to prompting; refusing to move the camera does not. Nano Banana
Pro is the default and Nano Banana is selectable per request.

**5. Drift is fixed by ranking the image above the text.** Two additions removed
most of it: telling the model that where the photograph and the text disagree the
photograph wins, and listing the objects with exact quantities ("exactly 1 ×
Patek armchair"). Counts stop duplication, precedence stops substitution.

---

## Catalog

49 products scraped from the two suppliers named in the brief. No product, price
or URL is invented.

| | Gorgia | Comforter |
|---|---|---|
| Products | 26 | 23 |
| Name / price / URL | 26 | 23 |
| Dimensions | 22/22 physical | 21/23 |
| Colour | 17 | 23 |
| Material | 17 | 16 |
| Brand | 16 | n/a |

Gorgia covers the renovation side of the brief (laminate, vinyl, tile, paint,
doors, pendants, sconces, kitchen units), not just furniture.

Products are selected by **data completeness, not by category**. All 382 scraped
Gorgia candidates are scored on how complete their spec data is, and each
subcategory takes its best entries. A product with no usable dimensions is never
eligible.

Four things that would otherwise corrupt the data quietly:

1. **Gorgia's dimension fields are dirty.** Units are mixed (most rows are metres,
   some centimetres), its "length" is this schema's *width* rather than depth, and
   product names state sizes in a third unit again (`191X1200X12mm` is a
   19.1 × 120 × 1.2 cm plank). Values are normalised, range-checked per
   subcategory, and cross-checked against the name, which wins on conflict.
2. **A bare `NNxNN` search of Gorgia's HTML matches thumbnail sizes** in image
   URLs and produces 64 cm sofas. Sizes are read only from the spec table, the
   gallery image `alt`, or the product name.
3. **Wall colour is two SKUs, not an attribute.** Every interior wall paint Gorgia
   sells is white; the market tints a white base with a separate pigment (Kolorex,
   4.75 GEL, 112 of them). A chosen palette therefore resolves to a real
   purchasable pigment SKU rather than a colour word that only exists in the
   prompt.
4. **Comforter publishes no colour.** Their spec block is country, dimensions and
   a generic "Fabric". Colour is read from the product photograph instead and
   marked `color_source: "derived from product photograph"`.

Two Gorgia products keep `null` dimensions because the supplier's own data is
wrong (one sofa is published as 4 × 5 × 5 cm at 55 kg), with the reason recorded
in `rejected_features`. Every record carries `dimensions_source` and a
`derived_fields` list, so what was read and what was inferred are always
distinguishable. `style_tags` are always inferred, as no supplier publishes them.

**Rugs and curtains** are in the brief's consistency list but not its catalog
requirement, which asks for furniture or renovation elements "whenever possible".
Neither supplier stocks them, so rather than invent SKUs the scene spec splits
elements into catalog-linked (priced and listed) and styling-only (rug, curtains,
plants, artwork: fully specified so they stay fixed across views, never priced).

### Schema

```json
{
  "id": "GRG-015", "supplier": "Gorgia",
  "name": "Laminate flooring 191X1200X12mm ...",
  "name_original": "<verbatim Georgian name>",
  "category": "flooring", "subcategory": "laminate_floor",
  "style_tags": ["modern"], "color": null, "material": null,
  "dimensions_cm": {"w": 19.1, "d": 120, "h": 1.2},
  "dimensions_source": "191X1200X12მმ",
  "brand": "CAMSAN", "country_of_manufacture": "თურქეთი",
  "price": 39.5, "currency": "GEL",
  "url": "https://gorgia.ge/...", "image_url": "...",
  "source": "scraped", "derived_fields": ["style_tags"]
}
```

Adding a supplier is a file copy: drop a JSON file matching this schema into
`catalog/`. `load_catalogs()` merges every file in the directory, so there is no
registry to update and no code to change. Importers for both suppliers are in
[`scripts/`](scripts/).

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/options` | styles, palettes, viewpoints, quality levels, catalog size |
| `POST /api/analyze` | floor plan → detected rooms |
| `POST /api/generate` | plan or `room_json` + style, palette, viewpoints, variations, quality → renders, products, cost |
| `POST /api/regenerate` | `{scene_id, changes?}` → re-render, plus a change diff |
| `GET /api/scene/{id}` | the stored scene spec |
| `GET /api/catalog/search` | filter by category, subcategory, style, colour, material, supplier, price, width |

Interactive docs at `/docs`. The web interface is one static page: plain
HTML/CSS/JS, no framework, no build step. It covers analyse and generate;
regeneration is API only, so exercise it from `/docs` or curl.

Measured end to end: one `/api/generate` on the 25.2 m² open-plan room, Japandi
and earth palette, 4 viewpoints × 2 variations (8 images) on Nano Banana Pro took
91 seconds and produced two different designs at 16,487 and 8,458 GEL. Each chose
a different pigment, and the rendered wall colour followed it.

---

## Running it

```bash
pip install -r requirements.txt
cp keys.env.example keys.env      # ANTHROPIC_API_KEY, GOOGLE_API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Sample floor plans are in [`samples/`](samples/).

Deployment is a single EC2 instance behind a systemd unit, no Docker and no
managed services. See [`deploy/`](deploy/).

---

## Scope and known limits

**Only 4 of the 6 camera positions are used by default.** The renderer defines
six viewpoints ordered by how far each sits from the establishing shot, and a run
takes the first N. The "from the doorway" position is last, because the
establishing shot is usually taken from near the doorway anyway, so the two
frames overlap and the second render comes back looking like the first. Asking
for 6 viewpoints includes it.

**Bathroom and kitchen coverage is uneven.** Gorgia's bathroom range is scraped
but not curated into the catalog, so a bathroom render would contain fixtures
with no matching product. Kitchen units are included, so the open-plan demo room
is fully covered. Adding bathroom is one line in `WANT` in
`scripts/rebuild_gorgia.py`.

**Consistency is best effort, not guaranteed.** Findings 2, 3 and 5 above reduce
drift and duplication but do not eliminate them. Occasional defects remain, most
often a piece of furniture changing proportions between views.

Deliberately not built:

- **Vector or embedding catalog search.** 49 products fit in a prompt. Semantic
  retrieval only starts paying off at real catalog scale, in the thousands.
- **A database layer.** JSON files already satisfy "importable and indexable" and
  keep swapping a supplier down to copying a file.
- **CV verification of renders.** Detecting furniture in the output and asserting
  it matches the scene spec is the natural next step for automated QA, and would
  turn finding 5 from a prompt technique into a measurable check.
- **True 3D or NeRF multi-view synthesis.** The actual fix for the viewpoint arc
  limit in finding 3, and a different project.
