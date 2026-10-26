"""Show the DataForSEO account balance and whether the Backlinks API subscription is active (free call)."""
from __future__ import annotations

from common import DataForSEO, DataForSEOError, first_result, setup_console


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found is not None:
                return found
    return None


def main():
    setup_console()
    try:
        t = DataForSEO().get("appendix/user_data", label="balance")
    except DataForSEOError as e:
        raise SystemExit(f"credentials problem: {e}")
    r = first_result(t)
    print(f"login: {r.get('login')}")
    print(f"balance: ${find_key(r, 'balance')}")
    sub = r.get("backlinks_subscription_expiry_date")
    print(f"backlinks subscription: {'active until ' + sub if sub else 'NOT active (backlink checks will be skipped)'}")


if __name__ == "__main__":
    main()
