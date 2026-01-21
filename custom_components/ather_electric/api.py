"""API Client for Ather Electric."""

from __future__ import annotations

import logging
import aiohttp
import json

from .const import (
    BASE_URL,
    COMMON_HEADERS,
    GENERATE_OTP_URL,
    ME_URL,
    TOKEN_REFRESH_URL,
    TOKEN_VERIFY_URL,
    VERIFY_OTP_URL,
)

_LOGGER = logging.getLogger(__name__)

# Default timeout for API calls
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20)


class AtherAPI:
    """Class to handle Ather API communications."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session

    async def generate_otp(self, phone_number: str) -> bool:
        """Generate OTP for the given phone number."""
        if self._session.closed:
            return False
        payload = {"email": "", "contact_no": phone_number, "country_code": "IN"}
        try:
            async with self._session.post(
                GENERATE_OTP_URL,
                json=payload,
                headers=COMMON_HEADERS,
                timeout=DEFAULT_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    return True
                _LOGGER.error("Generate OTP failed: %s", await resp.text())
        except RuntimeError:
             return False
        except Exception as e:
            _LOGGER.error("Error generating OTP: %s", e)
        return False

    async def verify_otp(self, phone_number: str, otp: str) -> dict | None:
        """Verify OTP and return response containing tokens."""
        if self._session.closed:
            return None
        payload = {
            "email": "",
            "contact_no": phone_number,
            "userOtp": otp,
            "is_mobile_login": "true",
            "country_code": "IN",
        }
        try:
            async with self._session.post(
                VERIFY_OTP_URL,
                json=payload,
                headers=COMMON_HEADERS,
                timeout=DEFAULT_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                _LOGGER.error("Verify OTP failed: %s", await resp.text())
        except RuntimeError:
            return None
        except Exception as e:
            _LOGGER.error("Error verifying OTP: %s", e)
        return None

    async def get_id_token(self, custom_token: str, api_key: str) -> str | None:
        """Exchange Custom Token for ID Token."""
        if self._session.closed:
            return None
        url = f"{TOKEN_VERIFY_URL}?key={api_key}"
        payload = {"token": custom_token, "returnSecureToken": True}
        try:
            async with self._session.post(
                url, json=payload, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("idToken")
                _LOGGER.error("Token Exchange failed: %s", await resp.text())
        except RuntimeError:
             return None
        except Exception as e:
            _LOGGER.error("Error exchanging token: %s", e)
        return None

    async def get_user_id(self, token: str) -> str | None:
        """Fetch User ID from Profile."""
        if self._session.closed:
            return None
        headers = COMMON_HEADERS.copy()
        headers["Authorization"] = f"Bearer {token}"
        try:
            async with self._session.get(
                ME_URL, headers=headers, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return str(data.get("id"))
                _LOGGER.error("Get Profile failed: %s", await resp.text())
        except RuntimeError:
            return None
        except Exception as e:
            _LOGGER.error("Error getting profile: %s", e)
        return None

    async def get_scooters(self, user_id: str, id_token: str) -> list[str] | None:
        """Fetch scooter IDs from Firebase."""
        if self._session.closed:
            return None
        url = f"{BASE_URL}/users/{user_id}/scooters.json?auth={id_token}"
        try:
            async with self._session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return list(data.keys())
                    return []
                _LOGGER.error("Get Scooters failed: %s", await resp.text())
        except RuntimeError:
            return None
        except Exception as e:
            _LOGGER.error("Error getting scooters: %s", e)
        return None

    async def get_scooter_details(self, scooter_id: str, id_token: str) -> dict | None:
        """Fetch details for a specific scooter."""
        if self._session.closed:
            return None
        url = f"{BASE_URL}/scooters/{scooter_id}.json?auth={id_token}"
        try:
            async with self._session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json()
        except RuntimeError:
            return None
        except Exception as e:
            _LOGGER.error("Error getting scooter details: %s", e)
        return None

    async def refresh_id_token(self, refresh_token: str, api_key: str) -> dict | None:
        """Get new ID and Refresh tokens using a refresh token."""
        if self._session.closed:
            return None
        url = f"{TOKEN_REFRESH_URL}?key={api_key}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        try:
            async with self._session.post(
                url, json=payload, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    _LOGGER.warning("Token refresh failed: %s", await resp.text())
        except RuntimeError:
            return None
        except Exception as e:
            _LOGGER.error("Error refreshing token: %s", e)
        return None

    async def exchange_custom_token(
        self, firebase_token: str, api_key: str
    ) -> dict | None:
        """Exchange custom token for ID and Refresh tokens."""
        if self._session.closed:
            return None
        url = f"{TOKEN_VERIFY_URL}?key={api_key}"
        payload = {"token": firebase_token, "returnSecureToken": True}
        try:
            async with self._session.post(
                url, json=payload, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    _LOGGER.error(
                        "Custom token exchange failed: %s. The configured token may be expired.",
                        await resp.text(),
                    )
        except RuntimeError:
            return None
        except Exception as e:
            _LOGGER.error("Error exchanging custom token: %s", e)
        return None

    async def send_put_request(self, path: str, data: dict, id_token: str) -> bool:
        """Send a PUT request to Firebase."""
        if self._session.closed:
            return False
        url = f"{BASE_URL}/{path}.json?auth={id_token}"
        try:
            async with self._session.put(
                url, json=data, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info("PUT request to %s successful", path)
                    return True
                else:
                    _LOGGER.error(
                        "PUT request to %s failed: %s", path, await resp.text()
                    )
        except RuntimeError:
            return False
        except Exception as e:
            _LOGGER.error("Error sending PUT request: %s", e)
        return False
