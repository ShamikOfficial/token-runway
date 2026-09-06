# TokenRunway

**LLM flight control for budget runway** — plan fuel before takeoff, land safely when burn spikes, and make cost↔safety tradeoffs visible (Tailwind / Headwind).

Local AWS via **[Floci](https://floci.io/)** · Public repo: **https://github.com/ShamikOfficial/token-runway**

Stages **1–5 complete**. See `EXECUTION_PLAN.md`.

---

## Quick start

```bash
docker compose up --build -d
python -m pip install httpx PyYAML
python scripts/demo_full.py
```

Dashboard: **http://localhost:8000/** · API docs: **/docs**

---

## Demo map

| Script | What it proves |
|--------|----------------|
| `demo_stage1.py` | Usage ingest + runway days on Floci |
| `demo_stage2.py` | Abandon Takeoff → CLEAR + 30-day forecast + tower |
| `demo_stage3.py` | Emergency Landing + Holding + Black Box + resume |
| `demo_stage4.py` | Tailwind / Headwind / Crosswind |
| `demo_stage5.py` | Weight & Balance, Ground Stop, NOTAMs |
| `demo_full.py` | Runs all of the above |
| `verify_floci.py` | DynamoDB + S3 proof |

---

## Features

- **Fuel & Runway** — LiteLLM pricing + license overrides, EWMA burn, bingo reserve  
- **Flight plans** — task growth curves, CLEAR / REPLAN / ABANDON  
- **In flight** — start, hold, emergency landing checkpoints (S3), black box audit, resume  
- **Weather** — Tailwind playbooks, Headwind risk surcharges, diversion / jettison hints  
- **Fleet** — weight & balance, ground stop, NOTAMs  
- **Adapter** — optional LiteLLM success callback (`packages/runway_adapters`)

---

## Tests

```bash
python -m pip install -e packages/runway_core -r apps/api/requirements.txt -r requirements-dev.txt
python -m pytest -q
```

---

## Why Floci

Same boto3 code path as real AWS. Compose points at `http://floci:4566`. Clear `AWS_ENDPOINT_URL` for a real account later — see `infra/README.md`.
