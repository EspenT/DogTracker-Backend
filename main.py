### 📁 File: main.py
import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
import traceback
from mqtt_handler import start_mqtt_thread  # ✅ Added MQTT integration

# Configure global logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI()

# Debug flag from env (e.g., DEBUG=true)
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Allow CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory list of connections
active_connections: list[WebSocket] = []

# SQLite DB path
DB_PATH = "/app/data/dogtracker.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# SQLite setup
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            timestamp TEXT,
            user_lat REAL,
            user_lon REAL,
            dog_lat REAL,
            dog_lon REAL,
            bark INTEGER,
            raw TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

async def broadcast(message: str, sender: WebSocket = None):
    logging.info(f"Broadcasting to {len(active_connections) - (1 if sender else 0)} clients")
    for connection in active_connections:
        if connection != sender:
            try:
                await connection.send_text(message)
            except Exception as e:
                logging.warning(f"Failed to send to a client: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logging.info("Client connected")

    try:
        while True:
            try:
                raw = await websocket.receive_text()
                logging.info(f"Raw received: {raw}")

                try:
                    data = json.loads(raw)
                    logging.info(f"Parsed data: {json.dumps(data, indent=2)}")
                    save_to_db(data)
                    await broadcast(raw, websocket)
                except Exception as parse_error:
                    logging.warning(f"Error parsing or saving: {parse_error}")
                    traceback.print_exc()

            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.warning(f"Error receiving message: {e}")
                traceback.print_exc()
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
        logging.info("Client disconnected")

def save_to_db(obj: dict):
    payload = obj.get("payload", {})
    dog = payload.get("dog", {})
    user = payload.get("user", {})

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO locations (device_id, timestamp, user_lat, user_lon, dog_lat, dog_lon, bark, raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        dog.get("device_id", "unknown"),
        payload.get("timestamp"),
        user.get("lat"),
        user.get("lon"),
        dog.get("latitude"),
        dog.get("longitude"),
        dog.get("bark", 0),
        json.dumps(obj)
    ))
    conn.commit()
    conn.close()

@app.get("/locations/recent")
def get_recent_locations(device_id: str = Query(...)):
    try:
        since = datetime.utcnow() - timedelta(hours=4)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT timestamp, dog_lat, dog_lon, bark FROM locations
            WHERE device_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        ''', (device_id, since.isoformat()))

        rows = c.fetchall()
        conn.close()

        result = [
            {"timestamp": r[0], "lat": r[1], "lon": r[2], "bark": r[3]}
            for r in rows
        ]
        return JSONResponse(content=result)
    except Exception as e:
        logging.error(f"Error retrieving recent locations: {e}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# MQTT ingestion callback for backend
def mqtt_ingest(data):
    logging.info("[MQTT -> WS] Handling parsed MQTT data")
    save_to_db(data)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    asyncio.run_coroutine_threadsafe(broadcast(json.dumps(data)), loop)

# Start background MQTT listener thread
start_mqtt_thread(mqtt_ingest)

