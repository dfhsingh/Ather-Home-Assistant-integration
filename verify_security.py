import sys
from unittest.mock import MagicMock

# MOCK EVERYTHING before importing checking code
mock_vol = MagicMock()
sys.modules["voluptuous"] = mock_vol

mock_hass = MagicMock()
sys.modules["homeassistant"] = mock_hass
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.typing"] = MagicMock()
sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()
sys.modules["homeassistant.loader"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["homeassistant.util.dt"] = MagicMock()
sys.modules["aiohttp"] = MagicMock()

# Now we can safely add path and import
sys.path.append("/Volumes/data/DEV/ather/custom_components")

import asyncio
import logging
import json
import time
import os
from unittest.mock import AsyncMock

from ather_electric.coordinator import AtherCoordinator

# Setup basic logging to stdout
logging.basicConfig(level=logging.INFO)


async def test_rate_limiting():
    print("\n--- Testing Rate Limiting ---")
    mock_hass_inst = MagicMock()
    mock_hass_inst.loop = asyncio.get_event_loop()
    mock_hass_inst.config.path = lambda x: x

    coord = AtherCoordinator(mock_hass_inst, "123", "token", "key", "MyScooter")
    coord.api = MagicMock()
    coord.api.send_put_request = AsyncMock(return_value=True)
    coord.get_id_token = AsyncMock(return_value="mock_token")

    # First call - should succeed
    print("Call 1: Ping")
    await coord.async_ping_scooter()

    # Second call immediate - should be blocked (using internal var check)
    print("Call 2: Ping (Immediate)")
    await coord.async_ping_scooter()

    # Verify warnings in output later, but for now relying on execution flow without crash
    # To truly verify, we'd check if send_put_request was called only once.
    print(f"API Call Count: {coord.api.send_put_request.call_count}")
    if coord.api.send_put_request.call_count == 1:
        print("SUCCESS: Rate limit blocked second call")
    else:
        print("FAILURE: Rate limit did not block")

    # Wait 31s (simulated)
    print("Simulating 31s wait...")
    coord._last_remote_command_time = time.time() - 31

    # Third call - should succeed
    print("Call 3: Ping (After wait)")
    await coord.async_ping_scooter()

    print(f"API Call Count: {coord.api.send_put_request.call_count}")
    if coord.api.send_put_request.call_count == 2:
        print("SUCCESS: Rate limit allowed call after delay")
    else:
        print("FAILURE: Rate limit did not allow call after delay")


async def test_log_redaction():
    print("\n--- Testing Log Redaction ---")
    mock_hass_inst = MagicMock()
    coord = AtherCoordinator(mock_hass_inst, "123", "token", "key", "MyScooter")
    test_file = "test_redaction.log"

    sensitive_data = {
        "t": "d",
        "d": {
            "b": {
                "d": {
                    "token": "SECRET_TOKEN_123",
                    "lat": 12.9716,
                    "lng": 77.5946,
                    "speed": 45,
                }
            }
        },
    }

    coord._log_raw_message(test_file, json.dumps(sensitive_data))

    with open(test_file, "r") as f:
        content = f.read()
        print("Log Content:", content.strip())

        if "***REDACTED***" in content and "SECRET_TOKEN_123" not in content:
            print("SUCCESS: Token redacted")
        else:
            print("FAILURE: Token NOT redacted properly")

        if "12.9716" not in content:
            print("SUCCESS: Location redacted")
        else:
            print("FAILURE: Location NOT redacted")

    # Clean up
    if os.path.exists(test_file):
        os.remove(test_file)


async def main():
    await test_rate_limiting()
    await test_log_redaction()


if __name__ == "__main__":
    asyncio.run(main())
