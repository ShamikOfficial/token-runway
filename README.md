# TokenRunway

**LLM flight control for budget runway** — Stage 1 is live: ingest usage, price it (LiteLLM + license overrides), and see **how many days of fuel you have left**.

Local AWS is **[Floci](https://floci.io/)** on port `4566`. Same boto3 calls you would make against real AWS.

> Stage 1 of 5 — see `EXECUTION_PLAN.md` for Abandon Takeoff, Emergency Landing, Tailwind/Headwind, etc.

---

## Quick start

```bash
docker compose up --build -d
```

Wait until the API is healthy, then:

```bash
python -m pip install httpx
python scripts/demo_stage1.py
python scripts/verify_floci.py
```

Open the dashboard: **http://localhost:8000/**

API docs: **http://localhost:8000/docs**

---

## What Stage 1 proves

| Piece | How |
|--------|-----|
| Floci | DynamoDB tables + S3 bucket created by seed on boot |
| Pricing | LiteLLM for public models; `samples/pricing_overrides.json` for your licenses |
| Ingest | `POST /v1/usage` stores events in DynamoDB and archives JSON to S3 |
| Runway | EWMA daily burn → `days_remaining` after bingo reserve |
| UI | One page: create budget, log usage, read runway |

---

## Handy curls

```bash
# create a fuel tank
curl -s http://localhost:8000/v1/budgets \
  -H "content-type: application/json" \
  -d "{\"name\":\"Weekend build\",\"limit_usd\":50}" 

# log usage (replace BUDGET_ID)
curl -s http://localhost:8000/v1/usage \
  -H "content-type: application/json" \
  -d "{\"budget_id\":\"BUDGET_ID\",\"model\":\"gpt-4o-mini\",\"prompt_tokens\":1200,\"completion_tokens\":400}"

# runway
curl -s http://localhost:8000/v1/budgets/BUDGET_ID/runway
```

---

## Local Python tests (no Docker)

```bash
python -m pip install -e packages/runway_core -r apps/api/requirements.txt -r requirements-dev.txt
pytest -q
```

---

## Layout

```text
apps/api          FastAPI + entrypoint (waits for Floci, seeds, serves UI)
apps/ui/public    Stage 1 dashboard
packages/runway_core   pricing, burn, runway, FuelStore, aws_clients
scripts/seed_floci.py  create tables + bucket
scripts/demo_stage1.py exit-criteria demo
samples/pricing_overrides.json
```

---

## Why Floci (portfolio note)

Coding agents and demos should not need a paid cloud account to prove AWS skills. TokenRunway points boto3 at `http://floci:4566` in Compose. Flip `AWS_ENDPOINT_URL` off (and use real creds) when you deploy to AWS — the store code stays the same.
