#!/usr/bin/env python3
"""One-time YouTube sign-in. Opens your browser, you approve access, and the refresh token
is saved to .env as YOUTUBE_REFRESH_TOKEN. Run it on a computer with a browser.

Needs YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first (Google Cloud -> Credentials ->
OAuth client ID of type "Desktop app").
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import urllib.parse
import webbrowser

from uploaders.common import load_env, need, request, save_env
from uploaders.youtube import SCOPES, TOKEN_URL

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def main() -> int:
    load_env()
    client_id, client_secret = need("YOUTUBE_CLIENT_ID"), need("YOUTUBE_CLIENT_SECRET")

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in query and query.get("state", [""])[0] == state:
                result["code"] = query["code"][0]
                body, status = b"Done - you can close this tab and go back to the terminal.", 200
            elif "error" in query or "code" in query:
                result["error"] = query.get("error", ["state mismatch"])[0]
                body, status = b"Authorization failed - see the terminal.", 400
            else:
                body, status = b"", 404  # e.g. favicon requests
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Opening your browser. If nothing opens, paste this link into it:\n\n" + url + "\n")
    webbrowser.open(url)
    while not result:
        server.handle_request()
    server.server_close()

    if "error" in result:
        print("Sign-in failed:", result["error"])
        return 1

    tokens = request("POST", TOKEN_URL, data={
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
        "code_verifier": verifier}).json()
    refresh = tokens.get("refresh_token")
    if not refresh:
        print("Google did not return a refresh token. Remove this app at "
              "myaccount.google.com/permissions and run the script again.")
        return 1
    save_env("YOUTUBE_REFRESH_TOKEN", refresh)

    try:  # confirm which channel the uploads will go to
        channel = request("GET", "https://www.googleapis.com/youtube/v3/channels",
                          params={"part": "snippet", "mine": "true"},
                          headers={"Authorization": f"Bearer {tokens['access_token']}"}
                          ).json()["items"][0]["snippet"]["title"]
        print(f"Signed in. Uploads will go to the channel: {channel}")
    except Exception:
        print("Signed in.")
    print("Saved YOUTUBE_REFRESH_TOKEN to .env. Next: python3 publish_daily.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
