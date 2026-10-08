import requests
import time
import datetime
import threading
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass


# ─── Configuration ───────────────────────────────────────────────────────────
TURN_KEY_ID = os.environ.get('TURN_KEY_ID')
TURN_KEY_API_TOKEN = os.environ.get('TURN_KEY_API_TOKEN')
CLOUDFLARE_API_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN')
ACCOUNT_ID = os.environ.get('ACCOUNT_ID')

TURN_API_BASE = "https://rtc.live.cloudflare.com/v1/turn"
GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

FREE_TIER_GB = 1000          # 1,000 GB free per month
USAGE_THRESHOLD_PCT = 0.10    # % of free tier
POLL_INTERVAL_SEC = 60        # how often to check usage while credentials are live
CREDENTIAL_TTL_SEC = 3600     # 1 hour default TTL for generated credentials


def get_usage_gb():
    """
    Query the GraphQL Analytics API for total TURN egressBytes over
    the last 31 days.  Returns usage in GB (float).

    Uses callsTurnUsageAdaptiveGroups as documented in the Realtime TURN
    analytics docs.  A single aggregate query (limit: 1, no dimensions)
    is used — this is the approach Cloudflare recommends to avoid
    adaptive-sampling inaccuracies.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(days=31)

    query = """
    query TurnUsage($accountTag: String!, $datetimeStart: String!, $datetimeEnd: String!) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          callsTurnUsageAdaptiveGroups(
            limit: 1
            filter: {
              datetimeMinute_geq: $datetimeStart
              datetimeMinute_lt:  $datetimeEnd
            }
          ) {
            sum {
              egressBytes
            }
          }
        }
      }
    }
    """

    resp = requests.post(
        GRAPHQL_URL,
        headers={
            "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "variables": {
                "accountTag": ACCOUNT_ID,
                "datetimeStart": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "datetimeEnd": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        },
    )
    resp.raise_for_status()
    data = resp.json()

    groups = (
        data["data"]["viewer"]["accounts"][0]
        .get("callsTurnUsageAdaptiveGroups", [])
    )
    if not groups:
        return 0.0

    egress_bytes = groups[0]["sum"].get("egressBytes", 0) or 0
    return egress_bytes / (1024 ** 3)  # bytes → GB


def usage_exceeds_threshold():
    """Return True if current month's TURN usage >= x% of the free tier."""
    used_gb = get_usage_gb()
    limit_gb = FREE_TIER_GB * USAGE_THRESHOLD_PCT
    print(f"[usage] {used_gb:.2f} GB used / {limit_gb:.0f} GB threshold")
    return used_gb >= limit_gb


def generate_ice_servers(ttl=CREDENTIAL_TTL_SEC):
    """
    Generate a TURN credential and return the iceServers JSON.

    Before generating, checks current usage.  If usage has already reached
    90% of the free tier, raises RuntimeError and does NOT generate new
    credentials.
    """
    if usage_exceeds_threshold():
        raise RuntimeError(
            "TURN usage limit reached. "
            "Refusing to generate new credentials."
        )

    resp = requests.post(
        f"{TURN_API_BASE}/keys/{TURN_KEY_ID}/credentials/generate-ice-servers",
        headers={
            "Authorization": f"Bearer {TURN_KEY_API_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"ttl": ttl},
    )
    resp.raise_for_status()
    return resp.json()


def revoke_credential(username):
    """Revoke a single TURN credential by username."""
    resp = requests.post(
        f"{TURN_API_BASE}/keys/{TURN_KEY_ID}/credentials/{username}/revoke",
        headers={"Authorization": f"Bearer {TURN_KEY_API_TOKEN}"},
    )
    resp.raise_for_status()
    print(f"[revoke] Revoked credential for username: {username}")


def revoke_all_credentials(usernames):
    """Revoke every credential in the provided set of usernames."""
    for username in usernames:
        try:
            revoke_credential(username)
        except requests.HTTPError as e:
            print(f"[revoke] Failed to revoke {username}: {e}")


def extract_usernames(ice_servers_json):
    """
    Extract TURN usernames from the generate-ice-servers response.
    Only entries with a 'username' field are TURN (not STUN).
    """
    usernames = []
    for server in ice_servers_json.get("iceServers", []):
        if "username" in server:
            usernames.append(server["username"])
    return usernames


def monitor_and_revoke(usernames, expiry_time):
    """
    Background loop: poll usage until credentials expire.  If usage
    reaches x % of the free tier, immediately revoke all credentials.
    """
    while datetime.datetime.now(datetime.timezone.utc) < expiry_time:
        if usage_exceeds_threshold():
            print(f"[guard] threshold reached — revoking all credentials!")
            revoke_all_credentials(usernames)
            return
        time.sleep(POLL_INTERVAL_SEC)

    print("[monitor] Credentials expired naturally; no revocation needed.")


def get_turn_credentials(ttl=CREDENTIAL_TTL_SEC):
    """
    Main entry point.

    1. Check usage — refuse to generate if >= xx% of free tier.
    2. Generate ICE servers (TURN credentials).
    3. Start a background thread that monitors usage until the
       credentials' TTL expires.  If usage hits xx%, all credentials
       are revoked immediately.
    4. Return the iceServers JSON to the caller.

    Returns the iceServers dict (pass directly to RTCPeerConnection).
    Raises RuntimeError if the usage threshold is already exceeded.
    """
    # Step 1 + 2: generate (or refuse)
    ice_servers_json = generate_ice_servers(ttl)

    # Step 3: extract usernames for potential revocation
    usernames = extract_usernames(ice_servers_json)
    expiry_time = datetime.datetime.now(datetime.timezone.utc) + \
        datetime.timedelta(seconds=ttl)

    # Step 4: start monitoring in the background
    monitor_thread = threading.Thread(
        target=monitor_and_revoke,
        args=(usernames, expiry_time),
        daemon=True,
    )
    monitor_thread.start()

    # Step 5: return the iceServers JSON
    return ice_servers_json


# ─── Usage example ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ice_servers = get_turn_credentials(ttl=3600)
        print("ICE servers:")
        import json
        print(json.dumps(ice_servers, indent=2))
    except RuntimeError as e:
        print(f"Refused: {e}")
