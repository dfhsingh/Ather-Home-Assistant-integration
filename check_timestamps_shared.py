import json
from datetime import datetime, timezone

log_file_path = "private/ather_ws_debug.log"


def parse_iso_z(date_str):
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    return datetime.fromisoformat(date_str)


def analyze_timestamps(file_path):
    last_shared_diff = None
    last_shared_updated_at = None
    last_shared_last_synced = None

    with open(file_path, "r") as f:
        for line in f:
            try:
                if ": {" not in line:
                    continue

                parts = line.split(": ", 1)
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

                # Check for both in THIS message
                # Note: find_key returns the first occurrence.
                # Ideally we want them from the same context, but for now assuming uniqueness or proximity in structure.
                updated_at = find_key(data, "updatedAt")
                last_synced = find_key(data, "lastSyncedTime")

                if updated_at and last_synced:
                    ua_dt = parse_iso_z(updated_at)
                    ls_dt = datetime.fromtimestamp(last_synced / 1000, tz=timezone.utc)
                    diff = abs((ua_dt - ls_dt).total_seconds())

                    last_shared_diff = diff
                    last_shared_updated_at = ua_dt
                    last_shared_last_synced = ls_dt

            except Exception:
                continue

    if last_shared_diff is not None:
        print(f"Latest message with BOTH timestamps:")
        print(f"  updatedAt: {last_shared_updated_at}")
        print(f"  lastSyncedTime: {last_shared_last_synced}")
        print(f"  Difference: {last_shared_diff} seconds")
    else:
        print("No single message contained both timestamps.")


analyze_timestamps(log_file_path)
