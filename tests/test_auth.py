# tests/test_auth.py

def test_register_new_user(client):
    """Test that the system can successfully register a new Admin user."""
    
    payload = {
        "username": "test_admin",
        "email": "test@erp.com",
        "password": "securepassword",
        "role": "Admin"
    }
    
    # 1. Send the fake request
    response = client.post("/auth/register", json=payload)
    
    # 2. Assert the results match reality
    assert response.status_code == 201
    
    data = response.json()
    assert data["username"] == "test_admin"
    assert data["role"] == "Admin"
    assert "password" not in data # Ensure the API never leaks the password!