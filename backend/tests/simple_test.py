import pytest
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, '/app')

from fastapi.testclient import TestClient
from app.main import app

def test_app_import():
    """Test that the app can be imported"""
    assert app is not None

def test_app_has_routes():
    """Test that the app has routes"""
    routes = [route.path for route in app.routes]
    assert "/api/chats" in routes

def test_health_check():
    """Test basic health check"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
