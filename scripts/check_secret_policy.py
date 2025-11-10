import os
import sys
from datetime import datetime, timezone

MAX_AGE_DAYS = int(os.getenv("SECRET_MAX_TTL_DAYS", "90"))


def parse_date(value: str):
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def main():
    rotated_at = os.getenv("SECRET_KEY_ROTATED_AT")
    if not rotated_at:
        print("INFO: SECRET_KEY_ROTATED_AT not set; skipping TTL check.")
        return 0
    ts = parse_date(rotated_at)
    if not ts:
        sys.stderr.write(
            "ERROR: SECRET_KEY_ROTATED_AT has invalid format; expected YYYY-MM-DD or ISO8601.\n"
        )
        return 1
    age_days = (datetime.now(timezone.utc) - ts).days
    if age_days > MAX_AGE_DAYS:
        sys.stderr.write(
            f"ERROR: SECRET_KEY is older than {MAX_AGE_DAYS} days ({age_days}d). Rotate it.\n"
        )
        return 1
    print("OK: SECRET_KEY within TTL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
