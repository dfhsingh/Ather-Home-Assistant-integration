"""Constants for the Ather Electric (Binary) integration."""

DOMAIN = "ather_binary"

CONF_SCOOTER_ID = "scooter_id"
CONF_FIREBASE_TOKEN = "firebase_token"
CONF_FIREBASE_API_KEY = "firebase_api_key"
CONF_BASE_URL = "base_url"

# WebSocket URL
WS_URL = "wss://ather-production.firebaseio.com/.ws?v=5"

# Platforms
PLATFORMS = ["sensor", "device_tracker", "binary_sensor", "button", "switch"]

CONF_MOBILE_NO = "mobile_no"
CONF_OTP = "otp"

# API URLs
BASE_URL = "https://ather-production.firebaseio.com"

CONF_ENABLE_RAW_LOGGING = "enable_raw_logging"
DEFAULT_ENABLE_RAW_LOGGING = False

CONF_RIDE_RETENTION_MONTHS = "ride_retention_months"
DEFAULT_RIDE_RETENTION_MONTHS = 13

# TSDB Configuration
CONF_ATHER_TSDB_URL = "ather_tsdb_url"
CONF_ATHER_TSDB_TYPE = "ather_tsdb_type"
TSDB_TYPE_VICTORIAMETRICS = "victoriametrics"
