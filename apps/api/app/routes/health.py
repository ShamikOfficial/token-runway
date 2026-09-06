from fastapi import APIRouter

from runway_core.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "ok": True,
        "stage": 2,
        "env": settings.runway_env,
        "floci": settings.using_floci,
        "endpoint": settings.aws_endpoint_url,
    }
