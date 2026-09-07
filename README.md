# TokenRunway

**LLM flight control for budget runway** — plan fuel before takeoff, land safely when burn spikes, and make cost↔safety tradeoffs visible (Tailwind / Headwind).

Local AWS via **[Floci](https://floci.io/)** · Public repo: **https://github.com/ShamikOfficial/token-runway** · License: MIT

Stages **1–5** ship as a working Compose demo. See `EXECUTION_PLAN.md` for the product narrative.

---

## Why this exists

Gateways and dashboards show **what you spent**. TokenRunway answers **whether you’ll finish** — and how to land if you won’t — using aviation language (bingo fuel, abandon takeoff, emergency landing, weather).

Built on Floci so the same **boto3** path demos DynamoDB, S3, and SNS locally without rewriting for AWS later.

---

## Quick start

```bash
docker compose up --build -d
python -m pip install httpx PyYAML
python scripts/demo_full.py
```

| Surface | URL |
|---------|-----|
| Dashboard | http://localhost:8000/ |
| OpenAPI | http://localhost:8000/docs |
| Floci | http://localhost:4566 |

---

## Architecture (what actually ships)

```text
Browser / demos
    → FastAPI (apps/api)  :8000
         → runway_core (pricing, burn, flights, weather, fleet, store)
         → Floci :4566  (DynamoDB · S3 · SNS)

Optional: packages/runway_adapters  (LiteLLM success_callback → POST /v1/usage)
UI: vanilla HTML/CSS/JS under apps/ui/public (served by the API)
Infra notes: infra/README.md  (CDK sketch — not required for the demo)
```

---

## Demo map

| Script | What it proves |
|--------|----------------|
| `demo_stage1.py` | Usage ingest + runway days on Floci |
| `demo_stage2.py` | Abandon Takeoff → CLEAR + 30-day forecast + tower |
| `demo_stage3.py` | Emergency Landing → **budget top-up** → **same-flight resume** + Holding + Black Box |
| `demo_stage4.py` | Tailwind / Headwind / Crosswind |
| `demo_stage5.py` | Weight & Balance, Ground Stop (persisted), NOTAMs |
| `demo_full.py` | Runs all of the above |
| `verify_floci.py` | DynamoDB + S3 proof |

---

## Features

- **Fuel & Runway** — LiteLLM pricing + license overrides, EWMA burn, bingo reserve, `PATCH /v1/budgets/{id}` top-up  
- **Flight plans** — task growth curves, CLEAR / REPLAN / ABANDON  
- **In flight** — start, hold, emergency landing checkpoints (S3), black box audit, resume after refuel  
- **Weather** — Tailwind playbooks, Headwind risk surcharges, diversion / jettison hints  
- **Fleet** — weight & balance, ground stop + NOTAMs persisted in DynamoDB meta  
- **Adapter** — optional LiteLLM success callback (`packages/runway_adapters`)

---

## Tests

```bash
python -m pip install -e packages/runway_core -r apps/api/requirements.txt -r requirements-dev.txt
python -m pytest -q --ignore=tests/test_stage1_live.py --ignore=tests/test_stage2_live.py --ignore=tests/test_stage3_live.py
```

With Compose up, live tests also run against `:8000`.

---

## Curl taste

```bash
# Create a tank
curl -s -X POST http://localhost:8000/v1/budgets \
  -H 'content-type: application/json' \
  -d '{"name":"demo","limit_usd":25}' 

# Top up after landing
curl -s -X PATCH http://localhost:8000/v1/budgets/$BUDGET_ID \
  -H 'content-type: application/json' \
  -d '{"add_limit_usd":20}'
```

---

## Why Floci

Same boto3 code path as real AWS. Compose points at `http://floci:4566`. Clear `AWS_ENDPOINT_URL` for a real account later — see `infra/README.md`.
