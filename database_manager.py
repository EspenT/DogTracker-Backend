
import sqlite3
import logging

# Database Manager
class DatabaseManager:
    def __init__(self, logger: logging.Logger, db_path: str = "dog_tracker.db"):
        self.logger = logger
        self.db_path = db_path
        self._connection = sqlite3.connect(db_path)
        self.init_database()

    def init_database(self):
        """Initialize the database with all required tables."""
        with self._connection:
            cursor = self._connection.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    uuid TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP,
                    role TEXT CHECK(role IN ('U', 'A')) NOT NULL DEFAULT 'U'
                )
            ''')

            # User locations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_locations (
                    uuid TEXT PRIMARY KEY,
                    latitude REAL,
                    longitude REAL,
                    altitude REAL,
                    speed REAL,
                    battery INTEGER,
                    accuracy REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uuid) REFERENCES users (uuid)
                )
            ''')
            
            # Devices table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    imei TEXT PRIMARY KEY,
                    owner_uuid TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP,
                    FOREIGN KEY (owner_uuid) REFERENCES users (uuid)
                )
            ''')
            
            # Device locations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_locations (
                    device_id TEXT PRIMARY KEY,
                    latitude REAL,
                    longitude REAL,
                    altitude REAL,
                    speed REAL,
                    battery INTEGER,
                    battery_mv INTEGER,
                    bark INTEGER,
                    satellites INTEGER,
                    lte_signal INTEGER,
                    lora_rssi INTEGER,
                    connection_type TEXT,
                    time TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices (imei)
                )
            ''')
            
            # Friends table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS friends (
                    user_uuid TEXT,
                    friend_uuid TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_uuid, friend_uuid),
                    FOREIGN KEY (user_uuid) REFERENCES users (uuid),
                    FOREIGN KEY (friend_uuid) REFERENCES users (uuid)
                )
            ''')
            
            # Groups table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    owner_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users (uuid)
                )
            ''')
            
            # Group members table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id TEXT,
                    user_uuid TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (group_id, user_uuid),
                    FOREIGN KEY (group_id) REFERENCES groups (id),
                    FOREIGN KEY (user_uuid) REFERENCES users (uuid)
                )
            ''')
            
            # Device shares table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_shares (
                    device_imei TEXT,
                    owner_uuid TEXT,
                    shared_with_uuid TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (device_imei, shared_with_uuid),
                    FOREIGN KEY (device_imei) REFERENCES devices (imei),
                    FOREIGN KEY (owner_uuid) REFERENCES users (uuid),
                    FOREIGN KEY (shared_with_uuid) REFERENCES users (uuid)
                )
            ''')
            
            self._connection.commit()
            self.logger.info("Database initialized successfully")

    def get_connection(self):
        """Get a database connection."""
        return self._connection
