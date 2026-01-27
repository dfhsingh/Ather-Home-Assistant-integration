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
    CONF_ENABLE_RAW_LOGGING,
    DEFAULT_ENABLE_RAW_LOGGING,
    CONF_BASE_URL,
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
        self.api_key = None
        self.user_id = None
        self.base_url = None
        self.name = "Ather"  # Default name
        self.scooter_ids = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (Mobile Number, API Key, Name)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self.mobile_no = user_input[CONF_MOBILE_NO]
            self.api_key = user_input[CONF_FIREBASE_API_KEY]
            self.name = user_input.get(CONF_NAME, "Ather")
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
                    vol.Required(CONF_FIREBASE_API_KEY): str,
                    vol.Required(CONF_NAME, default="Ather"): str,
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

                # Extract Database URL if present
                user_db = tokens.get("userDatabase", {})
                if user_db and "databaseUrl" in user_db:
                    self.base_url = user_db.get("databaseUrl")
                    # Clean the URL if it ends with /
                    if self.base_url and self.base_url.endswith("/"):
                        self.base_url = self.base_url[:-1]

                    # CRITICAL: Update the API instance with the discovered URL immediately
                    # so get_scooters uses the correct shard.
                    api.base_url = self.base_url
                    _LOGGER.info("Config Flow using Discovered Base URL: %s", self.base_url)
                else:
                    _LOGGER.warning("No databaseUrl found in OTP response. Using default: %s", api.base_url)

                _LOGGER.debug("Tokens received. API Token (Len): %s, Firebase Token (Len): %s", 
                              len(str(self.api_token)) if self.api_token else 0,
                              len(str(self.firebase_token)) if self.firebase_token else 0)

                # Fetch User ID from API (more reliable than OTP response)
                self.user_id = await api.get_user_id(self.api_token)

                if not self.user_id:
                    # Fallback to token if API fetch fails, though unlikely
                    self.user_id = tokens.get("id")

                if self.user_id:
                    # Exchange for ID Token
                    id_token = await api.get_id_token(
                        self.firebase_token, self.api_key
                    )

                    if id_token:
                        _LOGGER.debug("ID Token Exchange Successful. URL for Scooters: %s", api.base_url)
                        # Fetch Scooters
                        try:
                             self.scooter_ids = await api.get_scooters(
                                 str(self.user_id), id_token
                             )
                        except Exception as e:
                             _LOGGER.error("get_scooters failed with error: %s", e)
                             self.scooter_ids = None # ensure it falls through to error handling

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
            id_token = await api.get_id_token(self.firebase_token, self.api_key)

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
        # Use the name provided by the user (or default)
        name = self.name
        
        # We NO LONGER fetch details here to avoid 401 errors.
        # The user-provided name is the single source of truth for the title.

        await self.async_set_unique_id(scooter_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=name,
            data={
                CONF_SCOOTER_ID: scooter_id,
                CONF_FIREBASE_TOKEN: self.firebase_token,
                CONF_FIREBASE_API_KEY: self.api_key,
                "api_token": self.api_token,
                CONF_BASE_URL: self.base_url,
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
