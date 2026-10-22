from fastapi.routing import APIRoute

from app.api.deps import require_admin
from app.main import app
from app.api.v1.routers import monitoring
from app.api.v1.routers.rag import upload


def test_detailed_monitoring_routes_require_admin():
    protected_paths = {"/monitoring/metrics", "/monitoring/health/detailed"}
    routes = {
        route.path: route
        for route in monitoring.router.routes
        if isinstance(route, APIRoute) and route.path in protected_paths
    }

    assert set(routes) == protected_paths
    for route in routes.values():
        assert any(dependency.call is require_admin for dependency in route.dependant.dependencies)


def test_legacy_unscoped_rag_presign_route_is_removed():
    assert all(route.path != "/upload/presign" for route in upload.router.routes)


def test_root_metrics_route_requires_admin():
    route = next(route for route in app.routes if isinstance(route, APIRoute) and route.path == "/metrics")

    assert any(dependency.call is require_admin for dependency in route.dependant.dependencies)
