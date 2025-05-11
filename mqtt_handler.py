### 📁 File: mqtt_handler.py
import os
import logging
import json
import threading
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from datetime import datetime

# Load from custom env file
load_dotenv(dotenv_path="mqtt.env")

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "DogTracker/devices/")

# Topic buffer for assembling packets
device_buffers = {}  # key = device_id
backend_callback = None  # set by main to receive parsed payloads

def on_connect(client, userdata, flags, rc):
    logging.info(f"[MQTT] Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC_PREFIX + "+/Position/latitude")
    client.subscribe(MQTT_TOPIC_PREFIX + "+/Position/longitude")
    client.subscribe(MQTT_TOPIC_PREFIX + "+/battery")
    client.subscribe(MQTT_TOPIC_PREFIX + "+/bark")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode("utf-8")
    logging.info(f"[MQTT] {topic}: {payload}")

    try:
        parts = topic[len(MQTT_TOPIC_PREFIX):].split("/")
        if len(parts) < 2:
            return

        device_id = parts[0]
        subtopic = "/".join(parts[1:])

        buf = device_buffers.setdefault(device_id, {
            "device_id": device_id,
            "latitude": None,
            "longitude": None,
            "battery": None,
            "bark": None,
            "last_update": datetime.utcnow().isoformat()
        })

        if subtopic == "Position/latitude":
            buf["latitude"] = float(payload)
        elif subtopic == "Position/longitude":
            buf["longitude"] = float(payload)
        elif subtopic == "battery":
            buf["battery"] = int(payload)
        elif subtopic == "bark":
            buf["bark"] = int(payload)
        else:
            return

        buf["last_update"] = datetime.utcnow().isoformat()

        # If we have a complete packet, dispatch it
        if all(k in buf and buf[k] is not None for k in ["latitude", "longitude", "battery", "bark"]):
            assembled = {
                "type": "update",
                "payload": {
                    "user": {},  # blank since it's not from a phone
                    "dog": {
                        **buf
                    },
                    "timestamp": buf["last_update"]
                }
            }
            logging.info(f"[MQTT] Dispatching full update for {device_id}")
            if backend_callback:
                backend_callback(assembled)

    except Exception as e:
        logging.warning(f"[MQTT] Failed to parse message: {e}")


def start_mqtt_thread(callback):
    global backend_callback
    backend_callback = callback
    client = mqtt.Client()
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    threading.Thread(target=client.loop_forever, daemon=True).start()
    logging.info("[MQTT] MQTT listener started")

