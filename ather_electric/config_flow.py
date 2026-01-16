"""Config flow for Ather Electric."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_FIREBASE_API_KEY,
    CONF_FIREBASE_TOKEN,
    CONF_MOBILE_NO,
    CONF_OTP,
    CONF_SCOOTER_ID,
    DOMAIN,
    FIREBASE_API_KEY,
)

_LOGGER = logging.getLogger(__name__)


class AtherAuth:
    """Helper class for Ather Authentication."""

    GENERATE_OTP_URL = "https://cerberus.ather.io/auth/v2/generate-login-otp"
    VERIFY_OTP_URL = "https://cerberus.ather.io/auth/v2/verify-login-otp"
    FIREBASE_DB_URL = "https://ather-production-mu.firebaseio.com"

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Source": "ATHER_APP/11.3.0",
        "User-Agent": "Ktor client",
    }

    def __init__(self, session: aiohttp.ClientSession):
        """Initialize."""
        self.session = session

    async def generate_otp(self, phone_number: str) -> bool:
        """Generate OTP."""
        payload = {"email": "", "contact_no": phone_number, "country_code": "IN"}
        try:
            async with self.session.post(
                self.GENERATE_OTP_URL, json=payload, headers=self.HEADERS
            ) as resp:
                if resp.status == 200:
                    return True
                _LOGGER.error("Generate OTP failed: %s", await resp.text())
        except Exception as e:
            _LOGGER.error("Error generating OTP: %s", e)
        return False

    async def verify_otp(self, phone_number: str, otp: str) -> dict | None:
        """Verify OTP and return tokens."""
        payload = {
            "email": "",
            "contact_no": phone_number,
            "userOtp": otp,
            "is_mobile_login": "true",
            "country_code": "IN",
        }
        try:
            async with self.session.post(
                self.VERIFY_OTP_URL, json=payload, headers=self.HEADERS
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                _LOGGER.error("Verify OTP failed: %s", await resp.text())
        except Exception as e:
            _LOGGER.error("Error verifying OTP: %s", e)
        return None

    async def get_id_token(self, custom_token: str, api_key: str) -> str | None:
        """Exchange Custom Token for ID Token."""
        url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken?key={api_key}"
        payload = {"token": custom_token, "returnSecureToken": True}
        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("idToken")
                _LOGGER.error("Token Exchange failed: %s", await resp.text())
        except Exception as e:
            _LOGGER.error("Error exchanging token: %s", e)
        return None

    async def get_user_id(self, token: str) -> str | None:
        """Fetch User ID from Profile."""
        url = "https://cerberus.ather.io/api/v1/me"
        headers = self.HEADERS.copy()
        headers["Authorization"] = f"Bearer {token}"
        try:
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return str(data.get("id"))
                _LOGGER.error("Get Profile failed: %s", await resp.text())
        except Exception as e:
            _LOGGER.error("Error getting profile: %s", e)
        return None

    async def get_scooters(self, user_id: str, id_token: str) -> list[str] | None:
        """Fetch scooter IDs from Firebase."""
        url = f"{self.FIREBASE_DB_URL}/users/{user_id}/scooters.json?auth={id_token}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return list(data.keys())
                    _LOGGER.warning("No scooters found in %s data: %s", url, data)
                    return []
                _LOGGER.error("Get Scooters failed: %s", await resp.text())
        except Exception as e:
            _LOGGER.error("Error getting scooters: %s", e)
        return None

    async def get_scooter_details(self, scooter_id: str, id_token: str) -> dict | None:
        """Fetch details for a specific scooter."""
        url = f"{self.FIREBASE_DB_URL}/scooters/{scooter_id}.json?auth={id_token}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            _LOGGER.error("Error getting scooter details: %s", e)
        return None


class AtherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ather Electric."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self.mobile_no = None
        self.api_token = None
        self.firebase_token = None
        self.user_id = None
        self.scooter_ids = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (Mobile Number, Name)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self.mobile_no = user_input[CONF_MOBILE_NO]
            session = async_get_clientsession(self.hass)
            auth = AtherAuth(session)
            if await auth.generate_otp(self.mobile_no):
                return await self.async_step_otp()
            errors["base"] = "otp_generation_failed"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MOBILE_NO): str,
                    vol.Optional(CONF_NAME, default="Ather Scooter"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle OTP Entry and Auto-Discovery."""
        errors: dict[str, str] = {}
        if user_input is not None:
            otp = user_input[CONF_OTP]
            session = async_get_clientsession(self.hass)
            auth = AtherAuth(session)
            tokens = await auth.verify_otp(self.mobile_no, otp)

            if tokens:
                self.api_token = tokens.get("token")
                self.firebase_token = tokens.get("firebase_token")

                # Fetch User ID from API (more reliable than OTP response)
                self.user_id = await auth.get_user_id(self.api_token)

                if not self.user_id:
                    # Fallback to token if API fetch fails, though unlikely
                    self.user_id = tokens.get("id")

                if self.user_id:
                    # Exchange for ID Token
                    id_token = await auth.get_id_token(
                        self.firebase_token, FIREBASE_API_KEY
                    )

                    if id_token:
                        # Fetch Scooters
                        self.scooter_ids = await auth.get_scooters(
                            str(self.user_id), id_token
                        )

                        if not self.scooter_ids:
                            errors["base"] = "no_vehicles_found"
                        elif len(self.scooter_ids) == 1:
                            # Auto-select
                            return await self.async_create_entry_from_scooter(
                                auth, self.scooter_ids[0], id_token
                            )
                        else:
                            # Multiple scooters
                            return await self.async_step_select_vehicle()
                    else:
                        errors["base"] = "token_exchange_failed"
                else:
                    errors["base"] = "user_id_fetch_failed"
            else:
                errors["base"] = "invalid_otp"

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required(CONF_OTP): str}),
            errors=errors,
        )

    async def async_step_select_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Vehicle Selection if multiple exist."""
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            auth = AtherAuth(session)

            # Re-getting ID token might be needed if step took too long
            id_token = await auth.get_id_token(self.firebase_token, FIREBASE_API_KEY)

            return await self.async_create_entry_from_scooter(
                auth, user_input[CONF_SCOOTER_ID], id_token
            )

        return self.async_show_form(
            step_id="select_vehicle",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCOOTER_ID): vol.In(self.scooter_ids)}
            ),
        )

    async def async_create_entry_from_scooter(
        self, auth: AtherAuth, scooter_id: str, id_token: str
    ):
        """Create the config entry."""
        # Try to fetch details for cleaner name
        details = await auth.get_scooter_details(scooter_id, id_token)
        name = "Ather Scooter"
        if details:
            model = details.get("model", "")
            vin = details.get("vin", "")
            if model:
                name = f"Ather {model.upper()}"

        await self.async_set_unique_id(scooter_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=name,
            data={
                CONF_SCOOTER_ID: scooter_id,
                CONF_FIREBASE_TOKEN: self.firebase_token,
                CONF_FIREBASE_API_KEY: FIREBASE_API_KEY,
                "api_token": self.api_token,
                CONF_NAME: name,
            },
        )
