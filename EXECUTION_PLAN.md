# TokenRunway — Execution Plan

Open-source **LLM flight control plane**: forecast runway, gate takeoffs, land safely, optimize (Tailwind) or spend for safety (Headwind).  
Built on **Floci** (local AWS) so the same code path demos real AWS skills.

---

## North star

| Do | Don't |
|----|--------|
| Plan fuel *before* work starts | Rebuild LiteLLM / Portkey / Helicone |
| Forecast 30-day burn + days of runway | Invent our own model price database |
| Save progress when fuel dies (Emergency Landing) | Replace LangGraph / user agent frameworks |
| Weather: efficiency vs safety tradeoffs | Fake AWS with random mocks — use **Floci** |
| Wrap *existing* APIs & licenses | Force users to move API keys to us |

**Tagline:** Gateways show what you spent. We show whether you’ll finish — and how to land if you won’t.

---

## Reuse existing open source (no duplication)

| Need | Use this | We only add |
|------|----------|-------------|
| Local AWS | **Floci** (`floci/floci`) on `:4566` | Compose wiring + seed scripts |
| Model prices / cost math | **LiteLLM** `completion_cost` / price map | License price *overrides* JSON |
| Optional usage tap | **LiteLLM** success callback → our ingest | Flight metadata (`flight_id`, task type) |
| HTTP API | **FastAPI** + **Pydantic** | Domain routes named like the product |
| AWS SDK | **boto3** with `endpoint_url` | Thin `aws_clients.py` (Floci vs real) |
| IaC | **AWS CDK** (Python) | Stacks that work against Floci *and* AWS |
| Token helpers (optional) | **tiktoken** / provider usage fields | Prefer provider-reported usage first |
| Tests | **pytest** + compose Floci | Integration tests on real emulated APIs |
| UI | **Vanilla HTML/CSS/JS** (served by FastAPI) | Flight / Tower / Weather / Fleet on one dashboard |
| Charts | Plain CSS sparkline | Runway + forecast visuals |
| Config | **pydantic-settings** + `.env` | Human-readable env names |
| HTTP client | **httpx** | Adapter calls |

**Explicit non-goals (already solved elsewhere):** full LLM gateway, tracing platform (Langfuse), agent orchestration (LangGraph), payment firewalls (Sipi/SpendOS).

**Integrate later (optional adapters, not forks):** LiteLLM callback plugin, thin wrap around OpenAI/Anthropic SDKs that only posts usage events.

---

## Coding style (your voice)

- Names from the product: `abandon_takeoff`, `bingo_fuel_ok`, `emergency_landing` — not `processHandlerV2`.
- Short functions; one job each; comments only where the *why* isn’t obvious.
- Prefer clear `if` / early returns over clever abstractions.
- Config and magic numbers live in named constants or YAML playbooks.
- No giant class hierarchies; plain modules + Pydantic models are enough.
- README and docstrings talk like a human explaining the plane, not enterprise whitepaper.

---

## Repo layout (as shipped)

```text
TokenRunway/
  docker-compose.yml          # Floci + API
  EXECUTION_PLAN.md
  README.md
  LICENSE
  .env.example
  infra/                      # AWS mapping notes (+ CDK sketch guidance)
  apps/
    api/                      # FastAPI
    ui/public/                # Vanilla dashboard (Stages 1–5 controls)
  packages/
    runway_core/              # pricing, burn, flights, weather, fleet, store
    runway_adapters/          # LiteLLM success_callback → /v1/usage
  scripts/
    seed_floci.py
    demo_stage{1-5}.py
    demo_full.py
  samples/
    pricing_overrides.json
    playbooks/                # tailwind + headwind YAML
```

Earlier drafts imagined split packages (`runway_flight`, Vite React). Domain code lives in **`runway_core`**; the UI is intentionally a thin static dashboard so the AWS/Floci story stays the hero.
---

## AWS / Floci map (portfolio proof)

| Feature | AWS service (via Floci) |
|---------|-------------------------|
| HTTP API | API Gateway + Lambda *or* FastAPI talking to AWS resources |
| Budgets, flights, usage | DynamoDB |
| Checkpoints / evidence | S3 |
| Scheduled forecast | EventBridge → Lambda |
| Tower alerts | SNS (+ webhook subscriber) |
| Config secrets (later) | SSM Parameter Store |
| Observability | CloudWatch Logs |

Every stage must keep: `AWS_ENDPOINT_URL=http://localhost:4566` (or CDK override) so **one codebase → Floci today, AWS tomorrow**.

---

## Rollout: 5 stages

### Stage 1 — Fuel & Runway (basics)  
**Goal:** Ingest usage, price it, show burn + days left. Floci is up.  
**Demo line:** “Here’s my budget and how many days of fuel I have.”

| Deliverable | Detail |
|-------------|--------|
| Compose | `floci` service + volume; API service |
| Seed | DynamoDB tables: `budgets`, `usage_events`; S3 bucket `tokenrunway-raw` |
| Ingest API | `POST /v1/usage` — model, in/out tokens, timestamp, optional `project_id` |
| Pricing | LiteLLM cost for public models; merge `pricing_overrides.json` for licenses |
| Runway | Remaining $ / daily burn (simple EWMA) → `days_remaining` |
| Read API | `GET /v1/budgets/{id}/runway` |
| UI (thin) | One page: budget, spend, days left |
| Docs | README: `docker compose up`, curl examples |

**Exit criteria:** Fresh clone → compose up → seed → post 20 fake usage events → runway number looks sane.

**Estimate:** 1–2 days

---

### Stage 2 — Flight Plan & Abandon Takeoff  
**Goal:** Don’t start work you can’t finish. 30-day forecast + Tower warnings.

| Deliverable | Detail |
|-------------|--------|
| Flight plan | `POST /v1/flights/plan` — task_type, model, estimated turns, agent_depth |
| Pre-flight | Checklist: budget exists, price known, reserve (bingo %) set |
| Estimate | Task priors + optional growth curve → p50/p90 tokens & $ |
| Abandon Takeoff | If p90 > remaining − bingo → `CLEAR` / `ABANDON` / `REPLAN` suggestions |
| Forecast | `GET .../forecast?days=30` — p50/p90 spend & tokens |
| Tower | EventBridge daily job; SNS when runway &lt; 7d / 3d |
| UI | Plan form + clear/abandon result + forecast chart |

**Exit criteria:** Plan a heavy agent project on a tiny budget → Abandon Takeoff; shrink plan or Tailwind stub → Clear.

**Estimate:** 2–3 days

---

### Stage 3 — In flight: Emergency Landing & Black Box  
**Goal:** Mid-job survival. Progress saved; audit trail.

| Deliverable | Detail |
|-------------|--------|
| Active flight | `POST /v1/flights/{id}/start` — bind usage to `flight_id` |
| Bingo fuel | Never burn last N% except landing save |
| Turbulence | Burn rate spike vs baseline → squawk alert |
| Emergency Landing | Soft-stop further calls; write checkpoint JSON to S3; status `LANDED_EMERGENCY` |
| Holding Pattern | Pause without destroying state; resume when refueled |
| Black Box | Append-only `audit_events` in DynamoDB (decision, reason, amounts) |
| Resume | `POST /v1/flights/{id}/resume` after top-up |
| UI | Active flights, land button, checkpoint download link |

**Exit criteria:** Simulated runaway usage → Emergency Landing → checkpoint in Floci S3 → resume after budget bump.

**Estimate:** 2–3 days

---

### Stage 4 — Weather: Tailwind & Headwind  
**Goal:** Cost efficiency *and* deliberate safety spend. Crosswind made visible.

| Deliverable | Detail |
|-------------|--------|
| Tailwind playbooks | YAML rules: compress history, cheaper model, max turns, cache hint — each with **estimated % save** |
| Apply Tailwind | Attach playbook to plan/flight; re-estimate; show before/after |
| Headwind profiles | Risk tags: `code_exec`, `full_fs`, `cloud_admin`, `pii` → extra verify pass / stricter prompt — **surcharge %** |
| Crosswind | UI when both apply: “saving X% but safety wants +Y%” |
| Diversion | Suggest mid-flight model downgrade (estimate only in MVP; enforce optional) |
| Jettison | API to mark context trim recommended |
| UI | Weather panel on flight detail |

**Exit criteria:** Same flight plan with Tailwind clears; with `full_fs` Headwind shows higher fuel need and why.

**Estimate:** 2–3 days

---

| 5 Tower polish / portfolio | **Complete** (fleet + persisted ground stop/NOTAMs + adapter + infra notes; CDK optional) |
**Goal:** Portfolio-ready OSS + clear AWS narrative.

| Deliverable | Detail |
|-------------|--------|
| Weight & Balance | Split budget across projects; wake-turbulence alert if one flight &gt; X% |
| Ground Stop | Freeze new takeoffs for a project/org |
| NOTAM | Price/license change notices affecting forecasts |
| LiteLLM adapter | Drop-in success_callback → ingest (no gateway fork) |
| CDK | Infra notes + deploy sketch (`infra/README.md`); full CDK optional follow-up |
| Demo script | `scripts/demo_full.py` walks Stages 1–5 |
| README | Architecture, competitor wedge, Floci→AWS path |
| Afterburner / Slot (light) | Optional burst flag + “schedule when window renews” note |

**Exit criteria:** One demo script + compose = full story; README explains Floci→AWS without code rewrite.

**Estimate:** 2–4 days

---

## Stage dependency graph

```text
Stage 1 Fuel/Runway
    → Stage 2 Plan/Abandon/Forecast/Tower
        → Stage 3 Emergency/Holding/Black Box
            → Stage 4 Tailwind/Headwind
                → Stage 5 Multi-project + CDK + OSS adapters
```

Do not skip Stage 1–2; Stage 4 can slim if time-boxed (Tailwind + one Headwind profile only).

---

## Day-one checklist (start Stage 1 today)

1. Init git repo + Python package layout + `.env.example`
2. `docker-compose.yml` with Floci (`4566`) + API build
3. `aws_clients.py` — boto3 session forced to Floci endpoint when `RUNWAY_ENV=local`
4. `scripts/seed_floci.py` — create tables + bucket
5. LiteLLM cost helper + overrides file
6. `POST /v1/usage` + `GET /v1/budgets/{id}/runway`
7. Minimal UI or even FastAPI `/docs` until UI lands end of Stage 1
8. README section: “Why Floci” for the portfolio

---

## Testing per stage

- **Unit:** forecast math, abandon decision, bingo math (pure Python, no Docker)
- **Integration:** compose up → seed → API calls against Floci
- **Demo:** scripted path matching portfolio talk track

---

## Portfolio talk track (final)

1. Floci = local AWS; here’s DynamoDB/S3/SNS in compose  
2. Usage in → LiteLLM prices → runway days  
3. Abandon Takeoff on an underfunded agent plan  
4. Emergency Landing saves checkpoint to S3  
5. Tailwind vs Headwind = cost governance, not only caps  
6. Same CDK path aims at real AWS when I’m ready  

---

## What we will not build in v1

- Full multi-tenant SaaS billing  
- Replacing LiteLLM proxy  
- Training custom ML burn models (EWMA + growth curves first)  
- Perfect invoice parity (planning-grade estimates + confidence)  

---

## Status

| Stage | Status |
|-------|--------|
| 1 Fuel & Runway | **Complete** |
| 2 Flight Plan & Abandon | **Complete** |
| 3 Emergency Landing | **Complete** |
| 4 Weather | **Complete** |
| 5 Tower polish / portfolio | **Complete** (fleet + persisted ground stop/NOTAMs + adapter + infra notes; CDK optional) |

Portfolio demo: `python scripts/demo_full.py` with Compose up.

