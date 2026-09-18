/* app.js — connects the Leaflet dashboard to the M4 REST API.
   Pipeline this file consumes: SQLite -> REST API -> (this file) -> Leaflet map / table */

const API = "/api";

let map, segmentLayerGroup, defectLayerGroup;
let currentSegments = [];
let currentDefects = [];
let currentSurveyId = null;
let tableSort = { key: "type", dir: 1 };

const CONDITION_COLOR = { Good: "#2ecc71", Moderate: "#f1c40f", Severe: "#e74c3c" };
const DEFECT_ICON = { pothole: "🕳️", crack: "⚡", raveling: "🪨", patch: "🩹", other: "⚠️" };

document.addEventListener("DOMContentLoaded", init);

async function init() {
  initTheme();
  initMap();
  initMobileNav();
  initViewTabs();
  initTableControls();

  await checkHealth();
  await loadSurveyList();
  hideBootOverlay();

  document.getElementById("surveySelect").addEventListener("change", (e) => {
    if (e.target.value) loadSurvey(parseInt(e.target.value));
  });

  document.getElementById("replayBtn").addEventListener("click", runReplay);
  document.getElementById("emptyStateReplayBtn").addEventListener("click", runReplay);

  document.querySelectorAll(".filter-type, .filter-severity").forEach((el) =>
    el.addEventListener("change", applyFilters)
  );
  document.getElementById("thermalOnlyToggle").addEventListener("change", applyFilters);
  document.getElementById("resetFiltersBtn").addEventListener("click", resetFilters);
}

/* ---------------------------------------------------------------------- */
/* Boot / theme                                                            */
/* ---------------------------------------------------------------------- */
function hideBootOverlay() {
  const overlay = document.getElementById("bootOverlay");
  overlay.classList.add("hidden");
  setTimeout(() => overlay.remove(), 350);
}

function initTheme() {
  const saved = localStorage.getItem("m4-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  syncThemeIcon(saved);

  document.getElementById("themeToggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("m4-theme", next);
    syncThemeIcon(next);
  });
}

function syncThemeIcon(theme) {
  document.getElementById("themeIconMoon").style.display = theme === "dark" ? "block" : "none";
  document.getElementById("themeIconSun").style.display = theme === "light" ? "block" : "none";
}

/* ---------------------------------------------------------------------- */
/* Toasts                                                                   */
/* ---------------------------------------------------------------------- */
function toast(message, type = "info", timeout = 3500) {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity .25s ease";
    setTimeout(() => el.remove(), 250);
  }, timeout);
}

/* ---------------------------------------------------------------------- */
/* Mobile nav (sidebar / detail panel as slide-overs)                      */
/* ---------------------------------------------------------------------- */
function initMobileNav() {
  const sidebar = document.getElementById("sidebar");
  const scrim = document.getElementById("mobileScrim");

  document.getElementById("menuToggle").addEventListener("click", () => {
    sidebar.classList.add("open");
    scrim.classList.add("show");
  });

  scrim.addEventListener("click", closeMobilePanels);

  document.querySelectorAll("[data-close]").forEach((btn) =>
    btn.addEventListener("click", () => closeMobilePanels())
  );
}

function closeMobilePanels() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("detailPanel").classList.remove("open");
  document.getElementById("mobileScrim").classList.remove("show");
}

function openDetailPanelOnMobile() {
  if (window.innerWidth <= 980) {
    document.getElementById("detailPanel").classList.add("open");
    document.getElementById("mobileScrim").classList.add("show");
  }
}

/* ---------------------------------------------------------------------- */
/* View tabs (Map / Table)                                                 */
/* ---------------------------------------------------------------------- */
function initViewTabs() {
  document.querySelectorAll(".view-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".view-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const view = tab.dataset.view;
      document.getElementById("mapView").hidden = view !== "map";
      document.getElementById("tableView").hidden = view !== "table";
      if (view === "map") setTimeout(() => map.invalidateSize(), 50);
      if (view === "table") renderTable();
    });
  });
}

/* ---------------------------------------------------------------------- */
/* Map                                                                      */
/* ---------------------------------------------------------------------- */
function initMap() {
  map = L.map("map", { zoomControl: true }).setView([14.4753, 78.8298], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);
  segmentLayerGroup = L.layerGroup().addTo(map);
  defectLayerGroup = L.layerGroup().addTo(map);
}

/* ---------------------------------------------------------------------- */
/* Health / survey list                                                    */
/* ---------------------------------------------------------------------- */
async function checkHealth() {
  const pill = document.getElementById("serverStatus");
  try {
    const r = await fetch(`${API}/health`);
    const data = await r.json();
    if (r.ok && data.status === "ok") {
      pill.textContent = "server online";
      pill.className = "status-pill status-ok";
    } else {
      throw new Error("bad health response");
    }
  } catch (e) {
    pill.textContent = "server offline";
    pill.className = "status-pill status-error";
    toast("Could not reach the M4 server.", "error");
  }
}

async function loadSurveyList() {
  const select = document.getElementById("surveySelect");
  try {
    const r = await fetch(`${API}/surveys`);
    const surveys = await r.json();

    if (!surveys.length) {
      select.innerHTML = `<option value="">No surveys yet</option>`;
      showEmptyState(true);
      return;
    }

    showEmptyState(false);
    select.innerHTML = surveys
      .map(
        (s) =>
          `<option value="${s.id}">${s.survey_name || s.survey_uid} (avg PDI ${
            s.avg_pdi ?? "–"
          })</option>`
      )
      .join("");

    loadSurvey(surveys[surveys.length - 1].id);
  } catch (e) {
    select.innerHTML = `<option value="">Could not load surveys</option>`;
    toast("Failed to load survey list.", "error");
  }
}

function showEmptyState(show) {
  document.getElementById("emptyState").hidden = !show;
}

/* ---------------------------------------------------------------------- */
/* Load one survey                                                          */
/* ---------------------------------------------------------------------- */
async function loadSurvey(surveyId) {
  currentSurveyId = surveyId;
  document.getElementById("surveySelect").value = surveyId;
  document.getElementById("mapLoading").hidden = false;

  try {
    const [surveyRes, segmentsRes, defectsRes] = await Promise.all([
      fetch(`${API}/surveys/${surveyId}`),
      fetch(`${API}/surveys/${surveyId}/segments`),
      fetch(`${API}/surveys/${surveyId}/defects`),
    ]);

    const survey = await surveyRes.json();
    currentSegments = await segmentsRes.json();
    currentDefects = await defectsRes.json();

    showEmptyState(false);
    renderSurveyInfo(survey);
    renderSummary(survey);
    renderMap(currentSegments, currentDefects);
    renderTable();
    document.getElementById("lastUpdated").textContent =
      "Updated " + new Date().toLocaleTimeString();
  } catch (e) {
    toast("Failed to load survey data.", "error");
  } finally {
    document.getElementById("mapLoading").hidden = true;
  }
}

function renderSurveyInfo(survey) {
  const el = document.getElementById("surveyInfo");
  const rows = [
    ["Survey ID", survey.survey_uid],
    ["Date", survey.survey_date || "–"],
    ["Drone", survey.drone_id || "–"],
    ["GSD", survey.gsd_cm_per_px ? `${survey.gsd_cm_per_px} cm/px` : "–"],
    ["Area covered", survey.area_covered_sqm ? `${survey.area_covered_sqm} m²` : "–"],
  ];
  el.innerHTML = rows
    .map(([k, v]) => `<div class="kv-row"><span class="k">${k}</span><span>${v}</span></div>`)
    .join("");
}

function renderSummary(survey) {
  document.getElementById("statAvgPdi").textContent = survey.avg_pdi ?? "–";

  const potholes = survey.defect_type_breakdown.find((d) => d.type === "pothole");
  const cracks = survey.defect_type_breakdown.find((d) => d.type === "crack");
  document.getElementById("statPotholes").textContent = potholes ? potholes.count : 0;
  document.getElementById("statCracks").textContent = cracks ? cracks.count : 0;
  document.getElementById("statThermal").textContent = survey.thermal_anomaly_count ?? 0;

  const total = survey.condition_breakdown.reduce((sum, c) => sum + c.count, 0) || 1;
  const order = ["Good", "Moderate", "Severe"];
  const byCond = {};
  survey.condition_breakdown.forEach((c) => (byCond[c.condition] = c.count));

  document.getElementById("conditionBreakdown").innerHTML = order
    .map((cond) => {
      const count = byCond[cond] || 0;
      const pct = Math.round((count / total) * 100);
      return `
        <div class="cond-bar-row">
          <span style="width:64px">${cond}</span>
          <div class="cond-bar-track"><div class="cond-bar-fill ${cond}" style="width:${pct}%"></div></div>
          <span>${count}</span>
        </div>`;
    })
    .join("");
}

/* ---------------------------------------------------------------------- */
/* Map rendering                                                            */
/* ---------------------------------------------------------------------- */
function renderMap(segments, defects) {
  segmentLayerGroup.clearLayers();
  defectLayerGroup.clearLayers();

  const bounds = [];

  segments.forEach((seg) => {
    const color = CONDITION_COLOR[seg.condition] || "#888";
    const line = L.polyline(
      [
        [seg.start_lat, seg.start_lon],
        [seg.end_lat, seg.end_lon],
      ],
      { color, weight: 6, opacity: 0.85 }
    );

    line.bindPopup(popupForSegment(seg));
    line.on("click", () => showSegmentDetail(seg));
    line.addTo(segmentLayerGroup);

    bounds.push([seg.start_lat, seg.start_lon], [seg.end_lat, seg.end_lon]);
  });

  defects.forEach((d) => addDefectMarker(d));

  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40] });
}

function addDefectMarker(d) {
  const icon = L.divIcon({
    className: "defect-div-icon",
    html: `<div style="font-size:18px;line-height:18px;filter:drop-shadow(0 0 2px #000)">${
      DEFECT_ICON[d.type] || "⚠️"
    }</div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
  const marker = L.marker([d.lat, d.lon], { icon });
  marker.bindPopup(popupForDefect(d));
  marker.on("click", () => showDefectDetail(d));
  marker.addTo(defectLayerGroup);
}

function popupForSegment(seg) {
  return `
    <div class="popup-title">Segment ${seg.segment_uid}</div>
    <div class="popup-row"><span class="k">PDI</span><span>${seg.pdi}</span></div>
    <div class="popup-row"><span class="k">Condition</span><span>${seg.condition}</span></div>
    <div class="popup-row"><span class="k">Length</span><span>${seg.length_m ?? "–"} m</span></div>
    <div class="popup-row"><span class="k">Thermal score</span><span>${seg.thermal_score ?? "–"}</span></div>
  `;
}

function popupForDefect(d) {
  return `
    <div class="popup-title">${DEFECT_ICON[d.type] || ""} ${d.type}</div>
    <div class="popup-row"><span class="k">Severity</span><span>${d.severity ?? "–"}</span></div>
    <div class="popup-row"><span class="k">Area</span><span>${d.area_sqcm ?? "–"} cm²</span></div>
    <div class="popup-row"><span class="k">Depth</span><span>${d.depth_cm ?? "–"} cm</span></div>
    <div class="popup-row"><span class="k">Thermal</span><span>${d.thermal_anomaly ? "Yes" : "No"}</span></div>
    <div class="popup-row"><span class="k">Confidence</span><span>${d.confidence ?? "–"}</span></div>
  `;
}

/* ---------------------------------------------------------------------- */
/* Detail panel                                                             */
/* ---------------------------------------------------------------------- */
function showSegmentDetail(seg) {
  document.getElementById("detailContent").innerHTML = `
    <div class="detail-block">
      <h3>Road Segment ${seg.segment_uid}</h3>
      <p><span class="badge ${seg.condition}">${seg.condition}</span></p>
      <div class="kv-list">
        <div class="kv-row"><span class="k">PDI</span><span>${seg.pdi}</span></div>
        <div class="kv-row"><span class="k">Length</span><span>${seg.length_m ?? "–"} m</span></div>
        <div class="kv-row"><span class="k">Thermal score</span><span>${seg.thermal_score ?? "–"}</span></div>
        <div class="kv-row"><span class="k">Start</span><span>${seg.start_lat.toFixed(5)}, ${seg.start_lon.toFixed(5)}</span></div>
        <div class="kv-row"><span class="k">End</span><span>${seg.end_lat.toFixed(5)}, ${seg.end_lon.toFixed(5)}</span></div>
      </div>
    </div>
  `;
  openDetailPanelOnMobile();
}

function showDefectDetail(d) {
  document.getElementById("detailContent").innerHTML = `
    <div class="detail-block">
      <h3>${DEFECT_ICON[d.type] || ""} ${d.type} (#${d.defect_uid || d.id})</h3>
      <p><span class="badge ${d.severity || ""}">${d.severity || "unknown"}</span></p>
      <div class="kv-list">
        <div class="kv-row"><span class="k">Area</span><span>${d.area_sqcm ?? "–"} cm²</span></div>
        <div class="kv-row"><span class="k">Depth</span><span>${d.depth_cm ?? "–"} cm</span></div>
        <div class="kv-row"><span class="k">Thermal anomaly</span><span>${d.thermal_anomaly ? "Yes" : "No"}</span></div>
        <div class="kv-row"><span class="k">Confidence</span><span>${d.confidence ?? "–"}</span></div>
        <div class="kv-row"><span class="k">Location</span><span>${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}</span></div>
      </div>
    </div>
  `;
  openDetailPanelOnMobile();
}

/* ---------------------------------------------------------------------- */
/* Filters                                                                  */
/* ---------------------------------------------------------------------- */
function getFilteredDefects() {
  const activeTypes = [...document.querySelectorAll(".filter-type:checked")].map((c) => c.value);
  const activeSeverities = [...document.querySelectorAll(".filter-severity:checked")].map((c) => c.value);
  const thermalOnly = document.getElementById("thermalOnlyToggle").checked;

  return currentDefects
    .filter((d) => activeTypes.includes(d.type))
    .filter((d) => !d.severity || activeSeverities.includes(d.severity))
    .filter((d) => !thermalOnly || d.thermal_anomaly);
}

function applyFilters() {
  defectLayerGroup.clearLayers();
  getFilteredDefects().forEach((d) => addDefectMarker(d));
  renderTable();
}

function resetFilters() {
  document.querySelectorAll(".filter-type, .filter-severity").forEach((c) => (c.checked = true));
  document.getElementById("thermalOnlyToggle").checked = false;
  document.getElementById("defectSearch").value = "";
  applyFilters();
  toast("Filters reset", "info", 1500);
}

/* ---------------------------------------------------------------------- */
/* Table view                                                               */
/* ---------------------------------------------------------------------- */
function initTableControls() {
  document.getElementById("defectSearch").addEventListener("input", renderTable);
  document.querySelectorAll("#defectTable thead th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (tableSort.key === key) tableSort.dir *= -1;
      else tableSort = { key, dir: 1 };
      renderTable();
    });
  });
}

function renderTable() {
  const tbody = document.getElementById("defectTableBody");
  const search = (document.getElementById("defectSearch").value || "").toLowerCase();

  let rows = getFilteredDefects();

  if (search) {
    rows = rows.filter((d) =>
      [d.type, d.severity, String(d.segment_id)].join(" ").toLowerCase().includes(search)
    );
  }

  rows.sort((a, b) => {
    const av = a[tableSort.key], bv = b[tableSort.key];
    if (av === bv) return 0;
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return av > bv ? tableSort.dir : -tableSort.dir;
  });

  document.getElementById("tableCount").textContent = `${rows.length} defect${rows.length === 1 ? "" : "s"}`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center;padding:24px;">No defects match the current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map(
      (d) => `
      <tr data-defect-id="${d.id}">
        <td>${DEFECT_ICON[d.type] || ""} ${d.type}</td>
        <td><span class="badge ${d.severity || ""}">${d.severity || "–"}</span></td>
        <td>${d.segment_id ?? "–"}</td>
        <td>${d.area_sqcm ?? "–"}</td>
        <td>${d.depth_cm ?? "–"}</td>
        <td><span class="${d.thermal_anomaly ? "badge badge-yes" : "badge badge-no"}">${d.thermal_anomaly ? "Yes" : "No"}</span></td>
        <td>${d.confidence ?? "–"}</td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const id = parseInt(tr.dataset.defectId);
      const d = currentDefects.find((x) => x.id === id);
      if (d) {
        showDefectDetail(d);
        // Also switch to map + pan to it for context
        document.querySelector('.view-tab[data-view="map"]').click();
        map.setView([d.lat, d.lon], 17);
      }
    });
  });
}

/* ---------------------------------------------------------------------- */
/* Replay / demo                                                            */
/* ---------------------------------------------------------------------- */
async function runReplay() {
  const btns = [document.getElementById("replayBtn"), document.getElementById("emptyStateReplayBtn")];
  btns.forEach((b) => { if (b) { b.disabled = true; } });

  try {
    const samplesRes = await fetch(`${API}/samples`);
    const samples = await samplesRes.json();

    if (!samples.length) {
      toast("No sample survey files found on the server.", "error");
      return;
    }

    for (const filename of samples) {
      await fetch(`${API}/replay/${filename}`, { method: "POST" });
    }
    toast(`Replayed ${samples.length} sample survey(s) successfully.`, "success");
    await loadSurveyList();
  } catch (e) {
    toast("Replay failed. Is the server running?", "error");
  } finally {
    btns.forEach((b) => { if (b) { b.disabled = false; } });
  }
}
