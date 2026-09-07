const state = { budgets: [], selected: null, lastFlightId: null };

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function money(n) {
  if (n === null || n === undefined) return "—";
  return `$${Number(n).toFixed(4)}`;
}

function show(el, data) {
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function syncBudgetFields(id) {
  for (const field of ["usageBudgetId", "flightBudgetId", "weatherBudgetId"]) {
    const node = document.getElementById(field);
    if (node) node.value = id || "";
  }
  if (state.lastFlightId) {
    document.getElementById("usageFlightId").value = state.lastFlightId;
  }
}

async function refreshHealth() {
  const chip = document.getElementById("healthChip");
  try {
    const h = await api("/health");
    chip.textContent = h.floci ? `Floci · stage ${h.stage}` : `env: ${h.env}`;
    chip.className = "chip ok";
  } catch {
    chip.textContent = "API down";
    chip.className = "chip muted";
  }
}

function renderBudgets() {
  const box = document.getElementById("budgetList");
  if (!state.budgets.length) {
    box.innerHTML = "<p class='hint'>No budgets yet.</p>";
    return;
  }
  box.innerHTML = "";
  for (const b of state.budgets) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "budget-row" + (state.selected === b.budget_id ? " active" : "");
    btn.innerHTML = `<span>${b.name}<br/><small>${b.budget_id}</small></span><span>${money(b.limit_usd)}</span>`;
    btn.onclick = () => selectBudget(b.budget_id);
    box.appendChild(btn);
  }
}

async function loadBudgets() {
  const data = await api("/v1/budgets");
  state.budgets = data.budgets || [];
  renderBudgets();
  if (state.selected) {
    syncBudgetFields(state.selected);
    await loadRunway(state.selected);
  }
}

async function selectBudget(id) {
  state.selected = id;
  syncBudgetFields(id);
  renderBudgets();
  await loadRunway(id);
}

async function loadRunway(id) {
  const data = await api(`/v1/budgets/${id}/runway`);
  const r = data.runway;
  document.getElementById("runwayEmpty").classList.add("hidden");
  document.getElementById("runwayCard").classList.remove("hidden");

  const days = r.days_remaining;
  document.getElementById("daysLeft").textContent = days === null ? "∞" : days;
  document.getElementById("daysLabel").textContent =
    days === null ? "need usage to estimate" : "days of usable fuel";
  const pill = document.getElementById("statusPill");
  pill.textContent = r.status;
  pill.dataset.status = r.status;
  document.getElementById("runwayNote").textContent = r.note;
  document.getElementById("mLimit").textContent = money(r.limit_usd);
  document.getElementById("mSpent").textContent = money(r.spent_usd);
  document.getElementById("mRemain").textContent = money(r.remaining_usd);
  document.getElementById("mBurn").textContent = money(r.daily_burn_usd);
  document.getElementById("mBingo").textContent = money(r.bingo_reserve_usd);
  document.getElementById("mEvents").textContent = String(r.event_count);
}

function renderTakeoff(plan) {
  state.lastFlightId = plan.flight_id;
  document.getElementById("usageFlightId").value = plan.flight_id;
  document.getElementById("takeoffCard").classList.remove("hidden");
  const decision = document.getElementById("takeoffDecision");
  decision.textContent = plan.takeoff.decision;
  decision.dataset.decision = plan.takeoff.decision;
  document.getElementById("takeoffReason").textContent = plan.takeoff.reason;
  document.getElementById("takeoffCosts").textContent =
    `p50 ${money(plan.estimate.p50.cost_usd)} · p90 ${money(plan.estimate.p90.cost_usd)} · usable ${money(plan.takeoff.usable_usd)}`;
  const ul = document.getElementById("takeoffSuggestions");
  ul.innerHTML = "";
  for (const tip of plan.takeoff.suggestions || []) {
    const li = document.createElement("li");
    li.textContent = tip;
    ul.appendChild(li);
  }
}

function renderSpark(forecast) {
  const box = document.getElementById("forecastSpark");
  const series = forecast?.series || forecast?.daily || [];
  if (!Array.isArray(series) || !series.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const values = series.map((d) => Number(d.p50_spend_usd ?? d.p50_cost_usd ?? d.cost_usd ?? 0));
  const max = Math.max(...values, 0.0001);
  const bars = values
    .map((v) => {
      const h = Math.max(4, Math.round((v / max) * 48));
      return `<span style="height:${h}px" title="${money(v)}"></span>`;
    })
    .join("");
  box.innerHTML = `<div class="spark-bars">${bars}</div><p class="hint">30-day p50 burn sparkline</p>`;
  box.classList.remove("hidden");
}

document.getElementById("budgetForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const created = await api("/v1/budgets", {
    method: "POST",
    body: JSON.stringify({ name: fd.get("name"), limit_usd: Number(fd.get("limit_usd")) }),
  });
  await loadBudgets();
  await selectBudget(created.budget_id);
});

document.getElementById("topUpForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.selected) {
    show(document.getElementById("lastEvent"), "Select a budget first");
    return;
  }
  const fd = new FormData(e.target);
  try {
    const updated = await api(`/v1/budgets/${state.selected}`, {
      method: "PATCH",
      body: JSON.stringify({ add_limit_usd: Number(fd.get("add_limit_usd")) }),
    });
    show(document.getElementById("lastEvent"), updated);
    await loadBudgets();
    await loadRunway(state.selected);
  } catch (err) {
    show(document.getElementById("lastEvent"), String(err.message || err));
  }
});

document.getElementById("usageForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    budget_id: fd.get("budget_id"),
    model: fd.get("model"),
    prompt_tokens: Number(fd.get("prompt_tokens")),
    completion_tokens: Number(fd.get("completion_tokens")),
    project_id: fd.get("project_id") || null,
    flight_id: fd.get("flight_id") || null,
  };
  try {
    const result = await api("/v1/usage", { method: "POST", body: JSON.stringify(body) });
    show(document.getElementById("lastEvent"), result);
    await loadRunway(body.budget_id);
  } catch (err) {
    show(document.getElementById("lastEvent"), String(err.message || err));
  }
});

document.getElementById("flightForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    budget_id: fd.get("budget_id"),
    name: fd.get("name"),
    model: fd.get("model"),
    task_type: fd.get("task_type"),
    estimated_turns: Number(fd.get("estimated_turns")),
    agent_depth: Number(fd.get("agent_depth")),
  };
  try {
    const plan = await api("/v1/flights/plan", { method: "POST", body: JSON.stringify(body) });
    renderTakeoff(plan);
    show(document.getElementById("forecastLog"), {
      flight_id: plan.flight_id,
      takeoff: plan.takeoff,
      estimate: plan.estimate,
    });
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

async function flightAction(path, body) {
  if (!state.lastFlightId) throw new Error("Run a pre-flight first");
  return api(`/v1/flights/${state.lastFlightId}${path}`, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

document.getElementById("startBtn").addEventListener("click", async () => {
  try {
    show(document.getElementById("forecastLog"), await flightAction("/start"));
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("holdBtn").addEventListener("click", async () => {
  try {
    show(document.getElementById("forecastLog"), await flightAction("/hold", { note: "UI holding pattern" }));
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("landBtn").addEventListener("click", async () => {
  try {
    const data = await flightAction("/emergency-landing", { note: "UI mayday", step: "saved-from-dashboard" });
    show(document.getElementById("forecastLog"), data);
    if (state.selected) await loadRunway(state.selected);
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("resumeBtn").addEventListener("click", async () => {
  try {
    show(document.getElementById("forecastLog"), await flightAction("/resume", { note: "UI resume" }));
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("forecastBtn").addEventListener("click", async () => {
  const bid = document.getElementById("flightBudgetId").value;
  if (!bid) return;
  const params = new URLSearchParams({ days: "30" });
  if (state.lastFlightId) params.set("flight_id", state.lastFlightId);
  try {
    const data = await api(`/v1/budgets/${bid}/forecast?${params}`);
    renderSpark(data);
    show(document.getElementById("forecastLog"), data);
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("towerBtn").addEventListener("click", async () => {
  const bid = document.getElementById("flightBudgetId").value;
  if (!bid) return;
  try {
    show(document.getElementById("forecastLog"), await api(`/v1/budgets/${bid}/tower/scan`, { method: "POST" }));
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("blackboxBtn").addEventListener("click", async () => {
  const bid = document.getElementById("flightBudgetId").value;
  if (!bid) return;
  try {
    show(document.getElementById("forecastLog"), await api(`/v1/budgets/${bid}/blackbox`));
  } catch (err) {
    show(document.getElementById("forecastLog"), String(err.message || err));
  }
});

document.getElementById("weatherForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const risks = String(fd.get("risk_tags") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const body = {
    budget_id: fd.get("budget_id"),
    name: "Weathered flight",
    model: fd.get("model"),
    task_type: fd.get("task_type"),
    estimated_turns: Number(fd.get("estimated_turns")),
    agent_depth: Number(fd.get("agent_depth")),
    risk_tags: risks,
    suggest_diversion: true,
  };
  try {
    const plan = await api("/v1/weather/plan", { method: "POST", body: JSON.stringify(body) });
    state.lastFlightId = plan.flight_id;
    document.getElementById("usageFlightId").value = plan.flight_id;
    show(document.getElementById("weatherLog"), plan);
  } catch (err) {
    show(document.getElementById("weatherLog"), String(err.message || err));
  }
});

document.getElementById("playbooksBtn").addEventListener("click", async () => {
  try {
    show(document.getElementById("weatherLog"), await api("/v1/weather/playbooks"));
  } catch (err) {
    show(document.getElementById("weatherLog"), String(err.message || err));
  }
});

async function refreshFleetStatus() {
  try {
    const gs = await api("/v1/fleet/ground-stop");
    document.getElementById("fleetStatus").textContent = gs.message;
  } catch {
    document.getElementById("fleetStatus").textContent = "";
  }
}

document.getElementById("wbBtn").addEventListener("click", async () => {
  try {
    show(document.getElementById("fleetLog"), await api("/v1/fleet/weight-balance"));
  } catch (err) {
    show(document.getElementById("fleetLog"), String(err.message || err));
  }
});

document.getElementById("gsOnBtn").addEventListener("click", async () => {
  try {
    show(
      document.getElementById("fleetLog"),
      await api("/v1/fleet/ground-stop", {
        method: "POST",
        body: JSON.stringify({ active: true, reason: "Dashboard ground stop" }),
      })
    );
    await refreshFleetStatus();
  } catch (err) {
    show(document.getElementById("fleetLog"), String(err.message || err));
  }
});

document.getElementById("gsOffBtn").addEventListener("click", async () => {
  try {
    show(
      document.getElementById("fleetLog"),
      await api("/v1/fleet/ground-stop", {
        method: "POST",
        body: JSON.stringify({ active: false }),
      })
    );
    await refreshFleetStatus();
  } catch (err) {
    show(document.getElementById("fleetLog"), String(err.message || err));
  }
});

document.getElementById("notamBtn").addEventListener("click", async () => {
  try {
    show(
      document.getElementById("fleetLog"),
      await api("/v1/fleet/notams", {
        method: "POST",
        body: JSON.stringify({
          code: "PRICE_CHANGE",
          message: "Model rates updated — re-run forecasts",
          severity: "INFO",
        }),
      })
    );
  } catch (err) {
    show(document.getElementById("fleetLog"), String(err.message || err));
  }
});

document.getElementById("notamListBtn").addEventListener("click", async () => {
  try {
    show(document.getElementById("fleetLog"), await api("/v1/fleet/notams"));
  } catch (err) {
    show(document.getElementById("fleetLog"), String(err.message || err));
  }
});

refreshHealth();
refreshFleetStatus();
loadBudgets().catch((err) => {
  document.getElementById("budgetList").textContent = String(err.message || err);
});
