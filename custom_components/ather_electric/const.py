"""Constants for the Ather Electric integration."""

DOMAIN = "ather_electric"

CONF_SCOOTER_ID = "scooter_id"
CONF_FIREBASE_TOKEN = "firebase_token"
CONF_FIREBASE_API_KEY = "firebase_api_key"

# WebSocket URL
WS_URL = "wss://ather-production-mu.firebaseio.com/.ws?v=5"

# Platforms
PLATFORMS = ["sensor", "device_tracker", "binary_sensor", "button", "switch"]

CONF_MOBILE_NO = "mobile_no"
CONF_OTP = "otp"

# API URLs
BASE_URL = "https://ather-production-mu.firebaseio.com"
GENERATE_OTP_URL = "https://cerberus.ather.io/auth/v2/generate-login-otp"
VERIFY_OTP_URL = "https://cerberus.ather.io/auth/v2/verify-login-otp"
TOKEN_VERIFY_URL = (
    "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken"
)
TOKEN_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
ME_URL = "https://cerberus.ather.io/api/v1/me"

# Headers
COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Source": "ATHER_APP/11.3.0",
    "User-Agent": "Ktor client",
}

CONF_ENABLE_RAW_LOGGING = "enable_raw_logging"
DEFAULT_ENABLE_RAW_LOGGING = False
