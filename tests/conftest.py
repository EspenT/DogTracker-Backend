"""
Pytest configuration and fixtures for end-to-end testing.
"""
import os
import pytest
from typing import Generator
from fastapi.testclient import TestClient

from main import app, DB_PATH_ENV_VAR, BOOTSTRAP_ADMIN_EMAIL_ENV_VAR, BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR

@pytest.fixture(scope="function")
def temp_db() -> Generator[str, None, None]:
    """Create a temporary database for testing."""
    # Use in-memory database for fast, isolated tests
    db_path = ":memory:"
    
    # Set environment variable for the test
    original_db_path = os.environ.get(DB_PATH_ENV_VAR)
    os.environ[DB_PATH_ENV_VAR] = db_path
    
    yield db_path
    
    # Cleanup
    if original_db_path is not None:
        os.environ[DB_PATH_ENV_VAR] = original_db_path
    elif DB_PATH_ENV_VAR in os.environ:
        del os.environ[DB_PATH_ENV_VAR]


@pytest.fixture(scope="function")
def test_client(temp_db) -> Generator[TestClient, None, None]:
    """Create a FastAPI TestClient instance."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def admin_token(test_client: TestClient) -> str:
    """Create an admin user and return authentication token."""
    # Get admin credentials from environment
    admin_email = os.getenv(BOOTSTRAP_ADMIN_EMAIL_ENV_VAR, "admin@test.com")
    admin_password = os.getenv(BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR, "admin123")
    
    # Set environment variables if not set
    if not os.getenv(BOOTSTRAP_ADMIN_EMAIL_ENV_VAR):
        os.environ[BOOTSTRAP_ADMIN_EMAIL_ENV_VAR] = admin_email
    if not os.getenv(BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR):
        os.environ[BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR] = admin_password
    
    # Sign in as admin
    response = test_client.post("/signin", json={
        "email": admin_email,
        "password": admin_password
    })
    
    if response.status_code == 200:
        return response.json()["token"]
    else:
        # If admin doesn't exist, it should be created automatically on startup
        # Try again (the app should have initialized by now)
        response = test_client.post("/signin", json={
            "email": admin_email,
            "password": admin_password
        })
        assert response.status_code == 200, f"Failed to sign in as admin: {response.text}"
        return response.json()["token"]


@pytest.fixture(scope="function")
def test_user_token(test_client: TestClient) -> str:
    """Create a test user and return authentication token."""
    import uuid
    # Create test user with unique email
    unique_email = f"testuser-{uuid.uuid4().hex[:8]}@example.com"
    user_data = {
        "email": unique_email,
        "password": "testpass123",
        "nickname": "TestUser"
    }
    
    # Sign up
    response = test_client.post("/signup", json=user_data)
    assert response.status_code == 200, f"Failed to create test user: {response.text}"
    
    # Sign in
    response = test_client.post("/signin", json={
        "email": user_data["email"],
        "password": user_data["password"]
    })
    assert response.status_code == 200, f"Failed to sign in test user: {response.text}"
    
    return response.json()["token"]
