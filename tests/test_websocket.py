"""
End-to-end tests for WebSocket functionality.
"""
import pytest
from tests.utils.fixtures import TestDataFixtures, TestAssertions
from fastapi.testclient import TestClient


class TestWebSocket:
    """Test WebSocket functionality."""
    
    @pytest.mark.timeout(5)
    def test_websocket_connection_with_valid_token(self, test_client: TestClient, test_user_token: str):
        """Test WebSocket connection with valid authentication token."""
        with test_client.websocket_connect(f'/ws?token={test_user_token}'):
            assert True
    
    @pytest.mark.timeout(5)
    def test_websocket_connection_without_token(self, test_client: TestClient):
        """Test WebSocket connection without authentication token fails."""
        with pytest.raises(Exception):
            with test_client.websocket_connect('/ws'):
                assert True

    @pytest.mark.timeout(5)
    def test_websocket_friend_user_location_update_broadcast(self, test_client: TestClient):
        """Test location update broadcasting between users."""
      
        alice_data = {
            "email": 'alice@example.com',
            "password": "testpass123",
            "nickname": "TestUser"
        }
        test_client.post("/signup", json=alice_data)
        alice_signin_response = test_client.post("/signin", json={
            "email": alice_data["email"],
            "password": alice_data["password"]
        })
        alice_token = alice_signin_response.json()["token"]


        bob_data = {
            "email": 'bob@example.com',
            "password": "testpass123",
            "nickname": "TestUser"
        }
        test_client.post("/signup", json=bob_data)
        bob_signin_response = test_client.post("/signin", json={
            "email": bob_data["email"],
            "password": bob_data["password"]
        })
        bob_token = bob_signin_response.json()["token"]

        assert test_client.post("/friends", json={'email': bob_data["email"]}, headers={"Authorization": f"Bearer {alice_token}"}).status_code == 200

        
        bobs_friends = test_client.get(f"/friends", headers={"Authorization": f"Bearer {bob_token}"}).json()
        alice_uuid = bobs_friends[0]['uuid']

        assert test_client.post(f"/friends/{alice_uuid}/accept", json={'email': bob_data["email"]}, headers={"Authorization": f"Bearer {bob_token}"}).status_code == 200

        with test_client.websocket_connect(f'/ws?token={alice_token}') as alice_ws, test_client.websocket_connect(f'/ws?token={bob_token}') as bob_ws:
           
            # Friend1 sends location update
            location_data = TestDataFixtures.location_update_data(
                latitude=59.9139,
                longitude=10.7522
            )
            message = {"type":"user_location", "data": location_data}
            alice_ws.send_json(message)
            
            message = bob_ws.receive_json()
            TestAssertions.assert_websocket_message(message, "user_locations")
            
            # Verify location data
            assert "data" in message
            data = message["data"]
            assert len(data) == 1
            TestAssertions.assert_location_response(
                data[0], 
                location_data["latitude"], 
                location_data["longitude"]
            )


    @pytest.mark.timeout(5)
    def test_websocket_friend_device_location_update_broadcast(self, test_client: TestClient):
        """Test location update broadcasting between users."""
        alice_data = {
            "email": 'alice@example.com',
            "password": "testpass123",
            "nickname": "TestUser"
        }
        test_client.post("/signup", json=alice_data)
        alice_signin_response = test_client.post("/signin", json={
            "email": alice_data["email"],
            "password": alice_data["password"]
        })
        alice_token = alice_signin_response.json()["token"]

        # Create a device
        headers = {"Authorization": f"Bearer {alice_token}"}
        alice_device_data = TestDataFixtures.device_data(
            imei="999888777666555",
            name="Test Dog Tracker"
        )
        device_response = test_client.post("/devices", json=alice_device_data, headers=headers)
        assert device_response.status_code == 200

        bob_data = {
            "email": 'bob@example.com',
            "password": "testpass123",
            "nickname": "TestUser"
        }
        test_client.post("/signup", json=bob_data)
        bob_signin_response = test_client.post("/signin", json={
            "email": bob_data["email"],
            "password": bob_data["password"]
        })
        bob_token = bob_signin_response.json()["token"]

        assert test_client.post("/friends", json={'email': bob_data["email"]}, headers={"Authorization": f"Bearer {alice_token}"}).status_code == 200

        
        bobs_friends = test_client.get(f"/friends", headers={"Authorization": f"Bearer {bob_token}"}).json()
        alice_uuid = bobs_friends[0]['uuid']

        assert test_client.post(f"/friends/{alice_uuid}/accept", json={'email': bob_data["email"]}, headers={"Authorization": f"Bearer {bob_token}"}).status_code == 200

        with test_client.websocket_connect(f'/ws?token={alice_token}') as alice_ws, test_client.websocket_connect(f'/ws?token={bob_token}') as bob_ws:
            # initial_data_message = bob_ws.receive_json() 
            # TestAssertions.assert_websocket_message(initial_data_message, "device_locations")
            # Send device location update
            location_data = TestDataFixtures.location_update_data(
                latitude=60.1699,
                longitude=24.9384
            )
            location_data['imei'] = alice_device_data['imei']
            location_update_msg = {"type":"device_location", "data": location_data}
            alice_ws.send_json(location_update_msg)
            
            # Friend should receive device location update via WebSocket
            message = bob_ws.receive_json()
            TestAssertions.assert_websocket_message(message, "device_locations")
            
            # Verify device location data
            assert "data" in message
            data = message["data"][0]
            assert "device_id" in data
            assert data["device_id"] == alice_device_data["imei"]
            assert "type" in data
            assert data["type"] == 'friend'
            TestAssertions.assert_location_response(
                data,
                location_data["latitude"],
                location_data["longitude"]
            )


    @pytest.mark.timeout(5)
    def test_websocket_device_location_sharing(self, test_client: TestClient, test_user_token: str):
        """Test device location sharing via WebSocket."""
        headers = {"Authorization": f"Bearer {test_user_token}"}

        # Create a device
        device_data = TestDataFixtures.device_data(
            imei="999888777666555",
            name="Test Dog Tracker"
        )
        device_response = test_client.post("/devices", json=device_data, headers=headers)
        assert device_response.status_code == 200
        
        # Create another user to share with
        friend_data = TestDataFixtures.user_signup_data(
            email="devicefriend@example.com",
            nickname="DeviceFriend"
        )
        test_client.post("/signup", json=friend_data)
        friend_signin = test_client.post("/signin", json={
            "email": friend_data["email"],
            "password": friend_data["password"]
        })
        friend_token = friend_signin.json()["token"]
        
        # Share device with friend
        share_response = test_client.post(
            f"/devices/{device_data['imei']}/share",
            json={"email": friend_data["email"]},
            headers=headers
        )
        assert share_response.status_code == 200
        
        with test_client.websocket_connect(f'/ws?token={friend_token}') as ws_friend, test_client.websocket_connect(f'/ws?token={test_user_token}') as ws:
            initial_data_message = ws_friend.receive_json() 
            TestAssertions.assert_websocket_message(initial_data_message, "device_locations")
            assert "data" in initial_data_message
            data = initial_data_message["data"][0]
            assert "device_id" in data
            assert data["device_id"] == device_data["imei"]
            assert data["latitude"] == None
            assert data["longitude"] == None
            
            # Send device location update
            location_data = TestDataFixtures.location_update_data(
                latitude=60.1699,
                longitude=24.9384
            )
            location_data['imei'] = device_data['imei']
            location_update_msg = {"type":"device_location", "data": location_data}
            ws.send_json(location_update_msg)
            
            # Friend should receive device location update via WebSocket
            message = ws_friend.receive_json()
            TestAssertions.assert_websocket_message(message, "device_locations")
            
            # Verify device location data
            assert "data" in message
            data = message["data"][0]
            assert "device_id" in data
            assert data["device_id"] == device_data["imei"]
            assert "type" in data
            assert data["type"] == 'shared'
            TestAssertions.assert_location_response(
                data,
                location_data["latitude"],
                location_data["longitude"]
            )
