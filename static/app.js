const $ = (id) => document.getElementById(id);
let layout = null;
let samplePlan = null;   // set when an example plan is chosen instead of an upload

const fill = (sel, values, labels) => {
  sel.innerHTML = "";
  values.forEach((v, i) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = labels ? labels[i] : v;
    sel.appendChild(o);
  });
};

const money = (n) =>
  n == null ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });

const esc = (s) => String(s ?? "").replace(/[<>&"]/g,
  (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));

// ---- boot -----------------------------------------------------------------
fetch("/api/options").then(r => r.json()).then(o => {
  fill($("style"), o.styles, o.styles.map(s => s[0].toUpperCase() + s.slice(1)));
  fill($("palette"), o.palettes);
  fill($("viewpoints"), Array.from({ length: o.max_viewpoints }, (_, i) => i + 1));
  $("viewpoints").value = Math.min(4, o.max_viewpoints);
  fill($("variations"), Array.from({ length: o.max_variations }, (_, i) => i + 1));
  $("variations").value = Math.min(2, o.max_variations);
  $("quality").value = o.default_quality;
  $("catmeta").textContent =
    `${o.catalog_size} catalog products · ${o.suppliers.join(" · ")}`;
});

// ---- plan selection -------------------------------------------------------
document.querySelectorAll(".sample").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".sample").forEach(b =>
      b.setAttribute("aria-pressed", String(b === btn)));
    samplePlan = btn.dataset.plan;
    $("file").value = "";           // an example and an upload are exclusive
    $("analysis").innerHTML = "";
  };
});

$("file").onchange = () => {
  if (!$("file").files.length) return;
  samplePlan = null;
  document.querySelectorAll(".sample").forEach(b =>
    b.setAttribute("aria-pressed", "false"));
};

/** The chosen plan as a File, whether uploaded or one of the examples. */
async function currentPlanFile() {
  if ($("file").files.length) return $("file").files[0];
  if (samplePlan) {
    const blob = await fetch(samplePlan).then(r => r.blob());
    return new File([blob], samplePlan.split("/").pop(), { type: blob.type });
  }
  return null;
}

// ---- analyse --------------------------------------------------------------
$("analyze").onclick = async () => {
  const f = await currentPlanFile();
  if (!f) {
    $("analysis").innerHTML =
      `<p class="err">Pick an example plan or upload your own first.</p>`;
    return;
  }

  $("analyze").disabled = true;
  $("analysis").textContent = "Reading the plan…";
  const fd = new FormData();
  fd.append("file", f);

  try {
    const res = await fetch("/api/analyze", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    layout = await res.json();

    const rooms = layout.rooms || [];
    $("analysis").innerHTML =
      `<div>Detected <b>${rooms.length}</b> rooms` +
      (layout.total_area_m2 ? ` · ${layout.total_area_m2} m² total` : "") + `</div>
       <div class="rooms">` +
      rooms.map(r => `<div class="room"><b>${esc(r.type)}</b>${esc(r.name)} · ${r.area_m2 ?? "?"} m²</div>`).join("") +
      `</div>` +
      (layout.warnings?.length
        ? `<p class="hint">${layout.warnings.map(w => "⚠ " + esc(w)).join("<br>")}</p>` : "");

    fill($("room"), rooms.map(r => r.id),
         rooms.map(r => `${r.name} — ${r.area_m2 ?? "?"} m²`));
    if (layout.default_room_id) $("room").value = layout.default_room_id;
    $("step2").hidden = false;
    $("step2").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) {
    $("analysis").innerHTML = `<p class="err">${esc(e.message)}</p>`;
  } finally {
    $("analyze").disabled = false;
  }
};

// ---- generate -------------------------------------------------------------
$("generate").onclick = async () => {
  const room = (layout?.rooms || []).find(r => r.id === $("room").value);
  if (!room) return;

  const views = +$("viewpoints").value, vars = +$("variations").value;
  const secs = ($("quality").value === "fast" ? 7 : 20) * views;
  $("generate").disabled = true;
  $("hint").textContent =
    `Planning ${vars} design${vars > 1 ? "s" : ""} and rendering ${views * vars} images, around ${secs}s…`;
  $("results").innerHTML = "";

  const fd = new FormData();
  fd.append("room_json", JSON.stringify(room));
  fd.append("style", $("style").value);
  fd.append("palette", $("palette").value);
  fd.append("viewpoints", views);
  fd.append("variations", vars);
  fd.append("quality", $("quality").value);

  const t0 = Date.now();
  try {
    const res = await fetch("/api/generate", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    $("results").innerHTML = data.variations.map((v, i) => card(v, i)).join("");
    wireRegen();
    $("hint").textContent =
      `Done in ${((Date.now() - t0) / 1000).toFixed(0)}s · ${data.image_model}`;
  } catch (e) {
    $("hint").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  } finally {
    $("generate").disabled = false;
  }
};

// ---- one design -----------------------------------------------------------
function card(v, i) {
  const rows = [
    ...v.products,
    ...v.finishes.map(f => ({
      name: f.name, supplier: "—", qty: 1, unit_price: f.unit_price,
      line_total: f.unit_price, url: f.url, catalog_id: f.catalog_id })),
  ];
  // renders are overwritten in place on regenerate, so bust the image cache
  const bust = Date.now();
  return `
  <div class="variation" id="var-${v.scene_id}">
    <h3>Design ${i + 1}</h3>
    <p class="sub">${esc(v.summary)}</p>
    <div class="shots">
      ${v.renders.map(r => `
        <figure class="shot">
          <img src="${r.url}?t=${bust}" alt="${esc(r.label)}" loading="lazy">
          <span>${esc(r.label)}${r.is_canonical ? " · reference view" : ""}</span>
        </figure>`).join("")}
    </div>
    <div class="tablewrap">
      <table>
        <thead><tr>
          <th>Product</th><th>Supplier</th><th class="num">Qty</th>
          <th class="num">Unit</th><th class="num">Total</th>
        </tr></thead>
        <tbody>
          ${rows.map(p => `
            <tr>
              <td>${p.url ? `<a href="${p.url}" target="_blank" rel="noopener">${esc(p.name)}</a>` : esc(p.name)}
                  <br><small>${esc(p.catalog_id)}</small></td>
              <td>${esc(p.supplier)}</td>
              <td class="num">${p.qty}</td>
              <td class="num">${money(p.unit_price)}</td>
              <td class="num">${money(p.line_total)}</td>
            </tr>`).join("")}
          <tr class="total">
            <td colspan="4">Estimated total</td>
            <td class="num">${money(v.estimated_total)} ${v.currency}</td>
          </tr>
        </tbody>
      </table>
    </div>
    ${v.styling_only?.length ? `<p class="styling">Styling only, not sold by either
      supplier and excluded from the total:
      ${v.styling_only.map(s => `<code>${esc(s.item)}</code>`).join(" ")}</p>` : ""}
    <div class="regen" data-scene="${v.scene_id}">
      <input type="text" placeholder="Change something, e.g. swap the armchair for a pouf">
      <button class="secondary regen-go">Regenerate</button>
      <button class="secondary regen-same">Re-render unchanged</button>
      <p class="note">Leave the box empty to re-render the identical scene. Any
        change is applied to the saved scene spec, so untouched items keep their
        product and position.</p>
    </div>
  </div>`;
}

// ---- regenerate -----------------------------------------------------------
function wireRegen() {
  document.querySelectorAll(".regen").forEach(box => {
    const sceneId = box.dataset.scene;
    const input = box.querySelector("input");

    const run = async (withChanges) => {
      box.querySelectorAll("button").forEach(b => (b.disabled = true));
      box.querySelector(".diff")?.remove();
      const note = box.querySelector(".note");
      note.textContent = "Re-rendering…";

      const fd = new FormData();
      fd.append("scene_id", sceneId);
      fd.append("viewpoints", $("viewpoints").value);
      fd.append("quality", $("quality").value);
      if (withChanges && input.value.trim()) fd.append("changes", input.value.trim());

      try {
        const res = await fetch("/api/regenerate", { method: "POST", body: fd });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const v = await res.json();

        const wrap = document.getElementById(`var-${sceneId}`);
        const idx = [...document.querySelectorAll(".variation")].indexOf(wrap);
        wrap.outerHTML = card(v, idx);
        wireRegen();

        const c = v.changes_applied;
        const fresh = document.querySelector(`.regen[data-scene="${sceneId}"]`);
        const p = document.createElement("p");
        p.className = "diff";
        p.innerHTML = c
          ? `Added <b>${c.added.length}</b> · removed <b>${c.removed.length}</b> ·
             moved <b>${c.moved.length}</b> · unchanged <b>${c.unchanged.length}</b>`
          : "Scene re-rendered unchanged.";
        fresh.appendChild(p);
      } catch (e) {
        note.innerHTML = `<span class="err">${esc(e.message)}</span>`;
        box.querySelectorAll("button").forEach(b => (b.disabled = false));
      }
    };

    box.querySelector(".regen-go").onclick = () => run(true);
    box.querySelector(".regen-same").onclick = () => run(false);
  });
}
