"""Config flow for Ather Electric (Binary)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AtherAPI, CORE_AVAILABLE
from .const import (
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
    """Handle a config flow for Ather Electric (Binary)."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self.mobile_no = None
        self.api_token = None
        self.firebase_token = None
        self.id_token = None
        self.user_id = None
        self.base_url = None
        self.name = "Ather"
        self.scooter_list = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (Mobile Number, Name)."""
        errors: dict[str, str] = {}
        
        if not CORE_AVAILABLE:
            errors["base"] = "core_not_found"
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}), errors=errors)

        if user_input is not None:
            self.mobile_no = user_input[CONF_MOBILE_NO]
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
                    vol.Required(CONF_NAME, default="Ather"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle OTP Entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            otp = user_input[CONF_OTP]
            session = async_get_clientsession(self.hass)
            api = AtherAPI(session)
            tokens = await api.verify_otp(self.mobile_no, otp)

            if tokens:
                self.api_token = tokens.get("token")
                self.firebase_token = tokens.get("firebase_token")
                self.user_id = tokens.get("id")
                
                # Prioritize database URL from verify response (Shard Discovery)
                user_db = tokens.get("userDatabase", {})
                if user_db and isinstance(user_db, dict) and "databaseUrl" in user_db:
                    self.base_url = user_db.get("databaseUrl", "").rstrip("/")
                    _LOGGER.info("Discovered Shard URL: %s", self.base_url)
                
                if not self.base_url:
                    # Fallback to profile check
                    try:
                        profile = await api.get_user_profile(self.api_token)
                        if not self.user_id:
                            self.user_id = profile.get("id")
                        for k, v in profile.items():
                            if isinstance(v, str) and "firebaseio.com" in v:
                                self.base_url = v.rstrip("/")
                                break
                    except Exception as e:
                        _LOGGER.warning("Profile fetch failed, using default URL: %s", e)

                if not self.base_url:
                    self.base_url = "https://ather-production.firebaseio.com"
                
                # Synchronize URL with Rust core
                api.base_url = self.base_url

                id_token_data = await api.exchange_custom_token(self.firebase_token)
                if id_token_data:
                    self.id_token = id_token_data.get("idToken")
                    
                    # Extract the definitive User ID from the ID Token itself
                    decoded_uid = api.get_user_id_from_token(self.id_token)
                    if decoded_uid:
                        self.user_id = decoded_uid
                        _LOGGER.debug("Using User ID decoded from ID Token: %s", self.user_id)
                    
                    # Fetch Scooters - Force Main Router URL for discovery
                    try:
                        scooters = await api.get_scooters(
                            str(self.user_id), 
                            self.id_token, 
                            override_base_url="https://ather-production.firebaseio.com"
                        )
                        if scooters:
                            self.scooter_list = {}
                            for sid, s in scooters.items():
                                if isinstance(s, dict):
                                    label = f"{s.get('model_type', '450X')} ({s.get('colour', 'N/A')})"
                                else:
                                    label = sid
                                self.scooter_list[sid] = label
                            
                            if len(self.scooter_list) == 1:
                                sid = list(self.scooter_list.keys())[0]
                                return self._create_ather_entry(sid)
                            
                            return await self.async_step_select_scooter()
                        else:
                            errors["base"] = "no_scooters_found"
                    except Exception as e:
                        _LOGGER.error("Failed to fetch scooters: %s", e)
                        errors["base"] = "scooter_discovery_failed"
                else:
                    errors["base"] = "token_exchange_failed"
            else:
                errors["base"] = "invalid_otp"

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required(CONF_OTP): str}),
            errors=errors,
        )

    async def async_step_select_scooter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Scooter Selection."""
        if user_input is not None:
            return self._create_ather_entry(user_input[CONF_SCOOTER_ID])

        return self.async_show_form(
            step_id="select_scooter",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCOOTER_ID): vol.In(self.scooter_list),
                }
            ),
        )

    def _create_ather_entry(self, scooter_id: str) -> FlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self.name,
            data={
                CONF_MOBILE_NO: self.mobile_no,
                CONF_FIREBASE_TOKEN: self.firebase_token,
                "api_token": self.api_token,
                CONF_BASE_URL: self.base_url,
                CONF_NAME: self.name,
                CONF_SCOOTER_ID: scooter_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return AtherOptionsFlowHandler(config_entry)

class AtherOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
