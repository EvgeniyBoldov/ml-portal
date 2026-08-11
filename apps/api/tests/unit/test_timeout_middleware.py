from app.core.middleware import TimeoutMiddleware


def test_sandbox_run_and_resume_are_streaming_routes():
    middleware = TimeoutMiddleware(app=object(), timeout_seconds=1)

    assert middleware._is_streaming("/api/v1/sandbox/sessions/session-1/run")
    assert middleware._is_streaming("/api/v1/sandbox/sessions/session-1/runs/run-1/resume")


def test_non_streaming_run_like_route_keeps_timeout():
    middleware = TimeoutMiddleware(app=object(), timeout_seconds=1)

    assert not middleware._is_streaming("/api/v1/sandbox/sessions/session-1/runs")
