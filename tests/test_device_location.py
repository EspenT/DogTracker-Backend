"""
End-to-end tests for device location history functionality.
"""
import pytest
from tests.utils.fixtures import TestDataFixtures
from typing import List
from fastapi.testclient import TestClient
from typing import Dict, Any

def add_device_history(test_client: TestClient, user_token: str, imei: str):
    # Create a device
    device_data = TestDataFixtures.device_data(
        imei=imei,
        name="Test Dog Tracker"
    )
    device_response = test_client.post("/devices", json=device_data, headers={"Authorization": f"Bearer {user_token}"})
    assert device_response.status_code == 200

    # send some location updates
    with test_client.websocket_connect(f'/ws?token={user_token}') as ws:
        location_data = TestDataFixtures.location_update_data(
            latitude=60,
            longitude=24,
            speed=12,
            battery=30,
            imei=imei
        )
        ws.send_json({"type":"device_location", "data": location_data})

        location_data = TestDataFixtures.location_update_data(
            latitude=61,
            longitude=25,
            speed=10,
            battery=29,
            imei=imei
        )
        ws.send_json({"type":"device_location", "data": location_data})

        location_data = TestDataFixtures.location_update_data(
            latitude=62,
            longitude=26,
            speed=11,
            battery=28,
            imei=imei
        )
        ws.send_json({"type":"device_location", "data": location_data})


@pytest.fixture(scope="function")
def test_user_with_one_device(test_client: TestClient, test_user_token: str) -> tuple[str, str]:
    """Create a test user with a device and return authentication token and imei of device."""

    add_device_history(test_client, test_user_token,  "495886777666555")
    return (test_user_token, "495886777666555")

@pytest.fixture(scope="function")
def test_user_with_two_devices(test_client: TestClient) -> tuple[str, str, str]:
    """  """
    import uuid
    # Create test user with unique email
    unique_email = f"testuser-{uuid.uuid4().hex[:8]}@example.com"
    user_data = {
        "email": unique_email,
        "password": "testpass123",
        "nickname": "TestUser"
    }
    response = test_client.post("/signup", json=user_data)
    response = test_client.post("/signin", json={
        "email": user_data["email"],
        "password": user_data["password"]
    })
    test_user_token = response.json()['token']

    # Create a device
    add_device_history(test_client, test_user_token,  "495886777666555")
    add_device_history(test_client, test_user_token,  "777777777776555")
    return (test_user_token, "495886777666555", "777777777776555")

class TestDeviceLocation:
    @pytest.mark.timeout(2)
    def test_get_device_locations_is_protected(self, test_client: TestClient):
        response = test_client.get(f"/device_locations")
        assert response.status_code == 403

    @pytest.mark.timeout(2)
    def test_get_device_locations_returns_all_previous_locations_of_users_owned_device(self, test_client: TestClient, test_user_with_one_device: tuple[str, str]):
        (user_token, imei) = test_user_with_one_device
    
        headers = {"Authorization": f"Bearer {user_token}"}
        
        response = test_client.get(f"/device_locations", headers=headers)
        assert response.status_code == 200
        all_device_locations: List[dict] = response.json()
        assert len(all_device_locations) == 3
        assert all(dev_loc['device_id'] == imei for dev_loc in all_device_locations)
        assert [int(dev_loc['latitude']) for dev_loc in all_device_locations] == [60, 61, 62]
        assert [int(dev_loc['longitude']) for dev_loc in all_device_locations] == [24, 25, 26]
        assert [int(dev_loc['speed']) for dev_loc in all_device_locations] == [12, 10, 11]
        assert [int(dev_loc['battery']) for dev_loc in all_device_locations] == [30, 29, 28]

    @pytest.mark.timeout(2)
    def test_get_device_locations_returns_all_previous_locations_of_users_owned_devices(self, test_client: TestClient, test_user_with_two_devices: tuple[str, str, str]):
        (user_token, imei, snd_imei) = test_user_with_two_devices
    
        headers = {"Authorization": f"Bearer {user_token}"}
        
        response = test_client.get(f"/device_locations", headers=headers)
        assert response.status_code == 200
        all_device_locations: List[dict] = response.json()
        assert len(all_device_locations) == 6
        assert [dev_loc['device_id'] for dev_loc in all_device_locations] == [imei] * 3 + [snd_imei] * 3

    @pytest.mark.timeout(2)
    def test_get_device_locations_returns_all_previous_locations_of_devices_shared_with_user(self, test_client: TestClient, signed_in_user: Dict[str, Any], test_user_with_two_devices: tuple[str, str, str]):
        (sharer_token, imei, snd_imei) = test_user_with_two_devices
      
        for imei_to_share in [imei, snd_imei]:
            test_client.post(
                f"/devices/{imei_to_share}/share",
                json={"email": signed_in_user["email"]},
                headers={"Authorization": f"Bearer {sharer_token}"}
            )
    
        response = test_client.get(f"/device_locations", headers={"Authorization": f"Bearer {signed_in_user['token']}"})
        assert response.status_code == 200
        all_device_locations: List[dict] = response.json()
        assert len(all_device_locations) == 6
        assert [dev_loc['device_id'] for dev_loc in all_device_locations] == [imei] * 3 + [snd_imei] * 3

    @pytest.mark.timeout(2)
    def test_get_device_locations_results_are_sorted_by_imei(self, test_client: TestClient, test_user_with_two_devices: tuple[str, str, str]):
        (user_token, imei, snd_imei) = test_user_with_two_devices

        headers = {"Authorization": f"Bearer {user_token}"}

        # add extra locations for both device in different order
        with test_client.websocket_connect(f'/ws?token={user_token}') as ws:
            location_data = TestDataFixtures.location_update_data(
                latitude=60,
                longitude=24,
                speed=12,
                battery=30,
                imei=imei
            )
            ws.send_json({"type":"device_location", "data": location_data})
            location_data = TestDataFixtures.location_update_data(
                latitude=60,
                longitude=24,
                speed=12,
                battery=30,
                imei=snd_imei
            )
            ws.send_json({"type":"device_location", "data": location_data})

        response = test_client.get(f"/device_locations", headers=headers)
        assert response.status_code == 200
        all_device_locations: List[dict] = response.json()
        assert len(all_device_locations) == 8
        assert [dev_loc['device_id'] for dev_loc in all_device_locations] == [imei] * 4 + [snd_imei] * 4
