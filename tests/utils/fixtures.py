"""
Common test data fixtures and utilities.
"""
from typing import Dict, Any


class TestDataFixtures:
    """Common test data for use across tests."""
    
    @staticmethod
    def user_signup_data(email: str = "test@example.com", 
                        password: str = "testpass123",
                        nickname: str = "TestUser") -> Dict[str, str]:
        """Generate user signup data."""
        return {
            "email": email,
            "password": password,
            "nickname": nickname
        }
    
    @staticmethod
    def user_signin_data(email: str = "test@example.com",
                        password: str = "testpass123") -> Dict[str, str]:
        """Generate user signin data."""
        return {
            "email": email,
            "password": password
        }
    
    @staticmethod
    def location_update_data(latitude: float = 59.9139,
                           longitude: float = 10.7522,
                           altitude: float = 100.0,
                           speed: float = 5.0,
                           battery: int = 85,
                           accuracy: float = 10.0) -> Dict[str, Any]:
        """Generate location update data (Oslo coordinates by default)."""
        return {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "speed": speed,
            "battery": battery,
            "accuracy": accuracy
        }
    
    @staticmethod
    def device_data(imei: str = "123456789012345",
                   name: str = "Test Device") -> Dict[str, str]:
        """Generate device data."""
        return {
            "imei": imei,
            "name": name
        }
    
    @staticmethod
    def friend_request_data(email: str = "friend@example.com") -> Dict[str, str]:
        """Generate friend request data."""
        return {
            "email": email
        }
    
    @staticmethod
    def group_data(name: str = "Test Group",
                  description: str = "A test group") -> Dict[str, str]:
        """Generate group creation data."""
        return {
            "name": name,
            "description": description
        }
    
    @staticmethod
    def device_share_data(email: str = "friend@example.com") -> Dict[str, str]:
        """Generate device share data."""
        return {
            "email": email
        }


class TestAssertions:
    """Common assertion helpers for tests."""
    
    @staticmethod
    def assert_user_response(response_data: Dict[str, Any],
                           expected_email: str,
                           expected_nickname: str):
        """Assert user response structure and content."""
        assert "uuid" in response_data
        assert "token" in response_data
        assert response_data["email"] == expected_email
        assert response_data["nickname"] == expected_nickname
        
    @staticmethod
    def assert_auth_response(response_data: Dict[str, Any]):
        """Assert authentication response structure."""
        assert "token" in response_data  # API returns 'token' not 'access_token'
        assert "email" in response_data
        assert "uuid" in response_data
        
    @staticmethod
    def assert_location_response(response_data: Dict[str, Any],
                               expected_latitude: float,
                               expected_longitude: float):
        """Assert location response structure and content."""
        assert "latitude" in response_data
        assert "longitude" in response_data
        assert abs(response_data["latitude"] - expected_latitude) < 0.0001
        assert abs(response_data["longitude"] - expected_longitude) < 0.0001
        assert "timestamp" in response_data
        
    @staticmethod
    def assert_device_response(response_data: Dict[str, Any],
                             expected_imei: str,
                             expected_name: str):
        """Assert device response structure and content."""
        assert "imei" in response_data
        assert "name" in response_data
        assert response_data["imei"] == expected_imei
        assert response_data["name"] == expected_name
        assert "created_at" in response_data
        
    @staticmethod
    def assert_websocket_message(message: Dict[str, Any],
                               expected_type: str):
        """Assert WebSocket message structure."""
        assert "type" in message
        assert message["type"] == expected_type
        assert "data" in message
