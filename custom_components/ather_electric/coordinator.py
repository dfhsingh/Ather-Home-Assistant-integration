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
from homeassistant.util import dt as dt_util
import datetime

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
        integration_version: str = "0.0.0",
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.scooter_id = scooter_id
        self.firebase_token = firebase_token
        self.api_key = api_key
        self.device_name = device_name
        # Store integration version
        self.integration_version = integration_version
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

        # Rate Limiting & Backoff
        self._last_remote_command_time = 0
        self._last_scooter_details_fetch = 0
        self._details_cache = None
        self._backoff_delay = 10  # Initial delay

        # State tracking
        self._previous_state = None

        # WebSocket URL management
        self.current_ws_url = WS_URL

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

        now = time.time()
        if now - self._last_remote_command_time < 30:
            _LOGGER.warning("Ping blocked: Rate limit (30s cooldown)")
            return
        self._last_remote_command_time = now

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

        now = time.time()
        if now - self._last_remote_command_time < 30:
            _LOGGER.warning("Remote Start/Stop blocked: Rate limit (30s cooldown)")
            return
        self._last_remote_command_time = now

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

        now = time.time()
        if now - self._last_remote_command_time < 30:
            _LOGGER.warning("Remote Shutdown blocked: Rate limit (30s cooldown)")
            return
        self._last_remote_command_time = now

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
                _LOGGER.debug(
                    "Halting coordinator loop: HAS stopping or session closed"
                )
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

                # DEBUG: Fetch User ID and Scooter List to verify account/shard
                try:
                    _LOGGER.info("DEBUG: Fetching Profile and Scooter List...")
                    uid = await self.api.get_user_id(id_token)
                    if uid:
                        scooters = await self.api.get_scooters(uid, id_token)
                        _LOGGER.info("DEBUG: User ID: %s, Scooters: %s", uid, scooters)
                except Exception as e:
                    _LOGGER.error("DEBUG: Failed to fetch profile/scooters: %s", e)

                # Fetch full state via HTTP to ensure initial freshness
                # This helps if WebSocket sends stale cached data initially.
                try:
                    current_time = time.time()
                    if (
                        self._details_cache
                        and (current_time - self._last_scooter_details_fetch) < 300
                    ):
                        _LOGGER.info("Using cached scooter details (TTL 5m)")
                        full_data = self._details_cache
                    else:
                        _LOGGER.info("Fetching full scooter state via HTTP...")
                        full_data = await self.api.get_scooter_details(
                            self.scooter_id, id_token
                        )
                        if full_data:
                            self._details_cache = full_data
                            self._last_scooter_details_fetch = current_time

                    if full_data:
                        _LOGGER.debug(
                            "HTTP Fetch successful. Keys: %s", list(full_data.keys())
                        )
                        # Log details to check for shard info
                        _LOGGER.info(
                            "DEBUG: Scooter Details Metadata: %s",
                            full_data.get("details"),
                        )
                        self._process_data(full_data)
                        self._notify_listeners()
                    else:
                        _LOGGER.warning("HTTP Fetch returned no data.")
                except Exception as httperr:
                    _LOGGER.error("HTTP Fetch failed: %s", httperr)

                async with self.session.ws_connect(self.current_ws_url) as ws:
                    self.ws = ws
                    _LOGGER.info("Connected to Ather WebSocket")
                    # Successful connection, reset backoff
                    self._backoff_delay = 10
                    self.last_update_success = True
                    self._notify_listeners()

                    # Authenticate
                    auth_payload = {
                        "t": "d",
                        "d": {"r": 1, "a": "auth", "b": {"cred": id_token}},
                    }
                    if _LOGGER.isEnabledFor(logging.DEBUG):
                        _LOGGER.debug("Sending Auth Payload")
                    await ws.send_json(auth_payload)

                    # Subscriptions
                    paths = [
                        f"/scooters/{self.scooter_id}",
                        f"/scooters/{self.scooter_id}/app",
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
                    # Exponential Backoff with Jitter
                    delay = self._backoff_delay
                    _LOGGER.info(
                        "Waiting %s seconds before reconnecting (Backoff)", delay
                    )
                    await asyncio.sleep(delay)
                    self._backoff_delay = min(300, self._backoff_delay * 2)
            except Exception as err:
                _LOGGER.error("Unexpected error in WebSocket loop: %s", err)
                self.last_update_success = False
                self._notify_listeners()
                if not self._shutdown:
                    # Exponential Backoff
                    delay = self._backoff_delay
                    _LOGGER.info(
                        "Waiting %s seconds before reconnecting (Backoff)", delay
                    )
                    await asyncio.sleep(delay)
                    self._backoff_delay = min(300, self._backoff_delay * 2)

    async def _handle_message(self, message: str):
        """Parse incoming WebSocket message."""
        try:
            if self.enable_raw_logging:
                log_path = self.hass.config.path("ather_ws_debug.log")
                await self.hass.async_add_executor_job(
                    self._log_raw_message, log_path, message
                )

            msg = json.loads(message)

            # Debug logging for message structure
            if _LOGGER.isEnabledFor(logging.DEBUG):
                t_val = msg.get("t")
                d_val = msg.get("d", {})
                a_val = d_val.get("a") if isinstance(d_val, dict) else None

                # Extract path if available
                path_val = None
                if isinstance(d_val, dict):
                    b_val = d_val.get("b")
                    if isinstance(b_val, dict):
                        path_val = b_val.get("p")

                _LOGGER.debug("RX Message: t=%s, a=%s, p=%s", t_val, a_val, path_val)

                # If we have data, log its keys to see if it's app data
                if isinstance(d_val, dict) and "b" in d_val:
                    real_data = d_val["b"].get("d")
                    if isinstance(real_data, dict):
                        _LOGGER.debug("RX Data Keys: %s", list(real_data.keys()))

            if "t" in msg:
                # Handle Control Messages (Redirects)
                if msg["t"] == "c":
                    d_data = msg.get("d", {})
                    if d_data.get("t") == "h":  # Handshake/Host redirect
                        d_inner = d_data.get("d", {})
                        new_host = d_inner.get("h")

                        if new_host:
                            new_url = f"wss://{new_host}/.ws?v=5"
                            # Append namespace (ns) parameter as we are connecting to a generic shard
                            # Namespace is usually the subdomain of the original URL (ather-production-mu)
                            new_url += "&ns=ather-production-mu"

                            if new_url != self.current_ws_url:
                                _LOGGER.info(
                                    "Received Redirect: Switching from %s to %s",
                                    self.current_ws_url,
                                    new_url,
                                )
                                self.current_ws_url = new_url
                                # Close current connection to force reconnect with new URL
                                if self.ws and not self.ws.closed:
                                    await self.ws.close()
                                return
                            else:
                                _LOGGER.debug("Redirect URL is same as current.")

            if "t" in msg and msg["t"] == "d":
                data = msg.get("d", {})
                b_body = data.get("b", {})

                # Check if it is a subscription response
                if isinstance(data, dict):
                    req_id = data.get("r")
                    status = b_body.get("s")
                    if req_id and status:
                        if _LOGGER.isEnabledFor(logging.DEBUG):
                            _LOGGER.debug(
                                "Subscription Response: r=%s, status=%s", req_id, status
                            )
                        # Mark ready if initial subscriptions succeed? (Optional, kept existing logic flow)

                if b_body and "d" in b_body:
                    real_data = b_body["d"]
                    path = b_body.get("p")
                    self._process_data(real_data, path)
                    self._notify_listeners()

                # Also try processing the whole data object, in case 'b' is missing (unlikely for Ather WS)
                elif isinstance(data, dict):
                    # Fallback without path
                    self._process_data(data)
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

    def _expand_collapsed_json(self, data: Any) -> Any:
        """Expand keys with slashes into nested dictionaries (Firebase style)."""
        if not isinstance(data, dict):
            return data

        expanded = {}
        for k, v in data.items():
            if isinstance(k, str) and "/" in k:
                # Split path: "bike/batterySOC" -> ["bike", "batterySOC"]
                parts = k.split("/")
                current_level = expanded
                for part in parts[:-1]:
                    if part not in current_level:
                        current_level[part] = {}

                    # Ensure we can traverse
                    if not isinstance(current_level[part], dict):
                        # If we hit a scalar where we need a dict, overwrite it.
                        current_level[part] = {}

                    current_level = current_level[part]

                # Set the leaf
                last_part = parts[-1]
                # Recursively expand the value too
                leaf_value = self._expand_collapsed_json(v)

                # Merge leaf if exists (careful with overwrite)
                if (
                    last_part in current_level
                    and isinstance(current_level[last_part], dict)
                    and isinstance(leaf_value, dict)
                ):
                    self._recursive_merge(current_level[last_part], leaf_value)
                else:
                    current_level[last_part] = leaf_value

            else:
                # Regular key
                processed_v = self._expand_collapsed_json(v)

                # Check for collision with expanded paths
                if k in expanded:
                    # If both are dicts, merge
                    if isinstance(expanded[k], dict) and isinstance(processed_v, dict):
                        self._recursive_merge(expanded[k], processed_v)
                    else:
                        # Overwrite (assuming strict order or simply last-write wins)
                        expanded[k] = processed_v
                else:
                    expanded[k] = processed_v

        return expanded

    def _process_data(self, data: Any, path: str = None):
        """Process and flatten data updates."""
        if not isinstance(data, dict):
            return

        # Pre-process: Expand any Firebase-style path keys (e.g. "prop/subprop": val)
        # This ensures that patches are converted to nested dicts that our candidates search can find.
        data = self._expand_collapsed_json(data)

        # Sanity Check: If entire packet is too old, drop it.
        # Check 'lastSyncedTime' field (Timestamp in milliseconds)
        last_synced_ms = data.get("lastSyncedTime")
        if last_synced_ms:
            try:
                # 1769217813472 -> Milliseconds
                last_synced_dt = datetime.datetime.fromtimestamp(
                    int(last_synced_ms) / 1000, tz=datetime.timezone.utc
                )
                if last_synced_dt:
                    now = dt_util.now()
                    diff = now - last_synced_dt
                    if diff > datetime.timedelta(hours=24):
                        _LOGGER.warning(
                            "Ignoring stale data (lastSyncedTime: %s, age: %s)",
                            last_synced_ms,
                            diff,
                        )
                        return
            except Exception as e:
                _LOGGER.warning("Failed to parse lastSyncedTime: %s", e)

        # --- Simplifed Path-Based Merging ---

        # Determine target dictionary based on path
        # If path ends in '/app', we merge into self.data['app']
        # Otherwise (root or generic), we merge into self.data

        target_dict = self.data
        if path and path.endswith("/app"):
            if "app" not in self.data:
                self.data["app"] = {}
            target_dict = self.data["app"]

        # Merge the incoming data
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Processing data for path: %s. Keys: %s", path, list(data.keys())
            )

        self._recursive_merge(target_dict, data)

        # --- Flattening Logic (Backward Compatibility) ---
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
            flatten_keys(
                bike,
                [
                    "batterySOC",
                    "predictedRange",
                    "range",
                    "speed",
                    "mode",
                    "keySwitch",
                    "VIN",
                    "odo",
                    "bikeType",
                    "otaStatus",
                    "TheftTowMovementState",
                    "vehicleState",
                    "ShutdownVacationMode",
                    "parkingAssist",
                    "UserFacingSoftwareVersion",
                ],
            )
            if "GPSLocation" in bike:
                self._update_gps(bike["GPSLocation"])

        # Flatten 'app' fields
        # Note: If path was /app, the data is now in self.data['app']
        app = self.data.get("app", {})
        if app:
            flatten_keys(app, ["modeRange", "features", "savings"])

        # Check if 'features' is now at root (from app flattening or direct) and flatten feature flags
        if "features" in self.data:
            flatten_keys(
                self.data["features"],
                [
                    "atherStackPingMyScooter",
                    "atherStackRemoteShutdown",
                    "atherStackRemoteCharging",
                ],
            )
            # Signal ready if we have the critical flags
            if "atherStackPingMyScooter" in self.data:
                self._ready_event.set()

        # Flatten 'trip' fields
        if "trip" in self.data:
            trip = self.data["trip"]
            current_trip = trip.copy()
            # Try to attach timestamp
            if "lastSyncedTime" in self.data:
                current_trip["timestamp"] = self.data["lastSyncedTime"]
            self.data["current_trip"] = current_trip

            flatten_keys(trip, ["tripA", "tripB"])

        # Flatten 'navigation'
        if "navigation" in self.data:  # Use self.data instead of just incoming data
            nav = self.data["navigation"]
            self.data["navigation_status"] = nav.get("status")
            self.data["navigation_trip_plan"] = nav.get("tripPlan")
            dest = nav.get("destination", {})
            if dest:
                self.data["navigation_title"] = dest.get("title")
                self.data["navigation_arrival_time"] = dest.get("time")

        # Flatten 'subscription'
        if "subscription" in self.data:
            sub = self.data["subscription"]
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
                    "mode",
                    "speed",
                    "batterySOC",
                    "predictedRange",
                    "range",
                    "keySwitch",
                    "odo",
                    "VIN",
                    "bikeType",
                    "otaStatus",
                    "TheftTowMovementState",
                    "vehicleState",
                    "ShutdownVacationMode",
                    "parkingAssist",
                    "UserFacingSoftwareVersion",
                ]:
                    self.data[field] = value

                if category == "app" and field in ["modeRange", "features", "savings"]:
                    self.data[field] = value

                # Trigger ready event if important data arrived
                if field in ["features", "modeRange"]:
                    self._ready_event.set()

        # Handle root level keys that might be direct updates
        flatten_keys(
            data, ["batterySOC", "predictedRange", "speed", "mode", "lastSyncedTime"]
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Post-Process Data Check: batterySOC=%s, speed=%s, odo=%s, lastSyncedTime=%s",
                self.data.get("batterySOC"),
                self.data.get("speed"),
                self.data.get("odo"),
                self.data.get("lastSyncedTime"),
            )

        if "GPSLocation" in data:
            self._update_gps(data["GPSLocation"])

        if "tripSummary" in data.get("stats", {}):
            self.data["tripSummary"] = data["stats"]["tripSummary"]
        elif (
            "stats" in data and "tripSummary" in data["stats"]
        ):  # Handle if stats came in
            pass  # recursive merge handled it, just ensure data['tripSummary'] exists if accessed directly?
            # Previous code put tripSummary at root.
            self.data["tripSummary"] = self.data.get("stats", {}).get("tripSummary")

        # Check if deep_extract found stats/tripSummary
        if "stats" in self.data and "tripSummary" in self.data["stats"]:
            self.data["tripSummary"] = self.data["stats"]["tripSummary"]

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

        # Trip Logic: Robust Capture based on State Transition
        # Analysis confirms 'riding' is always preceded by 'standby'

        # Detect Transition to Riding
        # Triggers when we enter 'riding' from any other state (usually 'standby')
        # Also handles the case where we start the integration while already 'riding' (previous known state None)
        if current_state == "riding" and self._previous_state != "riding":
            # Determine if we should capture start values
            # If previous_state is None (startup), we capture current values as best-effort start points
            # If previous_state was 'standby', this is a genuine new ride start

            _LOGGER.debug(
                "Trip Start Detected (State Transition: %s -> %s). Capturing Start Data.",
                self._previous_state,
                current_state,
            )

            if current_soc is not None:
                self.data["trip_start_soc"] = current_soc

            current_altitude = self.data.get("altitude")
            if current_altitude is not None:
                self.data["trip_start_altitude"] = current_altitude

        # Legacy/Fallback: If we somehow missed the transition but are moving and have no data
        # This helps if we didn't get the specific 'riding' packet but assume riding based on speed
        # However, with robust state logic, this is less critical, but good for safety.
        # We only do this if we are definitively moving but have no start data.
        if (
            (speed > 5 or trip_dist > 0.1)
            and self.data.get("trip_start_soc") is None
            and current_state == "riding"
        ):
            if current_soc is not None:
                self.data["trip_start_soc"] = current_soc
                _LOGGER.debug(
                    "Trip Start (Fallback): Captured SOC due to movement without existing data."
                )

        # Reset Logic: If Trip Distance resets to 0, implies manual trip reset or new logical trip A/B cycle
        # We clear the start data to allow fresh capture if needed, though the transition logic above handles overwrites.
        if (
            trip_dist < 0.1
            and self.data.get("trip_start_soc") is not None
            and current_state != "riding"
        ):
            # Only clear if NOT riding to avoid clearing valid data during a very short stop/start glitch
            _LOGGER.debug(
                "Trip Distance is 0 and not riding. Clearing trip start data."
            )
            self.data["trip_start_soc"] = None
            self.data["trip_start_altitude"] = None

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
        """Log raw message to file (runs in executor) with redaction."""
        try:
            # Redact sensitive info
            redacted_msg = message
            try:
                # Basic string replacement for common patterns to avoid full JSON parse if possible/fast
                # But JSON parse is safer for key targeting.
                msg_json = json.loads(message)

                def redact(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k in [
                                "token",
                                "idToken",
                                "refreshToken",
                                "cred",
                                "lat",
                                "lng",
                                "mobile_no",
                                "email",
                            ]:
                                obj[k] = "***REDACTED***"
                            elif isinstance(v, (dict, list)):
                                redact(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            redact(item)

                redact(msg_json)
                redacted_msg = json.dumps(msg_json)
            except Exception:
                # If parsing fails, just log it (or maybe don't log if too risky?)
                # We'll assume if it's not JSON, it might not contain structured secrets.
                pass

            with open(path, "a") as f:
                f.write(f"{int(time.time() * 1000)}: {redacted_msg}\n")
        except Exception as err:
            _LOGGER.error("Error writing to raw log: %s", err)
