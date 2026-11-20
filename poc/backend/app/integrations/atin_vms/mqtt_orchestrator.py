"""ATIN Smart VMS MQTT Orchestrator & Publisher (C01, C02, C03, C06, C07)."""

from __future__ import annotations

import json
import ssl
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import paho.mqtt.client as mqtt

from app.core.logging import get_logger

VN_TZ = timezone(timedelta(hours=7))
logger = get_logger("app.integrations.atin_vms.mqtt")


class AtinMqttClient:
    """Manages resilient WSS MQTT connection, camera sync, zone hot-reload, bbox & events."""

    def __init__(
        self,
        host: str,
        port: int,
        ws_path: str,
        username: str,
        password: str,
        client_id: str,
        keepalive: int = 30,
        organization_id: int = 103,
        zone_id: int = 51,
        ai_module_code: str = "ZONE",
        on_cameras_sync: Callable[[list[dict[str, Any]]], None] | None = None,
        on_zones_update: Callable[[str, list[dict[str, Any]]], None] | None = None,
    ) -> None:
        if client_id.startswith(("vms_staging_backend", "vms_prod_backend")):
            raise ValueError("MQTT_CLIENT_ID must not start with backend reserved prefixes")

        self.host = host
        self.port = port
        self.ws_path = ws_path
        self.organization_id = organization_id
        self.zone_id = zone_id
        self.ai_module_code = ai_module_code.upper()
        self.on_cameras_sync = on_cameras_sync
        self.on_zones_update = on_zones_update

        self._lock = threading.Lock()
        self._zones_by_camera: dict[str, list[dict[str, Any]]] = {}

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
        )
        self._client.ws_set_options(path=ws_path)
        if username:
            self._client.username_pw_set(username, password)
        if port == 443:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._handle_connect
        self._client.on_message = self._handle_message
        self.keepalive = keepalive

    def start(self) -> None:
        self._client.connect_async(self.host, self.port, keepalive=self.keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _handle_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, rc: Any, _props: Any = None) -> None:
        logger.info("MQTT connected (rc=%s) to %s:%s", rc, self.host, self.port)
        client.subscribe(f"smart_vms/cameras/company/{self.organization_id}", qos=1)
        client.subscribe(f"smart_vms/cameras/zone/{self.zone_id}", qos=1)
        client.subscribe(f"smart_vms/cameras/+/ai_zones/{self.ai_module_code}", qos=1)
        client.publish(
            "smart_vms/cameras/getdevice",
            json.dumps({"organization_id": self.organization_id, "zone_id": self.zone_id}),
            qos=1,
        )

    def _handle_message(self, _client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        raw = msg.payload.decode("utf-8", errors="ignore").strip()
        if not raw:
            if "/ai_zones/" in topic and topic.endswith(f"/{self.ai_module_code}"):
                cam_code = topic.split("/")[2]
                self._update_zones(cam_code, [])
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ignoring invalid JSON on topic %s", topic)
            return

        if topic.startswith(("smart_vms/cameras/company/", "smart_vms/cameras/zone/")):
            cameras = data if isinstance(data, list) else data.get("cameras", [])
            if self.on_cameras_sync and isinstance(cameras, list):
                self.on_cameras_sync(cameras)
            return

        if "/lines" in topic:
            return

        if "/ai_zones/" in topic and topic.endswith(f"/{self.ai_module_code}"):
            cam_code = data.get("camera_code") or topic.split("/")[2]
            filtered = [
                z
                for z in data.get("ai_zones", [])
                if str(z.get("ai_modules", "")).upper() == self.ai_module_code
            ]
            self._update_zones(cam_code, filtered)

    def _update_zones(self, cam_code: str, zones: list[dict[str, Any]]) -> None:
        with self._lock:
            self._zones_by_camera[cam_code] = zones
        if self.on_zones_update:
            self.on_zones_update(cam_code, zones)

    def get_zones(self, cam_code: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._zones_by_camera.get(cam_code, []))

    def publish_bbox(self, camera_code: str, boxes: list[dict[str, Any]]) -> None:
        """Publish realtime normalized BBox (C07: QoS 0, retain=False)."""
        payload = {
            "camera_code": camera_code,
            "ai_modules": self.ai_module_code,
            "timestamp": time.time(),
            "detections": boxes,
        }
        self._client.publish(f"smart_vms/ai/bbox/{camera_code}", json.dumps(payload), qos=0, retain=False)

    def publish_event(
        self,
        camera_id: str,
        camera_code: str,
        snapshot_object_key: str,
        payload_data: dict[str, Any],
        entity_type: str = "PERSON",
        submodule_code: str | None = None,
    ) -> int:
        """Publish verified AI event (C06: QoS 1, +07:00 ISO-8601)."""
        topic = f"smart_vms/ai_events/{self.ai_module_code}"
        event_time = datetime.now(VN_TZ).isoformat(timespec="seconds")
        body: dict[str, Any] = {
            "camera_id": camera_id,
            "camera_code": camera_code,
            "ai_modules": self.ai_module_code,
            "entity_type": entity_type,
            "event_time": event_time,
            "snapshot_url": snapshot_object_key,
            "payload": payload_data,
        }
        if submodule_code:
            body["submodule_code"] = submodule_code

        info = self._client.publish(topic, json.dumps(body, ensure_ascii=False), qos=1, retain=False)
        logger.info(
            "Published event timestamp=%s topic=%s camera_code=%s object_key=%s rc=%s",
            event_time,
            topic,
            camera_code,
            snapshot_object_key,
            info.rc,
        )
        return info.rc
