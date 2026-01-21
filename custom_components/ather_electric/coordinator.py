"""Coordinator for Ather Electric."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import aiohttp
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AtherAPI
from .const import WS_URL, DOMAIN, CONF_ENABLE_RAW_LOGGING, DEFAULT_ENABLE_RAW_LOGGING

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
        self.api = AtherAPI(self.session)
        self._shutdown = False
        self.shutdown_safe_mode = True  # Default to Safe Mode ON
        self.last_update_success = False  # For CoordinatorEntity compatibility

        # Token Management
        self.refresh_token: Optional[str] = None
        self.token_file = hass.config.path(".ather_tokens.json")
        self._ready_event = asyncio.Event()

        # Config Options
        self.enable_raw_logging = False  # Will be updated from entry options
        self._runner_task: Optional[asyncio.Task] = None
        self._remove_stop_listener = None
        
        # State tracking
        self._previous_state = None

    def start(self) -> None:
        """Start the coordinator background task."""
        if not self._runner_task:
            self._runner_task = self.hass.loop.create_task(self.connect())
            
        if not self._remove_stop_listener:
            self._remove_stop_listener = self.hass.bus.async_listen(
                EVENT_HOMEASSISTANT_STOP, self._handle_ha_stop
            )

    async def _handle_ha_stop(self, event: Event) -> None:
        """Handle Home Assistant shut down."""
        _LOGGER.debug("Home Assistant is stopping, closing coordinator")
        await self.close()

    async def close(self) -> None:
        """Close the coordinator and WebSocket connection."""
        self._shutdown = True
        
        # Cancel the runner task if active
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
        self._runner_task = None

        if self._remove_stop_listener:
            self._remove_stop_listener()
            self._remove_stop_listener = None
        
        if self.ws and not self.ws.closed:
            await self.ws.close()
        _LOGGER.info("AtherCoordinator closed")

    async def async_ping_scooter(self) -> None:
        """Send ping_my_scooter command."""
        key_state = self.data.get("keySwitch")
        if key_state == 1:
            _LOGGER.warning("Ping blocked: Scooter key is ON")
            return

        path = f"scooters/{self.scooter_id}/ping_my_scooter"
        ts = int(time.time() * 1000)
        data = {
            "request_id": f"HA_{ts}",
            "state": 1,
            "timestamp": ts,
            "error": "0",
        }
        await self._send_put_request(path, data)

    async def async_remote_charging(self, action: str) -> None:
        """Send remote_charging command (start/stop)."""
        charging_data = self.data.get("charging", {})
        status = charging_data.get("chargingStatus")
        heartbeat = charging_data.get("chargingHeartBeat")

        if action == "start":
            if status == "Charging":
                _LOGGER.warning("Remote Start blocked: Already Charging")
                return
            if heartbeat != "On":
                _LOGGER.warning("Remote Start blocked: Charger not connected/ready")
                return
        else:
            if status != "Charging":
                _LOGGER.warning("Remote Stop blocked: Not currently charging")
                return

        path = f"scooters/{self.scooter_id}/remote_charging"
        ts = int(time.time() * 1000)

        data = {
            "action": action,
            "state": 1,
            "timestamp": ts,
            "request_id": f"HA_{ts}",
            "error": "0",
        }
        await self._send_put_request(path, data)

    async def async_remote_shutdown(self) -> None:
        """Send remote_shutdown command."""
        key_state = self.data.get("keySwitch")
        charging_data = self.data.get("charging", {})
        heartbeat = charging_data.get("chargingHeartBeat")

        if key_state == 1:
            _LOGGER.warning("Remote Shutdown blocked: Key is ON")
            return
        if heartbeat == "On":
            _LOGGER.warning("Remote Shutdown blocked: Charger is connected")
            return

        path = f"scooters/{self.scooter_id}/remote_shutdown"
        ts = int(time.time() * 1000)
        data = {
            "state": 1,
            "timestamp": ts,
            "error": "0",
        }
        await self._send_put_request(path, data)

    async def _send_put_request(self, path: str, data: Dict[str, Any]) -> bool:
        """Delegate PUT request to API."""
        id_token = await self.get_id_token()
        if not id_token:
            _LOGGER.error("Cannot send PUT request: No ID token")
            return False
        return await self.api.send_put_request(path, data, id_token)

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

        def remove_listener():
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

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
        """Get new ID token using refresh token via API."""
        if not self.refresh_token:
            return None

        data = await self.api.refresh_id_token(self.refresh_token, self.api_key)
        if data:
            new_refresh = data.get("refresh_token")
            if new_refresh:
                self.refresh_token = new_refresh
                await self.hass.async_add_executor_job(self._save_tokens)
            return data.get("id_token")
        return None

    async def _exchange_custom_token(self) -> Optional[str]:
        """Exchanges custom token for ID token via API."""
        data = await self.api.exchange_custom_token(self.firebase_token, self.api_key)
        if data:
            id_token = data.get("idToken")
            refresh_token = data.get("refreshToken")

            if refresh_token:
                self.refresh_token = refresh_token
                await self.hass.async_add_executor_job(self._save_tokens)

            return id_token
        return None

    async def connect(self):
        """Connect to WebSocket and listen for messages."""
        if self.refresh_token is None:
            await self.hass.async_add_executor_job(self._load_tokens)

        while not self._shutdown:
            if self.hass.is_stopping or (self.session and self.session.closed):
                 _LOGGER.debug("Halting coordinator loop: HAS stopping or session closed")
                 break

            try:
                id_token = await self.get_id_token()
                if not id_token:
                    # If session is closed during token fetch, we should probably stop
                    if self.session and self.session.closed:
                         break
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

                    # Subscriptions
                    paths = [
                        f"/scooters/{self.scooter_id}",
                    ]
                    
                    for idx, path in enumerate(paths, start=2):
                        _LOGGER.info(f"Subscribing to {path}")
                        sub_payload = {
                            "t": "d",
                            "d": {"r": idx, "a": "q", "b": {"p": path, "h": ""}},
                        }
                        await ws.send_json(sub_payload)

                    # Mark as ready - REMOVED: Waiting for actual data in _process_data
                    # self._ready_event.set()

                    async for msg in ws:
                        if self._shutdown or self.hass.is_stopping:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            _LOGGER.error("WebSocket error: %s", msg.data)
                            break
            
            except asyncio.CancelledError:
                _LOGGER.info("WebSocket connection cancelled")
                self._shutdown = True
                break
            except RuntimeError as err:
                 if "Session is closed" in str(err):
                     _LOGGER.debug("Session closed, stopping coordinator loop")
                     self._shutdown = True
                     break
                 _LOGGER.error("Runtime error in coordinator: %s", err)
                 if not self._shutdown:
                     await asyncio.sleep(10)
            except aiohttp.ClientError as err:
                _LOGGER.error("WebSocket connection error: %s", err)
                self.last_update_success = False
                self._notify_listeners()
                if not self._shutdown:
                    await asyncio.sleep(10)
            except Exception as err:
                _LOGGER.error("Unexpected error in WebSocket loop: %s", err)
                self.last_update_success = False
                self._notify_listeners()
                if not self._shutdown:
                    await asyncio.sleep(10)

    async def _handle_message(self, message: str):
        """Parse incoming WebSocket message."""
        try:
            if self.enable_raw_logging:
                log_path = self.hass.config.path("ather_ws_debug.log")
                await self.hass.async_add_executor_job(
                    self._log_raw_message, log_path, message
                )

            msg = json.loads(message)
            if "t" in msg and msg["t"] == "d":
                data = msg.get("d", {})
                b_body = data.get("b", {})

                if b_body and "d" in b_body:
                    real_data = b_body["d"]
                    self._process_data(real_data)
                    self._notify_listeners()

        except Exception as err:
            _LOGGER.error("Error parsing message: %s", err)

    def _recursive_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Recursively merge source dict into target dict."""
        for key, value in source.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                self._recursive_merge(target[key], value)
            else:
                target[key] = value

    def _process_data(self, data: Any):
        """Process and flatten data updates."""
        if not isinstance(data, dict):
            return

        # 1. Update internal data structure recursively
        self._recursive_merge(self.data, data)

        # 2. Flatten helpful keys into self.data for easy sensor access (Backwards Compatibility)
        # Many sensors expect keys at the root level (e.g., 'batterySOC', 'speed')
        
        # Helper to flatten specific keys from a source dict to root
        def flatten_keys(source: Dict[str, Any], keys: list):
            for k in keys:
                if k in source:
                    self.data[k] = source[k]

        # Flatten 'bike' fields
        bike = self.data.get("bike", {})
        if bike:
             flatten_keys(bike, [
                "batterySOC", "predictedRange", "range", "speed", "mode",
                "keySwitch", "VIN", "odo", "bikeType", "otaStatus",
                "TheftTowMovementState", "vehicleState", "ShutdownVacationMode",
                "parkingAssist", "UserFacingSoftwareVersion"
            ])
             if "GPSLocation" in bike:
                 self._update_gps(bike["GPSLocation"])

        # Flatten 'charging' to root if present (sometimes comes as separate object)
        if "charging" in data:
            # We already merged it into self.data['charging'] via recursive merge
            # Check if any sensors need something specific? No, they use get_data('charging')
            pass
        
        # Flatten 'app' fields
        app = self.data.get("app", {})
        if app:
            flatten_keys(app, ["modeRange", "features", "savings"])
            
        # Check if 'features' is now at root (from app flattening or direct) and flatten feature flags
        if "features" in self.data:
            flatten_keys(self.data["features"], [
                "atherStackPingMyScooter", 
                "atherStackRemoteShutdown", 
                "atherStackRemoteCharging"
            ])
            # Signal ready if we have the critical flags
            if "atherStackPingMyScooter" in self.data:
                 self._ready_event.set()

        # Flatten 'trip' fields
        if "trip" in data:
            trip = data["trip"]
            current_trip = trip.copy()
            # Try to attach timestamp
            if "lastSyncedTime" in self.data:
                current_trip["timestamp"] = self.data["lastSyncedTime"]
            self.data["current_trip"] = current_trip
            
            flatten_keys(trip, ["tripA", "tripB"])

        # Flatten 'navigation'
        if "navigation" in data:
            nav = data["navigation"]
            self.data["navigation_status"] = nav.get("status")
            self.data["navigation_trip_plan"] = nav.get("tripPlan")
            dest = nav.get("destination", {})
            if dest:
                self.data["navigation_title"] = dest.get("title")
                self.data["navigation_arrival_time"] = dest.get("time")

        # Flatten 'subscription'
        if "subscription" in data:
            sub = data["subscription"]
            connect_plan = sub.get("connect", {})
            self.data["subscription_status"] = connect_plan.get("status")
            self.data["subscription_plan"] = connect_plan.get("plan")
            self.data["subscription_end_at"] = connect_plan.get("endAt")

        # Handle patch updates that might have come as "path/key": value (Firebase style in socket?)
        # Ather socket usually sends nested JSON objects in 'd', but sometimes keys have slashes?
        # The previous code handled "bike/speed" keys.
        # If the 'data' coming in has keys with slashes:
        for key, value in data.items():
            if "/" in key:
                parts = key.split("/")
                # This seems specific to how previous logic interpreted some messages.
                # If we assume 'data' is the 'b.d' payload, it might be a flat dict with slash keys.
                # Let's support it by expanding it into the structure.
                
                # We can use a helper to set nested item by path
                d = self.data
                for part in parts[:-1]:
                    if part not in d or not isinstance(d[part], dict):
                        d[part] = {}
                    d = d[part]
                d[parts[-1]] = value
                
                # Also do the specific flattening if it matches our interested keys
                # (This mimics the previous massive if-else block but genericaly)
                category = parts[0]
                field = parts[-1]
                
                if category == "bike" and field in [
                    "mode", "speed", "batterySOC", "predictedRange", "range", 
                    "keySwitch", "odo", "VIN", "bikeType", "otaStatus", 
                    "TheftTowMovementState", "vehicleState", "ShutdownVacationMode", 
                    "parkingAssist", "UserFacingSoftwareVersion"
                ]:
                    self.data[field] = value
                
                if category == "app" and field in ["modeRange", "features", "savings"]:
                     self.data[field] = value
                
                # Trigger ready event if important data arrived
                if field in ["features", "modeRange"]:
                     self._ready_event.set()

        # Handle root level keys that might be direct updates
        flatten_keys(data, [
            "batterySOC", "predictedRange", "speed", "mode", "lastSyncedTime"
        ])
        
        if "GPSLocation" in data:
            self._update_gps(data["GPSLocation"])
            
        if "tripSummary" in data.get("stats", {}):
            self.data["tripSummary"] = data["stats"]["tripSummary"]
        elif "stats" in data and "tripSummary" in data["stats"]: # Handle if stats came in
             pass # recursive merge handled it, just ensure data['tripSummary'] exists if accessed directly?
             # Previous code put tripSummary at root.
             self.data["tripSummary"] = self.data.get("stats", {}).get("tripSummary")

        # Capture Trip Start SOC
        current_state = self.data.get("vehicleState")
        current_soc = self.data.get("batterySOC")

        # Trip Logic: Robust Capture & Reset
        try:
             speed = float(self.data.get("speed", 0))
        except (ValueError, TypeError):
             speed = 0
             
        try:
             trip_dist = float(self.data.get("distance", 0))
             # Fallback if distance is not at root
             if trip_dist == 0:
                 trip_dist = float(self.data.get("current_trip", {}).get("distance", 0))
        except (ValueError, TypeError):
             trip_dist = 0

        # 1. Reset if trip distance is 0 (Ready for new trip)
        if trip_dist < 0.1:
             if self.data.get("trip_start_soc") is not None:
                 _LOGGER.debug("Trip reset detected (dist=0). Clearing start values.")
                 self.data["trip_start_soc"] = None
                 self.data["trip_start_altitude"] = None
        
        # 2. Lazy Capture: If moving or riding, and haven't captured yet
        # We rely on previous_state transition OR simple existence of motion/distance
        is_moving = speed > 0 or trip_dist > 0 or current_state == "riding"
        has_captured = self.data.get("trip_start_soc") is not None
        
        if is_moving and not has_captured:
            if current_soc is not None:
                self.data["trip_start_soc"] = current_soc
                _LOGGER.debug("Trip started (Lazy). Captured SOC: %s, Speed: %s, Dist: %s", current_soc, speed, trip_dist)
            
            current_altitude = self.data.get("altitude")
            if current_altitude is not None:
                self.data["trip_start_altitude"] = current_altitude
                _LOGGER.debug("Trip started (Lazy). Captured Altitude: %s", current_altitude)
        
        self._previous_state = current_state

    def _update_gps(self, gps_data):
        """Extract lat/lon."""
        if gps_data and "lat" in gps_data and "lng" in gps_data:
            self.data["lat"] = gps_data["lat"]
            self.data["lon"] = gps_data["lng"]
        if gps_data and "ALT_M" in gps_data:
            self.data["altitude"] = gps_data["ALT_M"]
        if gps_data and "Accuracy" in gps_data:
            self.data["gps_accuracy"] = gps_data["Accuracy"]

    async def async_wait_for_initial_data(self) -> None:
        """Wait for initial data to be received."""
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timed out waiting for initial data")

    def set_options(self, options):
        """Update options."""
        self.enable_raw_logging = options.get(
            CONF_ENABLE_RAW_LOGGING, DEFAULT_ENABLE_RAW_LOGGING
        )

    def _log_raw_message(self, path: str, message: str):
        """Log raw message to file (runs in executor)."""
        try:
            with open(path, "a") as f:
                f.write(f"{int(time.time() * 1000)}: {message}\n")
        except Exception as err:
            _LOGGER.error("Error writing to raw log: %s", err)
