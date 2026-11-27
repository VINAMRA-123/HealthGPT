import pytest

from app.observability import ChatMetrics, percentile, summarize


def test_percentile_matches_linear_interpolation():
    values = list(range(1, 101))  # 1..100
    assert percentile(values, 50) == pytest.approx(50.5)
    assert percentile(values, 90) == pytest.approx(90.1)
    assert percentile(values, 95) == pytest.approx(95.05)
    assert percentile(values, 0) == 1
    assert percentile(values, 100) == 100


def test_percentile_edge_cases():
    assert percentile([], 50) is None
    assert percentile([7], 99) == 7


def test_summarize_empty():
    assert summarize([])["count"] == 0
    assert summarize([])["p95"] is None


def test_snapshot_groups_by_path():
    metrics = ChatMetrics()

    for ms in (10, 20, 30):
        metrics.record(intent="daily_nutrition", model="sql", status="ok", latency_ms=ms)

    metrics.record(
        intent="llm",
        model="gemini",
        status="ok",
        latency_ms=2000,
        first_token_ms=800,
    )
    metrics.record(intent="off_topic", model="guardrail", status="ok", latency_ms=1)
    metrics.record(intent="llm", model=None, status="error", latency_ms=500)

    snap = metrics.snapshot()

    assert snap["window_requests"] == 6
    assert snap["by_path"]["sql"]["requests"] == 3
    assert snap["by_path"]["sql"]["latency_ms"]["p50"] == 20
    assert snap["by_path"]["llm"]["errors"] == 1
    assert snap["by_path"]["llm"]["first_token_ms"]["count"] == 1
    assert snap["by_path"]["guardrail"]["requests"] == 1
    assert snap["share_percent"]["sql"] == 50.0


def test_window_is_bounded():
    metrics = ChatMetrics(max_events=3)

    for ms in range(10):
        metrics.record(intent="llm", model="m", status="ok", latency_ms=ms)

    assert metrics.snapshot()["window_requests"] == 3
