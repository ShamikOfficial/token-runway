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

async function refreshHealth() {
  const chip = document.getElementById("healthChip");
  try {
    const h = await api("/health");
    chip.textContent = h.floci ? `Floci · stage ${h.stage}` : `env: ${h.env}`;
    chip.className = "chip ok";
  } catch (err) {
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
    document.getElementById("usageBudgetId").value = state.selected;
    document.getElementById("flightBudgetId").value = state.selected;
    await loadRunway(state.selected);
  }
}

async function selectBudget(id) {
  state.selected = id;
  document.getElementById("usageBudgetId").value = id;
  document.getElementById("flightBudgetId").value = id;
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
  document.getElementById("statusPill").textContent = r.status;
  document.getElementById("runwayNote").textContent = r.note;
  document.getElementById("mLimit").textContent = money(r.limit_usd);
  document.getElementById("mSpent").textContent = money(r.spent_usd);
  document.getElementById("mRemain").textContent = money(r.remaining_usd);
  document.getElementById("mBurn").textContent = money(r.daily_burn_usd);
  document.getElementById("mBingo").textContent = money(r.bingo_reserve_usd);
  document.getElementById("mEvents").textContent = String(r.event_count);
}

document.getElementById("budgetForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    name: fd.get("name"),
    limit_usd: Number(fd.get("limit_usd")),
  };
  const created = await api("/v1/budgets", { method: "POST", body: JSON.stringify(body) });
  await loadBudgets();
  await selectBudget(created.budget_id);
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
  };
  try {
    const result = await api("/v1/usage", { method: "POST", body: JSON.stringify(body) });
    document.getElementById("lastEvent").textContent = JSON.stringify(result, null, 2);
    await loadRunway(body.budget_id);
  } catch (err) {
    document.getElementById("lastEvent").textContent = String(err.message || err);
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
    state.lastFlightId = plan.flight_id;
    document.getElementById("takeoffCard").classList.remove("hidden");
    document.getElementById("takeoffDecision").textContent = plan.takeoff.decision;
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
    document.getElementById("forecastLog").textContent = JSON.stringify(
      { flight_id: plan.flight_id, takeoff: plan.takeoff, estimate: plan.estimate },
      null,
      2
    );
  } catch (err) {
    document.getElementById("forecastLog").textContent = String(err.message || err);
  }
});

document.getElementById("forecastBtn").addEventListener("click", async () => {
  const bid = document.getElementById("flightBudgetId").value;
  if (!bid) return;
  const params = new URLSearchParams({ days: "30" });
  if (state.lastFlightId) params.set("flight_id", state.lastFlightId);
  try {
    const data = await api(`/v1/budgets/${bid}/forecast?${params}`);
    document.getElementById("forecastLog").textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    document.getElementById("forecastLog").textContent = String(err.message || err);
  }
});

document.getElementById("towerBtn").addEventListener("click", async () => {
  const bid = document.getElementById("flightBudgetId").value;
  if (!bid) return;
  try {
    const data = await api(`/v1/budgets/${bid}/tower/scan`, { method: "POST" });
    document.getElementById("forecastLog").textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    document.getElementById("forecastLog").textContent = String(err.message || err);
  }
});

refreshHealth();
loadBudgets().catch((err) => {
  document.getElementById("budgetList").textContent = String(err.message || err);
});
