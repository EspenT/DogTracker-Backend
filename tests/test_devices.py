"""
End-to-end tests for device management functionality.
"""
from tests.utils.fixtures import TestDataFixtures, TestAssertions
from fastapi.testclient import TestClient

class TestDeviceManagement:
    """Test device management functionality."""
    
    def test_add_device_success(self, test_client: TestClient, test_user_token: str):
        """Test successful device addition."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        device_data = TestDataFixtures.device_data(
            imei="123456789012345",
            name="My Dog Tracker"
        )
        
        response = test_client.post("/devices", headers=headers, json=device_data)
        
        assert response.status_code == 200

    def test_update_device_success(self, test_client: TestClient, test_user_token: str):
        """Test successful device addition."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        device_data = TestDataFixtures.device_data(
            imei="123456789012345",
            name="My Dog Tracker"
        )
        
        test_client.post("/devices", headers=headers, json=device_data)

        put_response = test_client.put(f"/devices/{device_data['imei']}", headers=headers, json={'name':'New Device name'})
        
        assert put_response.status_code == 200

        get_response = test_client.get("/devices", headers=headers)  

        assert get_response.status_code == 200
        devices = get_response.json()
        assert isinstance(devices, list)
        assert len(devices) >= 1
        assert devices[0]['name'] == 'New Device name'

    def test_add_duplicate_device_fails(self, test_client: TestClient, test_user_token: str):
        """Test adding duplicate device fails."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        
        device_data = TestDataFixtures.device_data(imei="duplicate123456789")
        
        # First addition should succeed
        response = test_client.post("/devices", headers=headers, json=device_data)
        assert response.status_code == 200
        
        # Second addition should fail
        response = test_client.post("/devices", headers=headers, json=device_data)
        assert response.status_code == 400
    
    def test_get_user_devices(self, test_client: TestClient, test_user_token: str):
        """Test retrieving user's devices."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        
        # Add a device first
        device_data = TestDataFixtures.device_data(
            imei="getdevices123456789",
            name="Test Device for Get"
        )
        test_client.post("/devices", headers=headers, json=device_data)
        
        # Get devices
        response = test_client.get("/devices", headers=headers)
        
        assert response.status_code == 200
        devices = response.json()
        assert isinstance(devices, list)
        assert len(devices) >= 1
        
        # Find our device
        our_device = next((d for d in devices if d["imei"] == device_data["imei"]), None)
        assert our_device is not None
        TestAssertions.assert_device_response(
            our_device,
            device_data["imei"],
            device_data["name"]
        )
    
    def test_share_device_with_user(self, test_client: TestClient, test_user_token: str):
        """Test sharing device with another user."""
        headers = {"Authorization": f"Bearer {test_user_token}"}
        
        # Create another user to share with
        friend_data = TestDataFixtures.user_signup_data(
            email="deviceshare@example.com",
            nickname="DeviceShareFriend"
        )
        test_client.post("/signup", json=friend_data)
        

        # Add a device
        device_data = TestDataFixtures.device_data(
            imei="123456789123",
            name="Shared Device"
        )
        test_client.post("/devices", headers=headers, json=device_data)

        # Share device
        share_data = TestDataFixtures.device_share_data(email=friend_data["email"])
        response = test_client.post(
            f"/devices/{device_data['imei']}/share",
            headers=headers,
            json=share_data
        )

        assert response.status_code == 200
        response_data = response.json()
        assert "message" in response_data
        assert "shared" in response_data["message"].lower()
    
