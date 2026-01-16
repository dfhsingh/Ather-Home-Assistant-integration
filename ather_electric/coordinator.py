"""Coordinator for Ather Electric."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import WS_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AtherCoordinator:
    """Manages the WebSocket connection and data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        scooter_id: str,
        firebase_token: str,
        api_key: str,
        device_name: str,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.scooter_id = scooter_id
        self.firebase_token = firebase_token
        self.api_key = api_key
        self.device_name = device_name
        self.name = device_name
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.data: Dict[str, Any] = {}
        self._listeners: list = []
        self.session = async_get_clientsession(hass)
        self._shutdown = False
        self.shutdown_safe_mode = True  # Default to Safe Mode ON
        self.last_update_success = False  # For CoordinatorEntity compatibility

        # Token Management
        self.refresh_token: Optional[str] = None
        self.token_file = hass.config.path(".ather_tokens.json")

    async def _send_put_request(self, path: str, data: Dict[str, Any]) -> bool:
        """Send a PUT request to Firebase."""
        id_token = await self.get_id_token()
        if not id_token:
            _LOGGER.error("Cannot send PUT request: No ID token")
            return False

        url = f"https://ather-production-mu.firebaseio.com/{path}.json?auth={id_token}"
        try:
            async with self.session.put(url, json=data) as resp:
                if resp.status == 200:
                    _LOGGER.info("PUT request to %s successful", path)
                    return True
                else:
                    text = await resp.text()
                    _LOGGER.error("PUT request to %s failed: %s", path, text)
                    return False
        except Exception as err:
            _LOGGER.error("Error sending PUT request: %s", err)
            return False

    async def async_ping_scooter(self) -> None:
        """Send ping_my_scooter command."""
        path = f"scooters/{self.scooter_id}/ping_my_scooter"
        data = {"request_id": "home_assistant_ping", "state": 1}
        await self._send_put_request(path, data)

    async def async_remote_charging(self, action: str) -> None:
        """Send remote_charging command (start/stop)."""
        path = f"scooters/{self.scooter_id}/remote_charging"
        data = {"action": action}
        await self._send_put_request(path, data)

    async def async_remote_shutdown(self) -> None:
        """Send remote_shutdown command."""
        path = f"scooters/{self.scooter_id}/remote_shutdown"
        # Based on logic: state 1 triggers shutdown
        data = {"state": 1}
        await self._send_put_request(path, data)

    def _load_tokens(self):
        """Load refresh token from file."""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    data = json.load(f)
                    self.refresh_token = data.get("refresh_token")
            except Exception as err:
                _LOGGER.error("Failed to load tokens: %s", err)

    def _save_tokens(self):
        """Save refresh token to file."""
        try:
            with open(self.token_file, "w") as f:
                json.dump({"refresh_token": self.refresh_token}, f)
        except Exception as err:
            _LOGGER.error("Failed to save tokens: %s", err)

    def async_add_listener(self, update_callback, context=None):
        """Listen for data updates."""
        self._listeners.append(update_callback)

    def _notify_listeners(self):
        """Notify all listeners that data has changed."""
        for callback in self._listeners:
            callback()

    def get_data(self, key: str, default: Any = None) -> Any:
        """Get data value by key."""
        return self.data.get(key, default)

    async def get_id_token(self) -> Optional[str]:
        """Get a valid ID token, refreshing if necessary."""
        if self.refresh_token:
            token = await self._refresh_id_token()
            if token:
                return token
            _LOGGER.warning(
                "Refresh token failed, falling back to custom token exchange."
            )

        return await self._exchange_custom_token()

    async def _refresh_id_token(self) -> Optional[str]:
        """Get new ID token using refresh token."""
        url = f"https://securetoken.googleapis.com/v1/token?key={self.api_key}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }

        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    new_refresh = data.get("refresh_token")
                    if new_refresh:
                        self.refresh_token = new_refresh
                        await self.hass.async_add_executor_job(self._save_tokens)
                    return data.get("id_token")
                else:
                    text = await resp.text()
                    _LOGGER.warning("Token refresh failed: %s", text)
                    return None
        except Exception as err:
            _LOGGER.error("Error refreshing token: %s", err)
            return None

    async def _exchange_custom_token(self) -> Optional[str]:
        """Exchanges custom token for ID token and Refresh token."""
        url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken?key={self.api_key}"
        payload = {"token": self.firebase_token, "returnSecureToken": True}

        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status == 200:
                    json_resp = await resp.json()
                    id_token = json_resp.get("idToken")
                    refresh_token = json_resp.get("refreshToken")

                    if refresh_token:
                        self.refresh_token = refresh_token
                        await self.hass.async_add_executor_job(self._save_tokens)

                    return id_token
                else:
                    text = await resp.text()
                    _LOGGER.error(
                        "Custom token exchange failed: %s. The configured token may be expired.",
                        text,
                    )
                    return None
        except Exception as err:
            _LOGGER.error("Error exchanging custom token: %s", err)
            return None

    async def connect(self):
        """Connect to WebSocket and listen for messages."""
        if self.refresh_token is None:
            await self.hass.async_add_executor_job(self._load_tokens)

        while not self._shutdown:
            try:
                id_token = await self.get_id_token()
                if not id_token:
                    _LOGGER.error(
                        "Could not obtain ID token. Waiting 60s before retry."
                    )
                    await asyncio.sleep(60)
                    continue

                async with self.session.ws_connect(WS_URL) as ws:
                    self.ws = ws
                    _LOGGER.info("Connected to Ather WebSocket")
                    self.last_update_success = True
                    self._notify_listeners()

                    # Authenticate
                    auth_payload = {
                        "t": "d",
                        "d": {"r": 1, "a": "auth", "b": {"cred": id_token}},
                    }
                    await ws.send_json(auth_payload)

                    # Single Subscription to the root scooter node
                    # This minimizes calls and ensures we get all data in one stream
                    path = f"/scooters/{self.scooter_id}"
                    _LOGGER.info(f"Subscribing to {path}")
                    sub_payload = {
                        "t": "d",
                        "d": {"r": 2, "a": "q", "b": {"p": path, "h": ""}},
                    }
                    await ws.send_json(sub_payload)

                    # Subscribe to 'app' (for mode ranges)
                    path_app = f"/scooters/{self.scooter_id}/app"
                    _LOGGER.info(f"Subscribing to {path_app}")
                    sub_payload_app = {
                        "t": "d",
                        "d": {"r": 3, "a": "q", "b": {"p": path_app, "h": ""}},
                    }
                    await ws.send_json(sub_payload_app)

                    # Subscribe to 'lastSyncedTime'
                    path_sync = f"/scooters/{self.scooter_id}/lastSyncedTime"
                    _LOGGER.info(f"Subscribing to {path_sync}")
                    sub_payload_sync = {
                        "t": "d",
                        "d": {"r": 4, "a": "q", "b": {"p": path_sync, "h": ""}},
                    }
                    await ws.send_json(sub_payload_sync)

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            break

            except aiohttp.ClientError as err:
                _LOGGER.error("WebSocket connection error: %s", err)
                self.last_update_success = False
                self._notify_listeners()
                await asyncio.sleep(10)
            except Exception as err:
                _LOGGER.error("Unexpected error in WebSocket loop: %s", err)
                self.last_update_success = False
                self._notify_listeners()
                await asyncio.sleep(10)

    async def _handle_message(self, message: str):
        """Parse incoming WebSocket message."""
        try:
            msg = json.loads(message)
            if "t" in msg and msg["t"] == "d":
                data = msg.get("d", {})
                b_body = data.get("b", {})

                if b_body and "d" in b_body:
                    real_data = b_body["d"]

                    # Data handling logic
                    # Since we subscribed to the root, 'real_data' might be the whole scooter object
                    # or partial updates (patches)
                    # We should merge into self.data recursively or just flat map common keys

                    self._process_data(real_data)
                    self._notify_listeners()

        except Exception as err:
            _LOGGER.error("Error parsing message: %s", err)

    def _process_data(self, data: Any):
        """Process and flatten data updates."""
        if not isinstance(data, dict):
            return

        # 1. Look for 'bike' or nested structures
        # If we got the full object, it has keys like 'bike', 'charging', etc.

        # Flatten helpful keys into self.data for easy sensor access

        # --- Battery & Range (often in bike -> batterySOC) ---
        # Check standard path
        bike = data.get("bike", {})
        if bike:
            if "batterySOC" in bike:
                self.data["batterySOC"] = bike["batterySOC"]
            if "predictedRange" in bike:
                self.data["predictedRange"] = bike["predictedRange"]
            if "range" in bike:
                self.data["range"] = bike["range"]
            if "speed" in bike:
                self.data["speed"] = bike["speed"]
            if "mode" in bike:
                self.data["mode"] = bike["mode"]
            if "keySwitch" in bike:
                self.data["keySwitch"] = bike["keySwitch"]
            if "VIN" in bike:
                self.data["vin"] = bike["VIN"]
            if "odo" in bike:
                self.data["odo"] = bike["odo"]
            if "bikeType" in bike:
                self.data["bikeType"] = bike["bikeType"]
            if "otaStatus" in bike:
                self.data["otaStatus"] = bike["otaStatus"]
            if "GPSLocation" in bike:
                self._update_gps(bike["GPSLocation"])

        # Check root level (sometimes updates come as flattened patches)
        if "batterySOC" in data:
            self.data["batterySOC"] = data["batterySOC"]
        if "predictedRange" in data:
            self.data["predictedRange"] = data["predictedRange"]
        if "speed" in data:
            self.data["speed"] = data["speed"]
        if "mode" in data:
            self.data["mode"] = data["mode"]
        if "charging" in data:
            self.data["charging"] = data["charging"]  # This is usually a dict
        if "GPSLocation" in data:
            self._update_gps(data["GPSLocation"])

        # 3. Handle 'charging' object at root if present (it was in the payload)
        if "charging" in data:
            self.data["charging"] = data["charging"]

        # 4. Handle flattened patch updates (e.g. "bike/mode": "Warp")
        for key, value in data.items():
            if "/" in key:
                parts = key.split("/")
                if len(parts) == 2:
                    category, field = parts

                    # Handle bike/* updates (flatten to root self.data for sensors)
                    if category == "bike":
                        if field == "mode":
                            self.data["mode"] = value
                        elif field == "speed":
                            self.data["speed"] = value
                        elif field == "batterySOC":
                            self.data["batterySOC"] = value
                        elif field == "predictedRange":
                            self.data["predictedRange"] = value
                        elif field == "range":
                            self.data["range"] = value
                        elif field == "keySwitch":
                            self.data["keySwitch"] = value
                        elif field == "odo":
                            self.data["odo"] = value
                        elif field == "VIN":
                            self.data["vin"] = value
                        elif field == "bikeType":
                            self.data["bikeType"] = value
                        elif field == "otaStatus":
                            self.data["otaStatus"] = value

                    # Handle charging/* updates (update the nested dict)
                    elif category == "charging":
                        if "charging" not in self.data or not isinstance(
                            self.data["charging"], dict
                        ):
                            self.data["charging"] = {}
                        self.data["charging"][field] = value

        # Also maintain a raw dump if needed, or just update dict

        # Handle 'app' data for mode ranges
        app_data = data.get("app", {})
        if app_data and "modeRange" in app_data:
            self.data["modeRange"] = app_data["modeRange"]

        if "lastSyncedTime" in data:
            self.data["lastSyncedTime"] = data["lastSyncedTime"]

        # Flattened patch updates handling extended
        for key, value in data.items():
            if "/" in key:
                parts = key.split("/")
                if len(parts) == 2:
                    category, field = parts

                    if category == "app" and field == "modeRange":
                        self.data["modeRange"] = value

        # Check nested lastSyncedTime (if it comes under root or bike)
        # Based on logs, it was /scooters/s_421436/lastSyncedTime -> Value: ...
        # So it might come as a direct update.

        self.data.update(data)

    def _update_gps(self, gps_data):
        """Extract lat/lon."""
        if gps_data and "lat" in gps_data and "lng" in gps_data:
            self.data["lat"] = gps_data["lat"]
            self.data["lon"] = gps_data["lng"]
