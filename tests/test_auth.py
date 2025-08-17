"""
End-to-end tests for authentication endpoints.
"""
from fastapi.testclient import TestClient
from tests.utils.fixtures import TestDataFixtures, TestAssertions


class TestAuthentication:
    """Test authentication functionality."""
    
    def test_user_signup_success(self, test_client: TestClient):
        """Test successful user signup."""
        import uuid
        unique_email = f"newuser-{uuid.uuid4().hex[:8]}@example.com"
        user_data = TestDataFixtures.user_signup_data(
            email=unique_email,
            nickname="NewUser"
        )
        
        response = test_client.post("/signup", json=user_data)
        
        assert response.status_code == 200
        response_data = response.json()
        TestAssertions.assert_user_response(
            response_data, 
            user_data["email"], 
            user_data["nickname"]
        )
    
    def test_user_signup_duplicate_email(self, test_client: TestClient):
        """Test signup with duplicate email fails."""
        import uuid
        unique_email = f"duplicate-{uuid.uuid4().hex[:8]}@example.com"
        user_data = TestDataFixtures.user_signup_data(email=unique_email)
        
        # First signup should succeed
        response = test_client.post("/signup", json=user_data)
        assert response.status_code == 200
        
        # Second signup with same email should fail
        response = test_client.post("/signup", json=user_data)
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()
    
    def test_user_signin_success(self, test_client: TestClient):
        """Test successful user signin."""
        # Create user first
        user_data = TestDataFixtures.user_signup_data(email="signin@example.com")
        test_client.post("/signup", json=user_data)
        
        # Sign in
        signin_data = TestDataFixtures.user_signin_data(
            email=user_data["email"],
            password=user_data["password"]
        )
        response = test_client.post("/signin", json=signin_data)
        
        assert response.status_code == 200
        response_data = response.json()
        TestAssertions.assert_auth_response(response_data)
    
    def test_user_signin_invalid_credentials(self, test_client: TestClient):
        """Test signin with invalid credentials fails."""
        signin_data = TestDataFixtures.user_signin_data(
            email="nonexistent@example.com",
            password="wrongpassword"
        )
        response = test_client.post("/signin", json=signin_data)
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    def test_protected_endpoint_without_token(self, test_client: TestClient):
        """Test accessing protected endpoint without token fails."""
        # Try to access friends endpoint which requires authentication
        response = test_client.get("/friends")
        assert response.status_code == 403  # API returns 403 for missing auth
    
    def test_protected_endpoint_with_token(self, test_client: TestClient, test_user_token: str):
        """Test accessing protected endpoint with valid token succeeds."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        response = test_client.get("/friends", headers=headers)
        assert response.status_code == 200
        
        # Should return a list (even if empty)
        response_data = response.json()
        assert isinstance(response_data, list)
    
    def test_protected_endpoint_with_invalid_token(self, test_client: TestClient):
        """Test accessing protected endpoint with invalid token fails."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = test_client.get("/friends", headers=headers)
        assert response.status_code == 401  # API returns 401 for invalid token
