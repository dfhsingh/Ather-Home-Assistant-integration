import json
from datetime import datetime, timezone, timedelta

log_file_path = "private/ather_ws_debug.log"


def parse_iso_z(date_str):
    # Handle "Z" for UTC
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    return datetime.fromisoformat(date_str)


def get_latest_timestamps(file_path):
    latest_updated_at = None
    latest_last_synced_time = None

    with open(file_path, "r") as f:
        for line in f:
            try:
                if ": {" not in line:
                    continue

                parts = line.split(": ", 1)
                if len(parts) < 2:
                    continue

                json_str = parts[1]
                data = json.loads(json_str)

                def find_key(obj, key):
                    if isinstance(obj, dict):
                        if key in obj:
                            return obj[key]
                        for k, v in obj.items():
                            res = find_key(v, key)
                            if res is not None:
                                return res
                    return None

                updated_at = find_key(data, "updatedAt")
                if updated_at:
                    latest_updated_at = updated_at

                last_synced = find_key(data, "lastSyncedTime")
                if last_synced:
                    latest_last_synced_time = last_synced

            except Exception as e:
                continue

    return latest_updated_at, latest_last_synced_time


updated_at_str, last_synced_ts = get_latest_timestamps(log_file_path)

print(f"Latest updatedAt: {updated_at_str}")
print(f"Latest lastSyncedTime: {last_synced_ts}")

if updated_at_str and last_synced_ts:
    try:
        updated_at_dt = parse_iso_z(updated_at_str)
        # lastSyncedTime is usually in ms
        last_synced_dt = datetime.fromtimestamp(last_synced_ts / 1000, tz=timezone.utc)

        print(f"updatedAt (DT): {updated_at_dt}")
        print(f"lastSyncedTime (DT): {last_synced_dt}")

        diff = abs((updated_at_dt - last_synced_dt).total_seconds())
        print(f"Difference in seconds: {diff}")

        if diff < 5:
            print("MATCH: Timestamps are within a few seconds.")
        else:
            print("MISMATCH: Timestamps differ significantly.")

    except Exception as e:
        print(f"Error comparing: {e}")
else:
    print("Could not find both timestamps.")
