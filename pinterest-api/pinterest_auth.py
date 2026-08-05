"""One-time OAuth 2.0 authorization for the Obenpaper_Scheduler Pinterest app.

Run once:  python pinterest_auth.py

Opens the Pinterest consent screen in your browser, catches the redirect on
localhost:8085, exchanges the code for tokens, and writes token.json.

NOTE (demo video): the consent screen shown by this script is the shot the
Pinterest Standard-access review needs. If you have already authorized this
app, revoke it first (Pinterest > Settings > Security > Apps with access)
or the consent screen will be skipped.
"""

import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from pinterest_common import (
    TOKEN_URL,
    basic_auth_header,
    load_config,
    save_token,
)

AUTH_URL = "https://www.pinterest.com/oauth/"

SCOPES = [
    "boards:read",
    "boards:write",
    "pins:read",
    "pins:write",
    "user_accounts:read",
]

_received = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (name fixed by BaseHTTPRequestHandler)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        _received["code"] = params.get("code", [None])[0]
        _received["state"] = params.get("state", [None])[0]
        _received["error"] = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if _received["code"]:
            body = "<h2>Authorized.</h2><p>You can close this tab and return to the terminal.</p>"
        else:
            body = "<h2>Authorization failed.</h2><p>Check the terminal for details.</p>"
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass  # keep the terminal clean for the recording


def main():
    cfg = load_config()
    state = "obenpaper-" + str(abs(hash(cfg["client_id"])) % 10**8)

    query = urllib.parse.urlencode(
        {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": ",".join(SCOPES),
            "state": state,
        }
    )
    consent_url = f"{AUTH_URL}?{query}"

    parsed_redirect = urllib.parse.urlparse(cfg["redirect_uri"])
    port = parsed_redirect.port or 8085

    server = HTTPServer(("localhost", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Requesting scopes: {', '.join(SCOPES)}")
    print(f"Listening for the redirect on {cfg['redirect_uri']}")
    print("Opening the Pinterest consent screen in your browser...")
    print(consent_url)
    webbrowser.open(consent_url)

    thread.join(timeout=300)
    server.server_close()

    if _received.get("error"):
        sys.exit(f"Pinterest returned an error: {_received['error']}")
    if not _received.get("code"):
        sys.exit("No authorization code received (timed out after 5 minutes).")
    if _received.get("state") != state:
        sys.exit("State mismatch — aborting rather than exchanging the code.")

    print("Authorization code received. Exchanging for tokens...")

    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": basic_auth_header(cfg),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": _received["code"],
            "redirect_uri": cfg["redirect_uri"],
        },
        timeout=30,
    )

    if resp.status_code != 200:
        sys.exit(f"Token exchange failed ({resp.status_code}): {resp.text}")

    payload = resp.json()
    save_token(payload)

    print("\ntoken.json written (file permissions 600).")
    print(f"  granted scope : {payload.get('scope', '(not returned)')}")
    print(f"  expires_in    : {payload.get('expires_in')} seconds")
    print(f"  refresh token : {'present' if payload.get('refresh_token') else 'MISSING'}")
    print("\nNext: python pinterest_boards.py")


if __name__ == "__main__":
    main()
