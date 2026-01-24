import json

log_file_path = "private/ather_ws_debug.log"


def verify_log_structure(file_path):
    count_total_d_b_d = 0
    count_with_last_synced = 0
    count_valid_format = 0

    with open(file_path, "r") as f:
        for line in f:
            try:
                if ": {" not in line:
                    continue

                parts = line.split(": ", 1)
                json_str = parts[1]
                data = json.loads(json_str)

                # We are looking for structure: {"t": "d", "d": {"b": {"d": { ... }}}}
                # And usually "p" ending in "scooters/..." or similar, not necessarily nested detail.

                if data.get("t") == "d":
                    d_body = data.get("d", {})
                    b_body = d_body.get("b", {})

                    real_data = b_body.get("d")

                    if isinstance(real_data, dict):
                        count_total_d_b_d += 1

                        if "lastSyncedTime" in real_data:
                            count_with_last_synced += 1
                            val = real_data["lastSyncedTime"]
                            # Check if int/float and looks like ms timestamp (around 1.7e12)
                            if isinstance(val, (int, float)) and val > 1600000000000:
                                count_valid_format += 1
                            else:
                                print(
                                    f"Invalid format or value for lastSyncedTime: {val}"
                                )
                        else:
                            # Print a sample of what keys ARE there, to see if we miss it often
                            # Only print first few misses to avoid spam
                            if count_total_d_b_d - count_with_last_synced < 5:
                                print(
                                    f"Missing lastSyncedTime. Keys present: {list(real_data.keys())}"
                                )

            except Exception:
                continue

    print("-" * 30)
    print(f"Total data messages (d:b:d): {count_total_d_b_d}")
    print(f"Messages with 'lastSyncedTime': {count_with_last_synced}")
    print(f"Valid Millisecond Timestamps: {count_valid_format}")

    if count_with_last_synced > 0:
        percent = (count_with_last_synced / count_total_d_b_d) * 100
        print(f"Presence Percentage: {percent:.2f}%")

    return count_with_last_synced > 0


verify_log_structure(log_file_path)
