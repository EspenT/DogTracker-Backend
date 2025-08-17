#!/usr/bin/env python3
"""
Complete Dog Tracker Backend Server
This is the LATEST and COMPLETE version - use this file!

Features:
- WebSocket real-time communication
- User authentication (JWT)
- Friends management
- Groups management
- Device management and sharing
- Location tracking and broadcasting
- SQLite database storage
"""

from enum import Enum 
import asyncio
import json
import sqlite3
import hashlib
from fastapi.responses import StreamingResponse
import jwt
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

from database_manager import DatabaseManager

from dotenv import load_dotenv
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import uvicorn

# JWT Configuration
JWT_SECRET = "your-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

ROLE_ADMIN = 'A'
ROLE_USER = 'U'


BOOTSTRAP_ADMIN_EMAIL_ENV_VAR = 'BOOTSTRAP_ADMIN_EMAIL'
BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR = 'BOOTSTRAP_ADMIN_PASSWORD'
DB_PATH_ENV_VAR = 'DB_PATH'
SERVER_HOST_ENV_VAR = 'SERVER_HOST'
SERVER_PORT_ENV_VAR = 'SERVER_PORT'

PROD_ENV_PATH = "prod.env"

LOG_DIR_PATH = 'logs'
LOG_FILE_PATH = f'{LOG_DIR_PATH}/dogtracker_backend.log'


def create_and_configure_logger():
    os.makedirs(LOG_DIR_PATH, exist_ok=True)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    max_log_size_in_mb = 10
    file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=max_log_size_in_mb*1000000, backupCount=3)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s: %(name)s (%(levelname)s) %(message)s')

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

logger = create_and_configure_logger()

load_dotenv(dotenv_path=PROD_ENV_PATH)

if not os.getenv(BOOTSTRAP_ADMIN_EMAIL_ENV_VAR):
    logger.error(f"{BOOTSTRAP_ADMIN_EMAIL_ENV_VAR} not defined in {PROD_ENV_PATH}, exiting")
    exit(1)

if not os.getenv(BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR):
    logger.error(f"{BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR} not defined in {PROD_ENV_PATH}, exiting")
    exit(1)

# Security
security = HTTPBearer()

# Database manager will be initialized in startup event

db_manager = None

# Data Models
@dataclass
class User:
    uuid: str
    email: str
    password_hash: str
    nickname: str
    created_at: datetime
    role: str
    last_seen: Optional[datetime] = None

@dataclass
class UserLocation:
    uuid: str
    email: str
    nickname: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    speed: Optional[float]
    battery: Optional[int]
    accuracy: Optional[float]
    timestamp: datetime

@dataclass
class Device:
    imei: str
    owner_uuid: str
    name: str
    created_at: datetime
    last_seen: Optional[datetime] = None

class DeviceLocationType(Enum):
    OWN = 'own'
    SHARED = 'shared'
    FRIEND = 'friend'
    GROUP_MEMBER = 'group_member'

@dataclass
class DeviceLocation:
    device_id: str
    owner_uuid: str
    owner_email: str
    owner_nickname: str
    device_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    speed: Optional[float]
    battery: Optional[int]
    battery_mv: Optional[int]
    bark: Optional[int]
    satellites: Optional[int]
    lte_signal: Optional[int]
    lora_rssi: Optional[int]
    connection_type: Optional[str]
    time: Optional[str]
    timestamp: datetime
    type: DeviceLocationType  # 'own', 'shared', 'friend', 'group_member'

@dataclass
class Friend:
    uuid: str
    email: str
    nickname: str
    status: str  # 'pending', 'accepted', 'blocked'
    created_at: datetime
    request_sent_by: str

@dataclass
class Group:
    id: str
    name: str
    description: Optional[str]
    owner_id: str
    member_ids: List[str]
    created_at: datetime

@dataclass
class DeviceShare:
    device_imei: str
    owner_uuid: str
    shared_with_uuid: str
    created_at: datetime

# Pydantic Models for API
class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str

class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    speed: Optional[float] = None
    battery: Optional[int] = None
    accuracy: Optional[float] = None

class AddFriendRequest(BaseModel):
    email: EmailStr

class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None

class AddGroupMemberRequest(BaseModel):
    email: EmailStr

class AddDeviceRequest(BaseModel):
    imei: str
    name: str

class UpdateDeviceRequest(BaseModel):
    name: str

class ShareDeviceRequest(BaseModel):
    email: EmailStr

# Connection Manager for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_uuid -> websocket

    async def connect(self, websocket: WebSocket, user_uuid: str):
        await websocket.accept()
        self.active_connections[user_uuid] = websocket
        logger.info(f"User {user_uuid} connected via WebSocket")

    def disconnect(self, user_uuid: str):
        if user_uuid in self.active_connections:
            del self.active_connections[user_uuid]
            logger.info(f"User {user_uuid} disconnected from WebSocket")

    async def send_personal_message(self, message: dict, user_uuid: str):
        if user_uuid in self.active_connections:
            try:
                await self.active_connections[user_uuid].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {user_uuid}: {e}")
                self.disconnect(user_uuid)

    async def broadcast_to_friends(self, message: dict, user_uuid: str, db: DatabaseManager):
        """Broadcast message to all friends of the user."""
        friends = self.get_user_friends(user_uuid, db)
        for friend in friends:
            if friend.status == 'accepted':
                await self.send_personal_message(message, friend.uuid)

    async def broadcast_to_group_members(self, message: dict, group_id: str, db: DatabaseManager):
        """Broadcast message to all members of a group."""
        members = self.get_group_members(group_id, db)
        for member_uuid in members:
            await self.send_personal_message(message, member_uuid)

    def get_user_friends(self, user_uuid: str, db: DatabaseManager) -> List[Friend]:
        """Get all accepted and pending friends of a user."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.uuid, u.email, u.nickname, f.status, f.created_at, f.user_uuid
                FROM friends f
                JOIN users u ON f.friend_uuid = u.uuid
                WHERE f.user_uuid = ?
                UNION
                SELECT u.uuid, u.email, u.nickname, f.status, f.created_at, f.user_uuid
                FROM friends f
                JOIN users u ON f.user_uuid = u.uuid
                WHERE f.friend_uuid = ? AND (f.status = 'accepted' OR f.status = 'pending')
            ''', (user_uuid, user_uuid))
            
            friends = []
            for row in cursor.fetchall():
                friends.append(Friend(
                    uuid=row[0],
                    email=row[1],
                    nickname=row[2],
                    status=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    request_sent_by=row[5]
                ))
            return friends

    def get_group_members(self, group_id: str, db: DatabaseManager) -> List[str]:
        """Get all member UUIDs of a group."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_uuid FROM group_members WHERE group_id = ?', (group_id,))
            return [row[0] for row in cursor.fetchall()]

# Initialize managers
connection_manager = ConnectionManager()


# Authentication utilities
def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash

def create_jwt_token(user_uuid: str) -> str:
    """Create a JWT token for a user."""
    payload = {
        'user_uuid': user_uuid,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str) -> Optional[str]:
    """Decode a JWT token and return the user UUID."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('user_uuid')
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid JWT token")
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Get the current user from JWT token."""
    user_uuid = decode_jwt_token(credentials.credentials)
    if not user_uuid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_uuid

async def get_current_user_if_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Get the current user from JWT token, but only if the user is an admin."""
    user_uuid = decode_jwt_token(credentials.credentials)
    if not user_uuid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        # Check if user is admin
        cursor.execute('SELECT uuid FROM users WHERE uuid = ? AND role = ?', (user_uuid, ROLE_ADMIN))
        if cursor.rowcount == 0:
            raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have admin rights")

        return user_uuid

# Generate UUID
import uuid
def generate_uuid() -> str:
    return str(uuid.uuid4())

def create_bootstrap_admin():
    """Create bootstrap admin if no admin exists"""

    admin_email = os.getenv(BOOTSTRAP_ADMIN_EMAIL_ENV_VAR)
    if not admin_email:
        logger.error(f"{BOOTSTRAP_ADMIN_EMAIL_ENV_VAR} not defined in {PROD_ENV_PATH}")
        exit(1)

    admin_password = os.getenv(BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR)
    if not admin_password:
        logger.error(f"{BOOTSTRAP_ADMIN_PASSWORD_ENV_VAR} not defined in {PROD_ENV_PATH}")
        exit(1)

    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Check if any admin already exists
            cursor.execute('SELECT uuid FROM users WHERE role = ?', ROLE_ADMIN)
            if cursor.fetchone():
                logger.info("Admin user already exists. skipping bootstrap")
                return

            # Create new user
            user_uuid = generate_uuid()
            password_hash = hash_password(admin_password)

            cursor.execute('''
                INSERT INTO users (uuid, email, password_hash, nickname, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_uuid, admin_email, password_hash, 'bootstrap_admin', ROLE_ADMIN))

            logger.info(f"Creating bootstrap admin user")
            conn.commit()

    except Exception as e:
        logger.error(f"Error creating bootstrap admin: {e}")
        raise

def on_startup():
    global db_manager
    logger.info("Dog Tracker Backend starting up...")
   
    # Initialize database manager with current environment configuration
    db_path = os.getenv(DB_PATH_ENV_VAR, "dog_tracker.db")
    db_manager = DatabaseManager(logger, db_path)
    logger.info("Database initialized")
    
    # Create bootstrap admin after database is initialized
    try:
        create_bootstrap_admin()
    except Exception as e:
        logger.error(f"Failed to create bootstrap admin: {e}")
        exit(1)
    
    logger.info("WebSocket manager ready")
    logger.info("Backend server ready!")

# Shutdown event
def on_shutdown():
    logger.info("Dog Tracker Backend shutting down...")

@asynccontextmanager
async def lifespan(app: FastAPI):
    on_startup()
    yield
    on_shutdown()

# FastAPI app
app = FastAPI(title="Dog Tracker Backend", version="1.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Authentication endpoints
@app.post("/signup")
async def sign_up(request: SignUpRequest):
    """Register a new user."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute('SELECT uuid FROM users WHERE email = ?', (request.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")
            
            # Create new user
            user_uuid = generate_uuid()
            password_hash = hash_password(request.password)
            
            cursor.execute('''
                INSERT INTO users (uuid, email, password_hash, nickname)
                VALUES (?, ?, ?, ?)
            ''', (user_uuid, request.email, password_hash, request.nickname))
            
            conn.commit()
            
            # Create JWT token
            token = create_jwt_token(user_uuid)
            
            logger.info(f"New user registered: {request.email}")
            return {
                "token": token,
                "uuid": user_uuid,
                "email": request.email,
                "nickname": request.nickname
            }
            
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign up error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/signin")
async def sign_in(request: SignInRequest):
    """Sign in an existing user."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT uuid, password_hash, nickname FROM users WHERE email = ?
            ''', (request.email,))
            
            user = cursor.fetchone()
            if not user or not verify_password(request.password, user[1]):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            user_uuid, _, nickname = user
            
            # Update last seen
            cursor.execute('UPDATE users SET last_seen = ? WHERE uuid = ?', 
                         (datetime.now(), user_uuid))
            conn.commit()
            
            # Create JWT token
            token = create_jwt_token(user_uuid)
            
            logger.info(f"User signed in: {request.email}")
            return {
                "token": token,
                "uuid": user_uuid,
                "email": request.email,
                "nickname": nickname
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign in error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Friends endpoints
@app.get("/friends")
async def get_friends(current_user: str = Depends(get_current_user)):
    """Get user's friends list."""
    try:
        friends = connection_manager.get_user_friends(current_user, db_manager)
        return [asdict(friend) for friend in friends]
    except Exception as e:
        logger.error(f"Get friends error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/friends")
async def add_friend(request: AddFriendRequest, current_user: str = Depends(get_current_user)):
    """Send a friend request."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Find the friend by email
            cursor.execute('SELECT uuid FROM users WHERE email = ?', (request.email,))
            friend = cursor.fetchone()
            if not friend:
                raise HTTPException(status_code=404, detail="User not found")
            
            friend_uuid = friend[0]
            
            if friend_uuid == current_user:
                raise HTTPException(status_code=400, detail="Cannot add yourself as friend")
            
            # Check if friendship already exists
            cursor.execute('''
                SELECT status FROM friends 
                WHERE (user_uuid = ? AND friend_uuid = ?) OR (user_uuid = ? AND friend_uuid = ?)
            ''', (current_user, friend_uuid, friend_uuid, current_user))
            
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Friend relationship already exists")
            
            # Add friend request
            cursor.execute('''
                INSERT INTO friends (user_uuid, friend_uuid, status)
                VALUES (?, ?, 'pending')
            ''', (current_user, friend_uuid))
            
            conn.commit()
            
            # Notify the friend via WebSocket
            await connection_manager.send_personal_message({
                "type": "friend_request",
                "data": {"from": current_user, "email": request.email}
            }, friend_uuid)
            
            return {"message": "Friend request sent"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add friend error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/friends/{friend_uuid}/accept")
async def accept_friend_request(friend_uuid: str, current_user: str = Depends(get_current_user)):
    """Accept a friend request."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Update the friend request status
            cursor.execute('''
                UPDATE friends SET status = 'accepted' 
                WHERE user_uuid = ? AND friend_uuid = ? AND status = 'pending'
            ''', (friend_uuid, current_user))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Friend request not found")
            
            conn.commit()
            
            # Notify the requester via WebSocket
            await connection_manager.send_personal_message({
                "type": "friend_accepted",
                "data": {"by": current_user}
            }, friend_uuid)
            
            return {"message": "Friend request accepted"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Accept friend error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/friends/{friend_uuid}")
async def remove_friend(friend_uuid: str, current_user: str = Depends(get_current_user)):
    """Remove a friend."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Remove the friendship (both directions)
            cursor.execute('''
                DELETE FROM friends 
                WHERE (user_uuid = ? AND friend_uuid = ?) OR (user_uuid = ? AND friend_uuid = ?)
            ''', (current_user, friend_uuid, friend_uuid, current_user))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Friend relationship not found")
            
            conn.commit()
            
            return {"message": "Friend removed"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove friend error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Groups endpoints
@app.get("/groups")
async def get_groups(current_user: str = Depends(get_current_user)):
    """Get user's groups."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT g.id, g.name, g.description, g.owner_id, g.created_at
                FROM groups g
                LEFT JOIN group_members gm ON g.id = gm.group_id
                WHERE g.owner_id = ? OR gm.user_uuid = ?
                GROUP BY g.id
            ''', (current_user, current_user))
            
            groups = []
            for row in cursor.fetchall():
                group_id = row[0]
                
                # Get member IDs
                cursor.execute('SELECT user_uuid FROM group_members WHERE group_id = ?', (group_id,))
                member_ids = [member[0] for member in cursor.fetchall()]
                
                groups.append({
                    'id': group_id,
                    'name': row[1],
                    'description': row[2],
                    'owner_id': row[3],
                    'member_ids': member_ids,
                    'created_at': row[4]
                })
            
            return groups
            
    except Exception as e:
        logger.error(f"Get groups error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/groups")
async def create_group(request: CreateGroupRequest, current_user: str = Depends(get_current_user)):
    """Create a new group."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            group_id = generate_uuid()
            
            cursor.execute('''
                INSERT INTO groups (id, name, description, owner_id)
                VALUES (?, ?, ?, ?)
            ''', (group_id, request.name, request.description, current_user))
            
            # Add owner as member
            cursor.execute('''
                INSERT INTO group_members (group_id, user_uuid)
                VALUES (?, ?)
            ''', (group_id, current_user))
            
            conn.commit()
            
            return {
                "id": group_id,
                "name": request.name,
                "description": request.description,
                "owner_id": current_user,
                "member_ids": [current_user],
                "created_at": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Create group error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/groups/{group_id}")
async def delete_group(group_id: str, current_user: str = Depends(get_current_user)):
    """Delete a group (owner only)."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user is the owner
            cursor.execute('SELECT owner_id FROM groups WHERE id = ?', (group_id,))
            group = cursor.fetchone()
            if not group:
                raise HTTPException(status_code=404, detail="Group not found")
            
            if group[0] != current_user:
                raise HTTPException(status_code=403, detail="Only group owner can delete the group")
            
            # Delete group members first
            cursor.execute('DELETE FROM group_members WHERE group_id = ?', (group_id,))
            
            # Delete the group
            cursor.execute('DELETE FROM groups WHERE id = ?', (group_id,))
            
            conn.commit()
            
            return {"message": "Group deleted"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete group error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/groups/{group_id}/members")
async def add_group_member(group_id: str, request: AddGroupMemberRequest, current_user: str = Depends(get_current_user)):
    """Add a member to a group."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user is the owner or member of the group
            cursor.execute('''
                SELECT g.owner_id FROM groups g
                LEFT JOIN group_members gm ON g.id = gm.group_id
                WHERE g.id = ? AND (g.owner_id = ? OR gm.user_uuid = ?)
            ''', (group_id, current_user, current_user))
            
            if not cursor.fetchone():
                raise HTTPException(status_code=403, detail="Not authorized to add members to this group")
            
            # Find user by email
            cursor.execute('SELECT uuid FROM users WHERE email = ?', (request.email,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            user_uuid = user[0]
            
            # Add member to group
            cursor.execute('''
                INSERT OR IGNORE INTO group_members (group_id, user_uuid)
                VALUES (?, ?)
            ''', (group_id, user_uuid))
            
            conn.commit()
            
            # Notify the new member via WebSocket
            await connection_manager.send_personal_message({
                "type": "group_invitation",
                "data": {"group_id": group_id, "by": current_user}
            }, user_uuid)
            
            return {"message": "Member added to group"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add group member error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/groups/{group_id}/members/{member_uuid}")
async def remove_group_member(group_id: str, member_uuid: str, current_user: str = Depends(get_current_user)):
    """Remove a member from a group."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user is the owner of the group or removing themselves
            cursor.execute('SELECT owner_id FROM groups WHERE id = ?', (group_id,))
            group = cursor.fetchone()
            if not group:
                raise HTTPException(status_code=404, detail="Group not found")
            
            if group[0] != current_user and member_uuid != current_user:
                raise HTTPException(status_code=403, detail="Not authorized to remove this member")
            
            # Remove member from group
            cursor.execute('''
                DELETE FROM group_members WHERE group_id = ? AND user_uuid = ?
            ''', (group_id, member_uuid))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Member not found in group")
            
            conn.commit()
            
            return {"message": "Member removed from group"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove group member error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Device management endpoints
@app.get("/devices")
async def get_devices(current_user: str = Depends(get_current_user)):
    """Get user's devices."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT imei, name, created_at, last_seen FROM devices WHERE owner_uuid = ?
            ''', (current_user,))
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    'imei': row[0],
                    'name': row[1],
                    'created_at': row[2],
                    'last_seen': row[3]
                })
            
            return devices
            
    except Exception as e:
        logger.error(f"Get devices error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/devices")
async def add_device(request: AddDeviceRequest, current_user: str = Depends(get_current_user)):
    """Add a new device."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if device already exists
            cursor.execute('SELECT owner_uuid FROM devices WHERE imei = ?', (request.imei,))
            existing = cursor.fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Device already registered")
            
            cursor.execute('''
                INSERT INTO devices (imei, owner_uuid, name)
                VALUES (?, ?, ?)
            ''', (request.imei, current_user, request.name))
            
            conn.commit()
            
            return {"message": "Device added successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add device error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/devices/{imei}")
async def update_device(imei: str, request: UpdateDeviceRequest, current_user: str = Depends(get_current_user)):
    """Update device name."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE devices SET name = ? WHERE imei = ? AND owner_uuid = ?
            ''', (request.name, imei, current_user))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Device not found")
            
            conn.commit()
            
            return {"message": "Device updated successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update device error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/devices/{imei}")
async def remove_device(imei: str, current_user: str = Depends(get_current_user)):
    """Remove a device."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Remove device shares first
            cursor.execute('DELETE FROM device_shares WHERE device_imei = ?', (imei,))
            
            # Remove device locations
            cursor.execute('DELETE FROM device_locations WHERE device_id = ?', (imei,))
            
            # Remove the device
            cursor.execute('DELETE FROM devices WHERE imei = ? AND owner_uuid = ?', (imei, current_user))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Device not found")
            
            conn.commit()
            
            return {"message": "Device removed successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove device error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/devices/{imei}/share")
async def share_device(imei: str, request: ShareDeviceRequest, current_user: str = Depends(get_current_user)):
    """Share a device with another user."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if device belongs to current user
            cursor.execute('SELECT name FROM devices WHERE imei = ? AND owner_uuid = ?', (imei, current_user))
            device = cursor.fetchone()
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
            
            # Find user by email
            cursor.execute('SELECT uuid FROM users WHERE email = ?', (request.email,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            shared_with_uuid = user[0]
            
            if shared_with_uuid == current_user:
                raise HTTPException(status_code=400, detail="Cannot share device with yourself")
            
            # Add device share
            cursor.execute('''
                INSERT OR REPLACE INTO device_shares (device_imei, owner_uuid, shared_with_uuid)
                VALUES (?, ?, ?)
            ''', (imei, current_user, shared_with_uuid))
            
            conn.commit()
            
            # Notify the user via WebSocket
            await connection_manager.send_personal_message({
                "type": "device_shared",
                "data": {"device_imei": imei, "device_name": device[0], "by": current_user}
            }, shared_with_uuid)
            
            return {"message": "Device shared successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Share device error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/devices/{imei}/share/{user_uuid}")
async def unshare_device(imei: str, user_uuid: str, current_user: str = Depends(get_current_user)):
    """Stop sharing a device with a user."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM device_shares 
                WHERE device_imei = ? AND owner_uuid = ? AND shared_with_uuid = ?
            ''', (imei, current_user, user_uuid))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Device share not found")
            
            conn.commit()
            
            return {"message": "Device unshared successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unshare device error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/admin/logs", response_class=StreamingResponse)
async def get_logs(_: str = Depends(get_current_user_if_admin)):
    """Get server logs"""
    def iterfile():
        with open(LOG_FILE_PATH, mode="rb") as file_like:
            yield from file_like

    return StreamingResponse(iterfile())

@app.get("/admin/users")
async def get_users(_: str = Depends(get_current_user_if_admin)):
    """Get all users"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT uuid, email, created_at, last_seen, role FROM users')

        users = []
        for row in cursor.fetchall():
            users.append({
                'uuid': row[0],
                'email': row[1],
                'created_at': row[2],
                'last_seen': row[3],
                'role': row[4],
            })
        return users

@app.get("/admin/devices")
async def get_all_devices(_: str = Depends(get_current_user_if_admin)):
    """Get all devices for all users."""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT d.imei, d.owner_uuid, d.name
            FROM devices d
        ''', )

        devices = []
        for row in cursor.fetchall():
            devices.append({
                'device_id': row[0],
                'owner_uuid': row[1],
                'device_name': row[2],
            })
        return devices

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """WebSocket endpoint for real-time communication."""
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return
    
    user_uuid = decode_jwt_token(token)
    if not user_uuid:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    await connection_manager.connect(websocket, user_uuid)
    
    try:
        # Send initial data
        await send_initial_data(user_uuid)
        
        while True:
            # Receive data from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            await handle_websocket_message(message, user_uuid)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(user_uuid)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_uuid}: {e}")
        connection_manager.disconnect(user_uuid)

async def send_initial_data(user_uuid: str):
    """Send initial data to a newly connected user."""
    try:
        # Send friend locations
        friend_locations = get_friend_locations(user_uuid)
        if friend_locations:
            await connection_manager.send_personal_message({
                "type": "user_locations",
                "data": friend_locations
            }, user_uuid)
        
        # Send device locations
        device_locations = get_device_locations(user_uuid)
        if device_locations:
            await connection_manager.send_personal_message({
                "type": "device_locations",
                "data": device_locations
            }, user_uuid)
        
        # Send groups
        groups = get_user_groups_ws(user_uuid)
        if groups:
            await connection_manager.send_personal_message({
                "type": "groups",
                "data": groups
            }, user_uuid)
            
    except Exception as e:
        logger.error(f"Error sending initial data to {user_uuid}: {e}")

async def handle_websocket_message(message: dict, user_uuid: str):
    """Handle incoming WebSocket messages."""
    try:
        message_type = message.get('type')
        data = message.get('data', {})
        
        if message_type == 'user_location':
            await handle_user_location_update(data, user_uuid)
        elif message_type == 'device_location':
            await handle_device_location_update(data, user_uuid)
        else:
            logger.warning(f"Unknown message type: {message_type}")
            
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")

async def handle_user_location_update(data: dict, user_uuid: str):
    """Handle user location update."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Update user location
            cursor.execute('''
                INSERT OR REPLACE INTO user_locations 
                (uuid, latitude, longitude, altitude, speed, battery, accuracy, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_uuid,
                data.get('latitude'),
                data.get('longitude'),
                data.get('altitude'),
                data.get('speed'),
                data.get('battery'),
                data.get('accuracy'),
                datetime.now()
            ))
            
            # Update user last seen
            cursor.execute('UPDATE users SET last_seen = ? WHERE uuid = ?', (datetime.now(), user_uuid))
            
            conn.commit()
        
        # Broadcast to friends
        friend_locations = get_friend_locations(user_uuid, include_self=True)
        user_location = next((loc for loc in friend_locations if loc['uuid'] == user_uuid), None)
        
        if user_location:
            await connection_manager.broadcast_to_friends({
                "type": "user_locations",
                "data": [user_location]
            }, user_uuid, db_manager)
        
        logger.info(f"Updated location for user {user_uuid}")
        
    except Exception as e:
        logger.error(f"Error handling user location update: {e}")

async def handle_device_location_update(data: dict, user_uuid: str):
    """Handle device location update."""
    try:
        device_id = data.get('device_id') or data.get('imei')
        if not device_id:
            logger.warning("Device location update missing device_id/imei")
            return
        
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if device belongs to user
            cursor.execute('SELECT name FROM devices WHERE imei = ? AND owner_uuid = ?', (device_id, user_uuid))
            device = cursor.fetchone()
            if not device:
                logger.warning(f"Device {device_id} not found for user {user_uuid}")
                return
            
            # Update device location
            cursor.execute('''
                INSERT OR REPLACE INTO device_locations 
                (device_id, latitude, longitude, altitude, speed, battery, battery_mv, 
                 bark, satellites, lte_signal, lora_rssi, connection_type, time, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                device_id,
                data.get('latitude') or data.get('lat'),
                data.get('longitude') or data.get('lon'),
                data.get('altitude'),
                data.get('speed'),
                data.get('battery'),
                data.get('battery_mv'),
                data.get('bark'),
                data.get('satellites'),
                data.get('lte_signal'),
                data.get('lora_rssi'),
                data.get('connection_type'),
                data.get('time'),
                datetime.now()
            ))
            
            # Update device last seen
            cursor.execute('UPDATE devices SET last_seen = ? WHERE imei = ?', (datetime.now(), device_id))
            
            conn.commit()
        
        # Broadcast to friends and shared users
        device_locations = get_device_locations(user_uuid)
        device_location = next((loc for loc in device_locations if loc['device_id'] == device_id), None)
        
        if device_location:
            # Send to friends
            device_location['type'] = DeviceLocationType.FRIEND.value
            await connection_manager.broadcast_to_friends({
                "type": "device_locations",
                "data": [device_location]
            }, user_uuid, db_manager)
            
            # Send to users with whom device is shared
            device_location['type'] = DeviceLocationType.SHARED.value
            await broadcast_to_shared_users(device_id, {
                "type": "device_locations",
                "data": [device_location]
            })
        
        logger.info(f"Updated location for device {device_id}")
        
    except Exception as e:
        logger.error(f"Error handling device location update: {e}")

def get_friend_locations(user_uuid: str, include_self: bool = False) -> List[dict]:
    """Get locations of user's friends."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT u.uuid, u.email, u.nickname, ul.latitude, ul.longitude, 
                       ul.altitude, ul.speed, ul.battery, ul.accuracy, ul.timestamp
                FROM users u
                JOIN user_locations ul ON u.uuid = ul.uuid
                WHERE u.uuid IN (
                    SELECT f.friend_uuid FROM friends f 
                    WHERE f.user_uuid = ? AND f.status = 'accepted'
                    UNION
                    SELECT f.user_uuid FROM friends f 
                    WHERE f.friend_uuid = ? AND f.status = 'accepted'
                )
            '''
            
            if include_self:
                query += ' OR u.uuid = ?'
                cursor.execute(query, (user_uuid, user_uuid, user_uuid))
            else:
                cursor.execute(query, (user_uuid, user_uuid))
            
            locations = []
            for row in cursor.fetchall():
                locations.append({
                    'uuid': row[0],
                    'email': row[1],
                    'nickname': row[2],
                    'latitude': row[3],
                    'longitude': row[4],
                    'altitude': row[5],
                    'speed': row[6],
                    'battery': row[7],
                    'accuracy': row[8],
                    'timestamp': row[9]
                })
            
            return locations
            
    except Exception as e:
        logger.error(f"Error getting friend locations: {e}")
        return []

def get_device_locations(user_uuid: str) -> List[dict]:
    """Get locations of user's devices and shared devices."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get own devices
            cursor.execute('''
                SELECT d.imei, d.owner_uuid, u.email, u.nickname, d.name,
                       dl.latitude, dl.longitude, dl.altitude, dl.speed, dl.battery,
                       dl.battery_mv, dl.bark, dl.satellites, dl.lte_signal, dl.lora_rssi,
                       dl.connection_type, dl.time, dl.timestamp, 'own' as type
                FROM devices d
                JOIN users u ON d.owner_uuid = u.uuid
                LEFT JOIN device_locations dl ON d.imei = dl.device_id
                WHERE d.owner_uuid = ?
            ''', (user_uuid,))
            
            locations = []
            for row in cursor.fetchall():
                locations.append({
                    'device_id': row[0],
                    'owner_uuid': row[1],
                    'owner_email': row[2],
                    'owner_nickname': row[3],
                    'device_name': row[4],
                    'latitude': row[5],
                    'longitude': row[6],
                    'altitude': row[7],
                    'speed': row[8],
                    'battery': row[9],
                    'battery_mv': row[10],
                    'bark': row[11],
                    'satellites': row[12],
                    'lte_signal': row[13],
                    'lora_rssi': row[14],
                    'connection_type': row[15],
                    'time': row[16],
                    'timestamp': row[17],
                    'type': row[18]
                })
            
            # Get shared devices
            cursor.execute('''
                SELECT d.imei, d.owner_uuid, u.email, u.nickname, d.name,
                       dl.latitude, dl.longitude, dl.altitude, dl.speed, dl.battery,
                       dl.battery_mv, dl.bark, dl.satellites, dl.lte_signal, dl.lora_rssi,
                       dl.connection_type, dl.time, dl.timestamp, 'shared' as type
                FROM device_shares ds
                JOIN devices d ON ds.device_imei = d.imei
                JOIN users u ON d.owner_uuid = u.uuid
                LEFT JOIN device_locations dl ON d.imei = dl.device_id
                WHERE ds.shared_with_uuid = ?
            ''', (user_uuid,))
            
            for row in cursor.fetchall():
                locations.append({
                    'device_id': row[0],
                    'owner_uuid': row[1],
                    'owner_email': row[2],
                    'owner_nickname': row[3],
                    'device_name': row[4],
                    'latitude': row[5],
                    'longitude': row[6],
                    'altitude': row[7],
                    'speed': row[8],
                    'battery': row[9],
                    'battery_mv': row[10],
                    'bark': row[11],
                    'satellites': row[12],
                    'lte_signal': row[13],
                    'lora_rssi': row[14],
                    'connection_type': row[15],
                    'time': row[16],
                    'timestamp': row[17],
                    'type': row[18]
                })
            
            return locations
            
    except Exception as e:
        logger.error(f"Error getting device locations: {e}")
        return []

def get_user_groups_ws(user_uuid: str) -> List[dict]:
    """Get user's groups for WebSocket."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT g.id, g.name, g.description, g.owner_id, g.created_at
                FROM groups g
                LEFT JOIN group_members gm ON g.id = gm.group_id
                WHERE g.owner_id = ? OR gm.user_uuid = ?
                GROUP BY g.id
            ''', (user_uuid, user_uuid))
            
            groups = []
            for row in cursor.fetchall():
                group_id = row[0]
                
                # Get member IDs
                cursor.execute('SELECT user_uuid FROM group_members WHERE group_id = ?', (group_id,))
                member_ids = [member[0] for member in cursor.fetchall()]
                
                groups.append({
                    'id': group_id,
                    'name': row[1],
                    'description': row[2],
                    'owner_id': row[3],
                    'member_ids': member_ids,
                    'created_at': row[4]
                })
            
            return groups
            
    except Exception as e:
        logger.error(f"Error getting user groups: {e}")
        return []

async def broadcast_to_shared_users(device_imei: str, message: dict):
    """Broadcast message to users with whom device is shared."""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT shared_with_uuid FROM device_shares WHERE device_imei = ?', (device_imei,))
            
            for row in cursor.fetchall():
                shared_with_uuid = row[0]
                await connection_manager.send_personal_message(message, shared_with_uuid)
                
    except Exception as e:
        logger.error(f"Error broadcasting to shared users: {e}")


if __name__ == "__main__":
    # Server configuration
    host = os.getenv(SERVER_HOST_ENV_VAR, "0.0.0.0")
    port = int(os.getenv(SERVER_PORT_ENV_VAR, "8000"))
    
    # Run the server
    #TODO: make sure this also ends up in same logs (or different log file)
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )
