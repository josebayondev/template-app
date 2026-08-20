from fastapi import APIRouter

router = APIRouter()


# FastAPI's APIRoute, unlike Starlette's Route, does not add HEAD to a GET route,
# so it has to be spelled out. Uptime probes default to HEAD and would otherwise
# see a 405 and report the service as down.
@router.api_route("/health", methods=["GET", "HEAD"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
