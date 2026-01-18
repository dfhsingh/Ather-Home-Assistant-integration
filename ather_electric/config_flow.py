"""Config flow for Ather Electric."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AtherAPI
from .const import (
    CONF_FIREBASE_API_KEY,
    CONF_FIREBASE_TOKEN,
    CONF_MOBILE_NO,
    CONF_OTP,
    CONF_SCOOTER_ID,
    DOMAIN,
    FIREBASE_API_KEY,
    CONF_ENABLE_RAW_LOGGING,
    DEFAULT_ENABLE_RAW_LOGGING,
)
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)


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
            api = AtherAPI(session)
            if await api.generate_otp(self.mobile_no):
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
            api = AtherAPI(session)
            tokens = await api.verify_otp(self.mobile_no, otp)

            if tokens:
                self.api_token = tokens.get("token")
                self.firebase_token = tokens.get("firebase_token")

                # Fetch User ID from API (more reliable than OTP response)
                self.user_id = await api.get_user_id(self.api_token)

                if not self.user_id:
                    # Fallback to token if API fetch fails, though unlikely
                    self.user_id = tokens.get("id")

                if self.user_id:
                    # Exchange for ID Token
                    id_token = await api.get_id_token(
                        self.firebase_token, FIREBASE_API_KEY
                    )

                    if id_token:
                        # Fetch Scooters
                        self.scooter_ids = await api.get_scooters(
                            str(self.user_id), id_token
                        )

                        if not self.scooter_ids:
                            errors["base"] = "no_vehicles_found"
                        elif len(self.scooter_ids) == 1:
                            # Auto-select
                            return await self.async_create_entry_from_scooter(
                                api, self.scooter_ids[0], id_token
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
            api = AtherAPI(session)

            # Re-getting ID token might be needed if step took too long
            id_token = await api.get_id_token(self.firebase_token, FIREBASE_API_KEY)

            return await self.async_create_entry_from_scooter(
                api, user_input[CONF_SCOOTER_ID], id_token
            )

        return self.async_show_form(
            step_id="select_vehicle",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCOOTER_ID): vol.In(self.scooter_ids)}
            ),
        )

    async def async_create_entry_from_scooter(
        self, api: AtherAPI, scooter_id: str, id_token: str
    ):
        """Create the config entry."""
        # Try to fetch details for cleaner name
        details = await api.get_scooter_details(scooter_id, id_token)
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AtherOptionsFlowHandler(config_entry)


class AtherOptionsFlowHandler(config_entries.OptionsFlow):
    """Ather Options flow handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ENABLE_RAW_LOGGING,
                        default=self._config_entry.options.get(
                            CONF_ENABLE_RAW_LOGGING, DEFAULT_ENABLE_RAW_LOGGING
                        ),
                    ): bool,
                }
            ),
        )
