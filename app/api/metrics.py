import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException

from app.observability import chat_metrics

router = APIRouter(prefix="/api/v1/metrics", tags=["Observability"])


def require_metrics_token(
    x_metrics_token: str | None = Header(default=None),
) -> None:
    """Protect the metrics with a shared secret.

    Set METRICS_TOKEN on the server to enable the endpoint. Without it the
    endpoint behaves as if it does not exist.
    """
    expected = os.getenv("METRICS_TOKEN", "")

    if not expected:
        raise HTTPException(status_code=404, detail="Not found")

    if not x_metrics_token or not hmac.compare_digest(
        x_metrics_token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid metrics token")


@router.get("/chat", dependencies=[Depends(require_metrics_token)])
def chat_latency_metrics():
    """p50 / p90 / p95 / p99 latency, path shares and error rate."""
    return chat_metrics.snapshot()
