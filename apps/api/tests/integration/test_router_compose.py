def test_router_compose_imports():
    # Import shouldn't raise even when some routers are missing.
    from app.api.v1.router import router  # noqa: F401
