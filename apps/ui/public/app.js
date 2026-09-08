const state = { budgets: [], selected: null, lastFlightId: null, groundStop: false, busy: false };

async function api(path, options = {}) {
  const opts = { ...options };
  opts.headers = { ...(options.headers || {}) };
  if (opts.body && !opts.headers["Content-Type"]) {
    opts.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function money(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "-";
  return "$" + Number(n).toFixed(2);
}

function say(msg, isError = false) {
  const el = document.getElementById("statusMsg");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
  el.classList.toggle("ok", !isError);
}

function setBusy(on, label) {
  state.busy = on;
  if (on && label) say(label + "…");
}

function needTank() {
  if (!state.selected) {
    say("Pick a fuel tank first.", true);
    return false;
  }
  return true;
}

async function refreshHealth() {
  const chip = document.getElementById("healthChip");
  try {
    const h = await api("/health");
    chip.textContent = h.floci ? "Floci · local" : "env: " + h.env;
    chip.className = "chip ok";
  } catch {
    chip.textContent = "API down";
    chip.className = "chip muted";
  }
}

function fillTankSelect() {
  const sel = document.getElementById("tankSelect");
  const current = state.selected;
  sel.innerHTML = "";

  if (!state.budgets.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No tanks yet — create one below";
    sel.appendChild(opt);
    return;
  }

  const sorted = [...state.budgets].sort((a, b) =>
    String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))
  );
  const shown = sorted.slice(0, 40);
  for (const b of shown) {
    const opt = document.createElement("option");
    opt.value = b.budget_id;
    opt.textContent = b.name + " · " + money(b.limit_usd);
    sel.appendChild(opt);
  }

  if (current && shown.some((b) => b.budget_id === current)) {
    sel.value = current;
  } else {
    state.selected = shown[0].budget_id;
    sel.value = state.selected;
  }
}

function renderForecast(payload) {
  const f = payload.forecast || payload;
  const check = payload.budget_check || {};
  const budget = payload.budget || {};
  const p50 = Number(f.p50_spend_usd || 0);
  const p90 = Number(f.p90_spend_usd || 0);
  const series = Array.isArray(f.series) ? f.series : [];
  const remaining = Number(check.remaining_before_forecast_usd ?? budget.limit_usd ?? 0);
  const dailyBurn = Number(f.daily_burn_usd || 0);

  const fitLabel =
    check.fits_p90 === true ? "Yes (p90)" : check.fits_p50 === true ? "Tight (p50 only)" : check.fits_p50 === false ? "Over budget" : "-";

  document.getElementById("fP50").textContent = money(p50);
  document.getElementById("fP90").textContent = money(p90);
  document.getElementById("fFit").textContent = fitLabel;

  document.getElementById("forecastSummary").textContent =
    f.note ||
    "Next 30 days ≈ " + money(p50) + " (p50) / " + money(p90) + " (p90).";

  const legend = document.getElementById("forecastLegend");
  const hoverEl = document.getElementById("forecastHover");
  const box = document.getElementById("forecastSpark");

  if (!series.length) {
    legend.hidden = true;
    legend.innerHTML = "";
    hoverEl.textContent = "";
    box.innerHTML = "<p class='hint soft'>No series yet — log a few usage events.</p>";
    return;
  }

  const p50vals = series.map((d) => Number(d.p50_spend_usd || 0));
  const p90vals = series.map((d) => Number(d.p90_spend_usd || 0));
  const seriesMax = Math.max(...p90vals, ...p50vals, 0.0001);
  // Only pull the fuel line into the scale when it's near the forecast
  // (otherwise a fat tank flattens the curves to a flat line at the bottom).
  const showFuelOnChart = remaining > 0 && remaining <= seriesMax * 1.35;
  const maxY = showFuelOnChart ? Math.max(seriesMax, remaining) : seriesMax;
  const endDay = series[series.length - 1].day || "";
  const startDay = series[0].day || "";

  legend.hidden = false;
  legend.innerHTML =
    '<span class="leg leg-p50"><i></i>p50 expected <b>' +
    money(p50) +
    "</b></span>" +
    '<span class="leg leg-p90"><i></i>p90 high <b>' +
    money(p90) +
    "</b></span>" +
    '<span class="leg leg-fuel"><i></i>usable now <b>' +
    money(remaining) +
    "</b>" +
    (showFuelOnChart ? "" : " <em>(above chart)</em>") +
    "</span>" +
    '<span class="leg leg-rate">burn <b>' +
    money(dailyBurn) +
    "/day</b></span>" +
    '<span class="leg leg-fit" data-fit="' +
    (check.fits_p90 ? "ok" : check.fits_p50 ? "warn" : "bad") +
    '">' +
    fitLabel +
    "</span>";

  hoverEl.textContent = startDay + " → " + endDay + " · hover a day for detail";

  const W = 320;
  const H = 110;
  const padL = 2;
  const padR = 2;
  const padT = 8;
  const padB = 18;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const n = series.length;
  const xAt = (i) => padL + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const yAt = (v) => padT + innerH - (v / maxY) * innerH;

  function linePath(vals) {
    return vals
      .map((v, i) => (i === 0 ? "M" : "L") + xAt(i).toFixed(1) + " " + yAt(v).toFixed(1))
      .join(" ");
  }

  function areaPath(vals) {
    if (!vals.length) return "";
    const top = linePath(vals);
    return (
      top +
      " L" +
      xAt(n - 1).toFixed(1) +
      " " +
      (padT + innerH).toFixed(1) +
      " L" +
      xAt(0).toFixed(1) +
      " " +
      (padT + innerH).toFixed(1) +
      " Z"
    );
  }

  const fuelY = yAt(remaining);
  const tickIdx = [0, Math.floor((n - 1) / 2), n - 1].filter((v, i, a) => a.indexOf(v) === i);
  const ticks = tickIdx
    .map((i) => {
      const label = (series[i].day || "").slice(5);
      return (
        '<text class="axis-label" x="' +
        xAt(i).toFixed(1) +
        '" y="' +
        (H - 4) +
        '" text-anchor="' +
        (i === 0 ? "start" : i === n - 1 ? "end" : "middle") +
        '">' +
        label +
        "</text>"
      );
    })
    .join("");

  const hitPads = series
    .map((d, i) => {
      const x = xAt(i);
      const step = n <= 1 ? innerW : innerW / (n - 1);
      return (
        '<rect class="hit" data-i="' +
        i +
        '" x="' +
        (x - step / 2).toFixed(1) +
        '" y="' +
        padT +
        '" width="' +
        Math.max(step, 4).toFixed(1) +
        '" height="' +
        innerH +
        '" />'
      );
    })
    .join("");

  box.innerHTML =
    '<svg class="forecast-svg" viewBox="0 0 ' +
    W +
    " " +
    H +
    '" preserveAspectRatio="none" role="img" aria-label="30 day cumulative spend forecast">' +
    '<path class="area-p90" d="' +
    areaPath(p90vals) +
    '" />' +
    '<path class="area-p50" d="' +
    areaPath(p50vals) +
    '" />' +
    '<path class="line-p90" d="' +
    linePath(p90vals) +
    '" />' +
    '<path class="line-p50" d="' +
    linePath(p50vals) +
    '" />' +
    (showFuelOnChart
      ? '<line class="fuel-line" x1="' +
        padL +
        '" x2="' +
        (W - padR) +
        '" y1="' +
        fuelY.toFixed(1) +
        '" y2="' +
        fuelY.toFixed(1) +
        '" />'
      : "") +
    '<line class="cursor-line" x1="0" x2="0" y1="' +
    padT +
    '" y2="' +
    (padT + innerH) +
    '" visibility="hidden" />' +
    '<circle class="dot-p50" r="3.2" visibility="hidden" />' +
    '<circle class="dot-p90" r="3.2" visibility="hidden" />' +
    ticks +
    hitPads +
    "</svg>";

  const svg = box.querySelector("svg");
  const cursor = svg.querySelector(".cursor-line");
  const dot50 = svg.querySelector(".dot-p50");
  const dot90 = svg.querySelector(".dot-p90");

  function showDay(i) {
    const d = series[i];
    const v50 = p50vals[i];
    const v90 = p90vals[i];
    const x = xAt(i);
    cursor.setAttribute("x1", x.toFixed(1));
    cursor.setAttribute("x2", x.toFixed(1));
    cursor.setAttribute("visibility", "visible");
    dot50.setAttribute("cx", x.toFixed(1));
    dot50.setAttribute("cy", yAt(v50).toFixed(1));
    dot50.setAttribute("visibility", "visible");
    dot90.setAttribute("cx", x.toFixed(1));
    dot90.setAttribute("cy", yAt(v90).toFixed(1));
    dot90.setAttribute("visibility", "visible");
    hoverEl.textContent =
      d.day +
      " · p50 " +
      money(v50) +
      " · p90 " +
      money(v90) +
      (remaining > 0 ? " · fuel left now " + money(remaining) : "");
  }

  function clearDay() {
    cursor.setAttribute("visibility", "hidden");
    dot50.setAttribute("visibility", "hidden");
    dot90.setAttribute("visibility", "hidden");
    hoverEl.textContent = startDay + " → " + endDay + " · hover a day for detail";
  }

  svg.querySelectorAll(".hit").forEach((el) => {
    el.addEventListener("mouseenter", () => showDay(Number(el.dataset.i)));
    el.addEventListener("focus", () => showDay(Number(el.dataset.i)));
  });
  svg.addEventListener("mouseleave", clearDay);

  // Animate redraw when data changes
  box.classList.remove("chart-pop");
  void box.offsetWidth;
  box.classList.add("chart-pop");
}

async function loadForecast(id) {
  const params = new URLSearchParams({ days: "30" });
  if (state.lastFlightId) params.set("flight_id", state.lastFlightId);
  const data = await api("/v1/budgets/" + id + "/forecast?" + params);
  renderForecast(data);
  return data;
}

async function loadBudgets() {
  const data = await api("/v1/budgets");
  state.budgets = data.budgets || [];
  fillTankSelect();
  if (state.selected) await loadRunway(state.selected);
}

async function selectBudget(id) {
  state.selected = id || null;
  state.lastFlightId = null;
  if (id) {
    document.getElementById("tankSelect").value = id;
    await loadRunway(id);
  }
}

async function loadRunway(id) {
  const data = await api("/v1/budgets/" + id + "/runway");
  const r = data.runway;
  document.getElementById("runwayEmpty").classList.add("hidden");
  document.getElementById("runwayCard").classList.remove("hidden");

  const days = r.days_remaining;
  document.getElementById("daysLeft").textContent = days === null ? "∞" : days;
  document.getElementById("daysLabel").textContent =
    days === null
      ? "log usage to estimate days left at this burn rate"
      : "days of usable fuel left at this burn rate";
  const pill = document.getElementById("statusPill");
  pill.textContent = r.status;
  pill.dataset.status = r.status;
  document.getElementById("runwayNote").textContent = r.note || "";
  document.getElementById("mLimit").textContent = money(r.limit_usd);
  document.getElementById("mSpent").textContent = money(r.spent_usd);
  document.getElementById("mRemain").textContent = money(r.remaining_usd);
  document.getElementById("mBurn").textContent =
    r.daily_burn_usd == null ? "-" : money(r.daily_burn_usd) + "/day";

  // Keep forecast in sync so the sticky panel always tells the story
  try {
    await loadForecast(id);
  } catch (err) {
    document.getElementById("forecastSummary").textContent = String(err.message || err);
  }

  // Pulse so changes are obvious while clicking logs
  const dock = document.querySelector(".runway-dock");
  if (dock) {
    dock.classList.remove("pulse");
    void dock.offsetWidth;
    dock.classList.add("pulse");
  }
}

document.getElementById("tankSelect").addEventListener("change", async (e) => {
  try {
    setBusy(true, "Loading runway");
    await selectBudget(e.target.value || null);
    say("Selected tank loaded.");
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("newTankBtn").addEventListener("click", async () => {
  const name = document.getElementById("newTankName").value.trim() || "Demo tank";
  const limit_usd = Number(document.getElementById("newTankLimit").value);
  if (!(limit_usd > 0)) {
    say("Enter a positive limit.", true);
    return;
  }
  try {
    setBusy(true, "Creating tank");
    const created = await api("/v1/budgets", {
      method: "POST",
      body: JSON.stringify({ name, limit_usd }),
    });
    state.selected = created.budget_id;
    await loadBudgets();
    say("Created tank: " + created.name + " (" + money(created.limit_usd) + ")");
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("usageBtn").addEventListener("click", async () => {
  if (!needTank()) return;
  try {
    setBusy(true, "Logging usage");
    const result = await api("/v1/usage", {
      method: "POST",
      body: JSON.stringify({
        budget_id: state.selected,
        model: document.getElementById("usageModel").value,
        prompt_tokens: Number(document.getElementById("usagePrompt").value),
        completion_tokens: Number(document.getElementById("usageCompletion").value),
        project_id: "demo",
        flight_id: state.lastFlightId,
      }),
    });
    await loadRunway(state.selected);
    say("Logged " + money(result.priced.cost_usd) + " — runway + forecast updated.");
  } catch (err) {
    say(String(err.message || err), true);
    try {
      if (state.selected) await loadRunway(state.selected);
    } catch (_) {}
  } finally {
    setBusy(false);
  }
});

document.getElementById("flightBtn").addEventListener("click", async () => {
  if (!needTank()) return;
  const task = document.getElementById("flightTask").value;
  try {
    setBusy(true, "Running pre-flight");
    const plan = await api("/v1/flights/plan", {
      method: "POST",
      body: JSON.stringify({
        budget_id: state.selected,
        name: "Dashboard flight",
        model: document.getElementById("flightModel").value,
        task_type: task,
        estimated_turns: Number(document.getElementById("flightTurns").value),
        agent_depth: task === "agent" ? 3 : 1,
      }),
    });
    state.lastFlightId = plan.flight_id;
    document.getElementById("takeoffCard").classList.remove("hidden");
    const decision = document.getElementById("takeoffDecision");
    decision.textContent = plan.takeoff.decision;
    decision.dataset.decision = plan.takeoff.decision;
    document.getElementById("takeoffReason").textContent = plan.takeoff.reason;
    document.getElementById("takeoffCosts").textContent =
      "Est. p50 " +
      money(plan.estimate.p50.cost_usd) +
      " · p90 " +
      money(plan.estimate.p90.cost_usd) +
      " · usable " +
      money(plan.takeoff.usable_usd);
    await loadForecast(state.selected);
    say("Pre-flight result: " + plan.takeoff.decision);
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

async function flightAction(path, body) {
  if (!state.lastFlightId) throw new Error("Run a pre-flight check first.");
  const opts = { method: "POST" };
  if (body) opts.body = JSON.stringify(body);
  return api("/v1/flights/" + state.lastFlightId + path, opts);
}

document.getElementById("startBtn").addEventListener("click", async () => {
  try {
    setBusy(true, "Starting flight");
    const flight = await flightAction("/start");
    say("Flight started (" + flight.status + "). Now log usage to burn fuel.");
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("landBtn").addEventListener("click", async () => {
  try {
    setBusy(true, "Emergency landing");
    await flightAction("/emergency-landing", { note: "Dashboard mayday" });
    say("Landed. Progress saved. Refuel, then Resume.");
    if (state.selected) await loadRunway(state.selected);
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("resumeBtn").addEventListener("click", async () => {
  try {
    setBusy(true, "Resuming");
    const data = await flightAction("/resume", { note: "Dashboard resume" });
    say("Resumed (" + data.flight.status + ").");
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("refuelBtn").addEventListener("click", async () => {
  if (!needTank()) return;
  const add = Number(document.getElementById("refuelAmount").value);
  if (!(add > 0)) {
    say("Enter a positive refuel amount.", true);
    return;
  }
  try {
    setBusy(true, "Refueling");
    const updated = await api("/v1/budgets/" + state.selected, {
      method: "PATCH",
      body: JSON.stringify({ add_limit_usd: add }),
    });
    await loadBudgets();
    say("Refueled. New limit " + money(updated.limit_usd) + ".");
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("forecastBtn").addEventListener("click", async () => {
  if (!needTank()) return;
  try {
    setBusy(true, "Refreshing forecast");
    await loadForecast(state.selected);
    say("30-day forecast updated on the runway panel.");
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("weatherBtn").addEventListener("click", async () => {
  if (!needTank()) return;
  try {
    setBusy(true, "Weather plan");
    const plan = await api("/v1/weather/plan", {
      method: "POST",
      body: JSON.stringify({
        budget_id: state.selected,
        name: "Weathered flight",
        model: "gpt-4o",
        task_type: "agent",
        estimated_turns: 10,
        agent_depth: 3,
        risk_tags: ["full_fs"],
      }),
    });
    state.lastFlightId = plan.flight_id;
    document.getElementById("moreLog").textContent = JSON.stringify(plan.takeoff || plan, null, 2);
    say("Weather plan: " + (plan.takeoff && plan.takeoff.decision));
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

document.getElementById("gsToggleBtn").addEventListener("click", async () => {
  try {
    setBusy(true, "Updating ground stop");
    const next = !state.groundStop;
    const gs = await api("/v1/fleet/ground-stop", {
      method: "POST",
      body: JSON.stringify({ active: next, reason: "Dashboard toggle" }),
    });
    state.groundStop = gs.ground_stop;
    document.getElementById("moreLog").textContent = gs.message;
    say(gs.message);
  } catch (err) {
    say(String(err.message || err), true);
  } finally {
    setBusy(false);
  }
});

(async function boot() {
  try {
    await refreshHealth();
    await loadBudgets();
    say(state.selected ? "Ready — watch the runway panel while you log usage." : "Ready — create a fuel tank.");
    const gs = await api("/v1/fleet/ground-stop");
    state.groundStop = gs.ground_stop;
    if (gs.ground_stop) say("Ground stop is ON — turn it off under Advanced to plan flights.", true);
  } catch (err) {
    say(String(err.message || err), true);
  }
})();
