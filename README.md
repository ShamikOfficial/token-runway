# TokenRunway

**LLM flight control for budget runway** — ingest usage, estimate flight fuel, **Abandon Takeoff** when you can’t finish, and project the next 30 days.

Local AWS is **[Floci](https://floci.io/)** on port `4566`. Same boto3 calls you would make against real AWS.

Repo: **https://github.com/ShamikOfficial/token-runway** (public)

> Stages 1–2 of 5 — see `EXECUTION_PLAN.md` for Emergency Landing, Tailwind/Headwind, etc.

---

## Quick start

```bash
docker compose up --build -d
```

Wait until the API is healthy, then:

```bash
python -m pip install httpx
python scripts/demo_stage1.py
python scripts/demo_stage2.py
python scripts/verify_floci.py
```

Open the dashboard: **http://localhost:8000/**

API docs: **http://localhost:8000/docs**

---

## What’s live

| Stage | Capability |
|-------|------------|
| 1 | Usage ingest, LiteLLM pricing, runway days, Floci DynamoDB/S3 |
| 2 | Flight plans, pre-flight, **Abandon Takeoff** (CLEAR/REPLAN/ABANDON), 30-day forecast, Tower SNS scan |

---

## Handy examples

```bash
# create a fuel tank
curl -s http://localhost:8000/v1/budgets \
  -H "content-type: application/json" \
  -d "{\"name\":\"Weekend build\",\"limit_usd\":50}"

# plan a flight (replace BUDGET_ID)
curl -s http://localhost:8000/v1/flights/plan \
  -H "content-type: application/json" \
  -d "{\"budget_id\":\"BUDGET_ID\",\"name\":\"Agent weekend\",\"model\":\"gpt-4o\",\"task_type\":\"agent\",\"estimated_turns\":20,\"agent_depth\":4}"

# 30-day forecast
curl -s "http://localhost:8000/v1/budgets/BUDGET_ID/forecast?days=30"

# tower scan (SNS on Floci)
curl -s -X POST http://localhost:8000/v1/budgets/BUDGET_ID/tower/scan
```

---

## Local Python tests

```bash
python -m pip install -e packages/runway_core -r apps/api/requirements.txt -r requirements-dev.txt
python -m pytest -q
```

With the stack up, live Floci tests also run:

```bash
python -m pytest -q tests/test_stage1_live.py tests/test_stage2_live.py
```

---

## Layout

```text
apps/api               FastAPI + entrypoint (waits for Floci, seeds, serves UI)
apps/ui/public         Dashboard (runway + flight plan + tower)
packages/runway_core   pricing, burn, runway, flight_plan, forecast, tower, store
scripts/seed_floci.py  DynamoDB + S3 + SNS
scripts/demo_stage1.py Stage 1 exit demo
scripts/demo_stage2.py Stage 2 E2E (abandon → clear → forecast → tower)
```

---

## Why Floci (portfolio note)

Coding agents and demos should not need a paid cloud account to prove AWS skills. TokenRunway points boto3 at `http://floci:4566` in Compose. Flip `AWS_ENDPOINT_URL` off (and use real creds) when you deploy to AWS — the store code stays the same.
