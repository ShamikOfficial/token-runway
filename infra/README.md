# Infra notes

TokenRunway is written so the same boto3 calls work against **Floci** (`AWS_ENDPOINT_URL`)
or real AWS (clear the endpoint + use real credentials).

## Suggested AWS shape (real account later)

| Concern | Service |
|---------|---------|
| HTTP API | API Gateway HTTP API → Lambda (container or zip) |
| State | DynamoDB (`budgets`, `usage`, `flights`, `audit`, `meta`) |
| Checkpoints | S3 versioned bucket |
| Tower alerts | SNS topic → email/Slack |
| Daily runway scan | EventBridge schedule → Lambda `tower/scan` |

## Local (what we ship today)

```bash
docker compose up --build -d
python scripts/seed_floci.py   # safe to re-run; creates tables + bucket + topic
```

`apps/api/entrypoint.sh` waits for Floci, runs `scripts/seed_floci.py`, then serves FastAPI.
Set `RUNWAY_RELOAD=1` only when you want uvicorn `--reload` against bind-mounted source.
## CDK sketch (not required to demo)

A Python CDK app would declare the tables/bucket/topic and set `AWS_ENDPOINT_URL`
only in the Floci deploy profile. Keep application code free of LocalStack/Floci imports —
only settings change.

See root `README.md` and `EXECUTION_PLAN.md`.
