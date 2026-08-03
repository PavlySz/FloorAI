# Project Overview

A prototype system that takes a floor plan (image/PDF), uses an analyzer agent to read the layout into structured data, a planner agent to commit that layout to an explicit **scene spec** built only from catalog products, and a generator agent (Nano Banana) to produce photorealistic renders from multiple consistent viewpoints. Delivered as a FastAPI REST API with a minimal web interface, deployed directly on a single EC2 instance.

---

# Requirements (from the PDF, unchanged)

**Functional**
- Accept floor plans: PNG, JPG, JPEG, PDF
- Analyze layout, detect rooms
- Let user select style before generation
- Generate multiple photorealistic renders from different viewpoints
- Use only catalog products
- Return products used in every render
- REST API, CLI, or minimal web interface

**User Features**
- Choose style (Scandinavian, Nordic, Japanese, Japandi, Modern, Contemporary, Minimalist, Industrial, Classic, Luxury, Rustic, Bohemian, etc. — list given directly in the doc)
- Choose color palette
- Generate multiple design variations
- Regenerate while preserving scene unless changes requested

**Scene Consistency**
- Same scene, identical layout across camera positions
- Furniture/decor/lighting stay in same locations
- No objects moving/disappearing/rotating/resizing/changing identity between views
- Architecture unchanged, only camera moves
- Furniture proportions match floor plan
- No mismatched layouts, floating objects, duplicated/missing items

**Catalog**
- Import/index supplied catalogs (Gorgia, Comforter — no specific tech mandated)
- Covers furniture **and renovation materials**: flooring, paint, tile, lighting, bathroom, kitchen
- Search by category, dimensions, color, material, **style**, price
- Every visible furniture *or renovation* element maps to a real catalog product where possible
- Return product names/IDs **or URLs**, quantities, estimated total cost
- Support multiple suppliers, swappable catalogs with minimal changes

---

# Architecture

**Three-stage pipeline**

1. **Analyzer agent** (Claude, vision-capable) — floor plan image/PDF → structured JSON: room list with name, type, area, approximate dimensions, doors, windows, existing fixtures. One-shot structured output, no CV model. PDF pages rasterized to PNG first.

2. **Planner agent** (Claude) — analyzer JSON + target room + style + palette + the *filtered catalog subset* for that room type → an explicit **scene spec**: every placement as `{catalog_id, name, qty, position_description, facing}`, plus wall/floor/lighting finishes, all chosen from real catalog entries.

   Scene elements come in two classes. **Catalog-linked** elements (furniture, lighting, flooring, paint, doors, cushions) must carry a real catalog ID and are what the API returns and prices. **Styling-only** elements (`catalog_linked: false` — rug, curtains, plants, artwork) are fully specified in the prompt so they stay locked across viewpoints, but never enter the product list or the cost. Neither supplier stocks rugs or curtains, and the brief only requires catalog mapping for furniture/renovation elements "whenever possible" — so they are rendered and held consistent without fabricating SKUs.

3. **Generator agent** (Nano Banana / Gemini 2.5 Flash Image) — scene spec → deterministic master prompt → canonical render → additional viewpoints.

**The scene spec is the load-bearing artifact.** It is persisted to `scenes/{scene_id}.json` next to its renders, and it is what makes three separate requirements fall out of one mechanism:

- **Consistency** — the master prompt is built from the spec by a single pure function, so the text is byte-identical across every call for that scene.
- **Design variations** — run the planner N times at higher temperature on the same room/style. Each run yields a distinct scene spec, i.e. a genuinely different design, rendered independently. Variations are *different scenes*; viewpoints are *the same scene*. Keeping these separate is what stops the two requirements from being conflated.
- **Regeneration** — reload a stored spec and re-render it verbatim (scene preserved). If the user supplies a change request, apply it as a delta to the spec via one LLM call, diff it, and re-render only from the amended spec — so untouched items provably keep their catalog IDs and positions.

**Consistency mechanism (star topology, not chaining):** every additional viewpoint call sends the same master prompt text plus the **original canonical image** as reference (never a previously-generated image). Anchoring to the original avoids drift from chaining. Documented as best-effort, not a fully solved research problem.

**Two failure modes measured on `gemini-3-pro-image` before building** (smoke tests in `experiments/`), both of which shape the design:

1. *Instructing "only the camera moves" produces no camera movement at all.* The model re-emits the reference image with a slight crop — object identity is perfect but every "viewpoint" is the same shot, which fails the multiple-viewpoints requirement. **Fix:** the viewpoint prompt describes the **target frame**, not the transformation — where the camera stands, what it faces, what is *behind* the camera and therefore must not appear, and where each object sits in frame. This reliably produces genuinely different photographs.
2. *Near-180° reversals hallucinate duplicates.* A camera at the window looking back into the room duplicated the sofa and kept the window in frame. Rotations of ~45–120° and low close-up detail shots are reliable; frames sharing no landmark with the canonical image are not, because the reference is the only spatial anchor.

**Consequent rule:** the four demo viewpoints are constrained to a safe arc around the canonical camera, every view keeps at least one shared landmark in frame, and a full reverse angle is documented as unsupported rather than prompted around. Viewpoint definitions live in one config block so the arc is tunable.

**Room targeting:** the sample plans are multi-room (25.2 m² living/kitchen, 12.8 m² bedroom, 6.1 m² bath, balcony). `/generate` accepts an optional `room_id`; absent that, the largest room by area is used.

**Styles:** hardcoded enum from the list already given in the doc, each mapped to a short style descriptor for prompts, and each also used as a `style_tags` filter against the catalog.

---

# Tech Stack (MVP)

**API layer** — FastAPI
- `POST /analyze` — upload floor plan → rooms
- `POST /generate` — `{room_id, style, palette, viewpoints[], variations}` → `scene_id`(s), render URLs, products used, estimated total
- `POST /regenerate` — `{scene_id, changes?}` → same scene re-rendered, or spec-delta applied
- `GET /catalog/search` — the catalog filter exposed directly
- Static mount for `static/renders/`

**Web interface** — plain `index.html` + `style.css` + `app.js`. No framework, no Jinja, no Gradio. One page: file picker → style dropdown → palette picker → viewpoint checkboxes → variation count → Generate. Results render as an image grid plus a products table with running total. `fetch()` against the endpoints above.

**Floor plan analysis** — Claude vision → strict JSON schema output. `pymupdf` for PDF → PNG.

**Catalog layer (built first — everything downstream depends on the schema)**
- One schema across all suppliers: `id, supplier, name, category, subcategory, style_tags[], color, material, dimensions{w,d,h}, price, currency, url, image_url, source`
- `catalog/gorgia.json`, `catalog/comforter.json` — populated with real product names, prices and URLs sourced from the two named retailers wherever obtainable. Records that could not be sourced are marked `"source": "approximated"` and the split is stated plainly in the README. No silently invented SKUs.
- Categories span furniture **and renovation**: flooring, paint, wall tile, lighting fixtures, bathroom, kitchen — since those are the most visible surfaces in any render and the doc asks for them explicitly.
- `catalog.py`: `load_catalogs()` merges every JSON file in the dir; `search(category, style, color, material, price_max, dims)` filters in plain Python. Adding a supplier = dropping in one more file, no code change.
- 30–50 items per supplier is small enough to hand the filtered subset to the LLM as context. No DB, no vector index.

**Agent layer**
- Plain function-calling orchestration: analyze → filter catalog → plan scene → render → collect products used → sum estimated cost
- Two model providers (Claude for vision/analysis/planning, Gemini for image generation) to demonstrate multi-LLM proficiency

**Image generation** — canonical render + reference-conditioned viewpoint variants (star topology). Model chosen by measurement, not assumption: both `gemini-2.5-flash-image` (Nano Banana) and `gemini-3-pro-image` were smoke-tested on the same prompt. 3-pro is markedly more photorealistic and returns 16:9 (natural for interiors) at ~18s; 2.5-flash is flatter, square, ~6s. **3-pro is the default**, 2.5-flash stays configurable as a fast/cheap fallback — the model id is one setting. ComfyUI mentioned only in the writeup as a possible alternate local path, not built.

**Output** — JSON: renders (URLs), products used (id, name, url, qty, unit price, line total), style/palette applied, `scene_id` for regeneration.

**Deployment — simplest possible, single EC2 instance**
- Launch one EC2 instance (Ubuntu, t3.small or similar)
- SSH in, `git clone`, `pip install -r requirements.txt`
- Run with `uvicorn app:app --host 0.0.0.0 --port 8000`, kept alive via a basic systemd unit
- Open port 8000 in the instance's security group
- API keys as environment variables on the instance, not committed
- No Docker, no ECR, no App Runner, no RDS — one instance, one process

---

# Build Order

1. **Catalog** — schema, both supplier JSON files, `search()`. Do this first; it fixes the contract everything else codes against.
2. **Analyzer** — PDF/image ingest, vision call, rooms JSON. Test against the two floor plans extracted from the assessment PDF into `samples/`.
3. **Planner** — scene spec generation + persistence. The highest-value step; protect it if time runs short.
4. **Renderer** — master prompt builder, canonical render, viewpoint variants.
5. **API** — the five endpoints above.
6. **Web UI** — the single static page.
7. **README** — architecture, model choices and why, how consistency works and that it's best-effort, catalog data provenance, how to swap a supplier, run instructions, future work. Serves three graded criteria directly.
8. **Deploy** — EC2, once 1–7 run locally.

If time is tight, cut viewpoint count before cutting the planner — the scene spec is what makes consistency, variations and regeneration all work from one mechanism.

---

# Commands

Everything below is run from the repo root. Where it says Git Bash, that matters
on Windows: `C:\Windows\system32\bash.exe` is WSL and has a different filesystem
view, so use `C:\Program Files\Git\bin\bash.exe` (right-click the folder, "Git
Bash Here").

Live instance: **http://3.141.23.162** (EC2 `t3.small`, us-east-2, port 80)

## Local

```bash
pip install -r requirements.txt
cp keys.env.example keys.env          # then put the real keys in it
uvicorn app.main:app --port 8000      # http://localhost:8000

# run a single stage without the server
python -m app.analyzer samples/plan_1.png
```

## Testing

```bash
# five requests end to end, writes responses + images to api_outputs/
python api_client.py                        # local
python api_client.py http://3.141.23.162    # the deployment
```

## First deploy

Security group needs HTTP (port 80) open to anywhere, and SSH restricted to your
own IP. Then:

```bash
ssh -i <key>.pem ubuntu@3.141.23.162

# public repo
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/bootstrap.sh \
  | bash -s -- https://github.com/<you>/<repo>.git

# private repo: copy the source up first, then run bootstrap against it
# (from your machine)  bash deploy/push.sh 3.141.23.162 <key>.pem
# (on the server)      cd ~/floorai && bash deploy/bootstrap.sh
```

Bootstrap installs Python, builds the venv, writes the systemd unit and starts
the service. It grants `CAP_NET_BIND_SERVICE` so a non-root service can bind port
80. Override with `PORT=8000 bash deploy/bootstrap.sh`.

Then put the real keys on the box:

```bash
nano ~/floorai/keys.env
sudo systemctl restart floorai
```

## Updating a running deployment

Bootstrap is one-time. To ship a change, from Git Bash on your machine:

```bash
bash deploy/push.sh 3.141.23.162 <key>.pem
```

Uploads the source (about 900 KB), installs anything new from
`requirements.txt`, restarts the service and reports whether it came back up.
Uses tar over ssh rather than `scp -r`, which has no exclude support and no
delta. Skips `.git`, `.history`, `.claude`, the venv, `docs/`, `experiments/`,
`api_outputs/`, and the server's own `scenes/` and `static/renders/`.

Re-run `bootstrap.sh` only when the systemd unit or the port changes.

## On the server

```bash
systemctl status floorai
journalctl -u floorai -f              # live logs
journalctl -u floorai -n 50 --no-pager
sudo systemctl restart floorai
sudo systemctl stop floorai           # stop serving without terminating the box

curl -s localhost/api/options | head -c 200
```

## Rebuilding the catalog

Only needed if supplier data changes. Order matters: the scan feeds the rebuild.

```bash
cd scripts
python scrape_gorgia2.py        # furniture, lighting, flooring, tile, paint, doors
python scrape_gorgia3.py        # lighting fixtures and flooring subcategories
python scrape_gaps.py           # bathroom, kitchen, office, mattress, textile
python scrape_comforter.py      # all Comforter categories

python scan_complete.py         # score every candidate on data completeness
python rebuild_gorgia.py ../catalog/gorgia.json
python harvest_features.py ../catalog/gorgia.json
python append_paint.py          # wall paint base + tinting pigments
python append_kitchen.py        # kitchen units, sinks, dining sets
python colour_from_image.py ../catalog/comforter.json   # colour from product photos
```

Requires `ANTHROPIC_API_KEY` in the environment, since translation, attribute
extraction and colour reading all use it.

## Cost and lifecycle notes

- Every render a visitor triggers bills the keys on the instance. A 4 viewpoint,
  2 variation run is 8 image generations. Set `FLOORAI_IMAGE_QUALITY=fast` in the
  server's `keys.env` to make the default cheaper and quicker.
- Stopping the instance releases the auto-assigned public IP, which breaks the
  URL. Allocate an Elastic IP if the link needs to survive a stop/start. Reboot
  is safe.
- `scenes/` and `static/renders/` live only on the instance and are not in the
  repo.

Note: the Deployment bullets under Tech Stack above describe the original plan
(port 8000, manual clone). This section reflects what was actually built.

---

# Future Work (explicitly out of scope for MVP)
- Vector DB / embeddings-based semantic catalog search (only matters at real catalog scale)
- SQLite/pandas storage layer, formal adapter interface for non-JSON supplier sources
- Live scraped/API-fed catalog sync from Gorgia/Comforter instead of a snapshot
- ComfyUI local pipeline actually implemented
- CV-based object detection on generated renders to verify furniture placement against the scene spec
- True 3D/NeRF-based multi-view synthesis
- Containerization/orchestration (Docker, App Runner, ECS) if moving beyond single-instance demo scale
