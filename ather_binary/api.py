import platform
import logging
import os
import sys
import asyncio

_LOGGER = logging.getLogger(__name__)

# Determine OS and Architecture
os_type = platform.system().lower()
machine = platform.machine().lower()

if os_type == "darwin":
    os_name = "macos"
elif os_type == "linux":
    os_name = "linux"
else:
    os_name = None

if machine in ["aarch64", "arm64"]:
    arch_name = "aarch64"
elif machine in ["x86_64", "amd64"]:
    arch_name = "x86_64"
else:
    arch_name = None

# Try to load the binary core
CORE_AVAILABLE = False
if os_name and arch_name:
    arch_dir = f"{os_name}-{arch_name}"
    binary_path = os.path.join(os.path.dirname(__file__), "bin", arch_dir)
    
    if os.path.exists(binary_path):
        if binary_path not in sys.path:
            sys.path.append(binary_path)
        try:
            import ather_core
            CORE_AVAILABLE = True
            _LOGGER.info("Loaded Ather Core binary for %s", arch_dir)
        except ImportError as e:
            _LOGGER.error("Failed to import Ather Core for %s: %s", arch_dir, e)
    else:
        # Fallback to local directory
        local_dir = os.path.dirname(__file__)
        if local_dir not in sys.path:
            sys.path.append(local_dir)
        try:
            import ather_core
            CORE_AVAILABLE = True
        except ImportError:
            pass

if not CORE_AVAILABLE:
    _LOGGER.warning("Ather Core binary not found for platform %s-%s. Please compile the Rust core.", os_type, machine)

class AtherAuthError(Exception):
    """Exception to indicate an authentication error."""

class AtherAPI:
    def __init__(self, session, base_url="https://ather-production.firebaseio.com"):
        self.session = session
        self._base_url = base_url
        if CORE_AVAILABLE:
            self.core = ather_core.AtherCore(base_url)
        else:
            self.core = None

    @property
    def base_url(self):
        return self._base_url

    @base_url.setter
    def base_url(self, value):
        self._base_url = value
        if self.core:
            self.core.set_base_url(value)

    async def _run_in_executor(self, func, *args):
        """Helper to run synchronous Rust methods in executor."""
        if not self.core:
            _LOGGER.error("Ather Core binary not available")
            return None
        return await asyncio.get_event_loop().run_in_executor(None, func, *args)

    async def generate_otp(self, phone_number):
        return await self._run_in_executor(self.core.generate_otp, phone_number)

    async def verify_otp(self, phone_number, otp):
        return await self._run_in_executor(self.core.verify_otp, phone_number, otp)

    async def exchange_custom_token(self, custom_token, api_key=None):
        # api_key is now embedded in the binary
        return await self._run_in_executor(self.core.get_id_token, custom_token)

    async def refresh_id_token(self, refresh_token, api_key=None):
        return await self._run_in_executor(self.core.refresh_id_token, refresh_token)

    async def get_user_profile(self, api_token):
        profile = await self._run_in_executor(self.core.get_user_profile, api_token)
        if profile is None:
            raise AtherAuthError("Failed to fetch user profile (Auth Error)")
        return profile

    async def get_scooters(self, user_id, id_token, override_base_url=None):
        scooters = await self._run_in_executor(self.core.get_scooters, user_id, id_token, override_base_url)
        if scooters is None:
            raise AtherAuthError("Failed to fetch scooters (Auth Error)")
        return scooters

    async def get_scooter_details(self, scooter_id, id_token):
        details = await self._run_in_executor(self.core.get_scooter_details, scooter_id, id_token)
        if details is None:
            raise AtherAuthError("Failed to fetch scooter details (Auth Error)")
        return details

    async def send_put_request(self, path, data, id_token):
        return await self._run_in_executor(self.core.send_put_request, path, data, id_token)

    async def fetch_rides(self, scooter_id, api_token, limit=10):
        rides = await self._run_in_executor(self.core.fetch_rides, scooter_id, api_token, limit)
        return rides

    def get_user_id_from_token(self, token):
        """Decode UID from JWT token without validation (same as old integration)."""
        import base64
        import json
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            payload_b64 = parts[1]
            padding = "=" * (4 - (len(payload_b64) % 4))
            if len(padding) == 4:
                padding = ""
            
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
            return payload.get("user_id") or payload.get("sub")
        except Exception:
            return None
