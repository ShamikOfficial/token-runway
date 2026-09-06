"""boto3 clients pointed at Floci locally, or real AWS when endpoint is cleared."""

from __future__ import annotations

import boto3
from botocore.config import Config

from runway_core.settings import Settings, get_settings


_SOFT_RETRIES = Config(retries={"max_attempts": 8, "mode": "standard"})


def _base_kwargs(settings: Settings) -> dict:
    kwargs: dict = {
        "region_name": settings.aws_default_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "config": _SOFT_RETRIES,
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


def dynamodb_resource(settings: Settings | None = None):
    settings = settings or get_settings()
    return boto3.resource("dynamodb", **_base_kwargs(settings))


def dynamodb_client(settings: Settings | None = None):
    settings = settings or get_settings()
    return boto3.client("dynamodb", **_base_kwargs(settings))


def s3_client(settings: Settings | None = None):
    settings = settings or get_settings()
    return boto3.client("s3", **_base_kwargs(settings))
