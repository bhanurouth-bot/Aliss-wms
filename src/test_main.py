import pytest
from fastapi.testclient import TestClient
from src.main import app

# Create a TestClient instance using your FastAPI app
client = TestClient(app)

def test_app_initialization():
    """Test that the app is properly configured with correct metadata."""
    assert app.title == "Pet Products ERP API"
    assert app.version == "1.0.0"
    assert app.description == "Enterprise Backend for WMS, APS, and Order Management"

def test_health_check():
    """Test the /health endpoint to ensure the API is responsive."""
    response = client.get("/health")
    
    # Check that the request was successful
    assert response.status_code == 200
    
    # Check the JSON payload returned by the health check
    data = response.json()
    assert data["status"] == "online"
    assert data["database"] == "SQLite connected."

def test_routers_included():
    """Test that specific routes from the included routers exist."""
    # We can test if the router paths are registered by looking at the app's routes
    routes = [route.path for route in app.routes]
    
    # The health route should be there
    assert "/health" in routes
    
    # Note: To fully test this, you would check a specific path from one of your routers.
    # For example, if auth_api has a "/login" route, you could test:
    # assert "/login" in routes