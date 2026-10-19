#!/usr/bin/env python3
"""One-time helper: turn a short-lived Graph API Explorer token into a long-lived Page token
and find the linked Instagram account. Saves META_PAGE_ID, META_PAGE_TOKEN and IG_USER_ID to .env.

    python3 meta_setup.py --user-token EAAB...

Needs META_APP_ID and META_APP_SECRET in .env first (Meta app dashboard -> App settings -> Basic).
"""
from __future__ import annotations

import argparse
from datetime import datetime

from uploaders.common import load_env, need, request, save_env
from uploaders.meta import graph

NEEDED_SCOPES = {"pages_show_list", "pages_read_engagement", "pages_manage_posts",
                 "pages_manage_engagement", "instagram_basic", "instagram_content_publish",
                 "instagram_manage_comments"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-token", required=True, help="token from the Graph API Explorer")
    ap.add_argument("--page", help="Page name, if you manage more than one")
    args = ap.parse_args(argv)

    load_env()
    app_id, secret = need("META_APP_ID"), need("META_APP_SECRET")
    g = graph()

    long_lived = request("GET", f"{g}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
        "fb_exchange_token": args.user_token}).json()["access_token"]

    pages = request("GET", f"{g}/me/accounts", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "access_token": long_lived}).json().get("data", [])
    if not pages:
        print("No Facebook Pages found for this token. Make sure you ticked the Page "
              "(and the Instagram account) when the permission dialog appeared.")
        return 1
    if args.page:
        pages = [p for p in pages if p["name"].lower() == args.page.lower()]
    if len(pages) != 1:
        print("Several Pages found - rerun with --page \"<name>\":")
        for p in pages:
            print("  -", p["name"])
        return 1

    page = pages[0]
    save_env("META_PAGE_ID", page["id"])
    save_env("META_PAGE_TOKEN", page["access_token"])
    print(f"Facebook Page: {page['name']} ({page['id']})")

    ig = page.get("instagram_business_account")
    if ig:
        save_env("IG_USER_ID", ig["id"])
        print(f"Instagram:     @{ig.get('username')} ({ig['id']})")
    else:
        print("WARNING: no Instagram account is linked to this Page. In Instagram: Settings -> "
              "Account type and tools -> switch to Professional, then link it to the Page.")

    info = request("GET", f"{g}/debug_token", params={
        "input_token": page["access_token"], "access_token": f"{app_id}|{secret}"}
    ).json().get("data", {})
    expires = info.get("expires_at", 0)
    print("Page token:    does not expire" if not expires
          else f"Page token:    expires {datetime.fromtimestamp(expires):%Y-%m-%d}")
    missing = NEEDED_SCOPES - set(info.get("scopes", []))
    if missing:
        print("WARNING: the token is missing permissions: " + ", ".join(sorted(missing)))
    print("Saved to .env. Next: python3 publish_daily.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
