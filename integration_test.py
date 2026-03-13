#!/usr/bin/env python3
"""Integration test using a local mock HTTP server with realistic Roblox API data.

Spins up a local server that mimics the Roblox API endpoints, then runs the
crawler against it to verify the full pipeline works end-to-end.
"""

import csv
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Realistic test data based on zhangyk2010's actual groups
USER_ID = 48032694
USERNAME = "zhangyk2010"

GROUPS = {
    "12877779": {"name": "Diligent Farmer", "id": 12877779},
    "7472400": {"name": "White Dragon Studio", "id": 7472400},
    "35151383": {"name": "Anime Forge No.1", "id": 35151383},
}

now = datetime.now(timezone.utc)
recent_1 = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
recent_2 = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
recent_3 = (now - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
old_1 = (now - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
old_2 = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
old_3 = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

# Games for user zhangyk2010
USER_GAMES = [
    {"id": 100001, "name": "Diligent Farmer", "created": recent_1},
    {"id": 100002, "name": "Dragon Tycoon", "created": old_1},
    {"id": 100003, "name": "Old Test Place", "created": old_3},
]

# Games for groups
GROUP_GAMES = {
    "12877779": [
        {"id": 200001, "name": "Farmer Simulator 2026", "created": recent_2},
        {"id": 200002, "name": "Crop Wars", "created": old_2},
    ],
    "7472400": [
        {"id": 300001, "name": "Dragon Quest RPG", "created": recent_3},
        {"id": 300002, "name": "White Dragon Arena", "created": recent_1},
        {"id": 300003, "name": "Legacy Dragon Game", "created": old_1},
    ],
    "35151383": [
        {"id": 400001, "name": "Anime Forge Battlegrounds", "created": old_2},
    ],
}

# Detailed universe data (returned by /v1/games?universeIds=...)
UNIVERSE_DETAILS = {
    100001: {
        "id": 100001, "rootPlaceId": 500001, "name": "Diligent Farmer",
        "description": "Farm your way to glory!", "created": recent_1,
        "updated": recent_1, "playing": 15234, "visits": 892341000,
        "maxPlayers": 30, "genre": "Town and City",
        "creator": {"id": USER_ID, "name": USERNAME, "type": "User"},
    },
    200001: {
        "id": 200001, "rootPlaceId": 500002, "name": "Farmer Simulator 2026",
        "description": "The ultimate farming experience", "created": recent_2,
        "updated": recent_2, "playing": 5621, "visits": 23456000,
        "maxPlayers": 25, "genre": "Town and City",
        "creator": {"id": 12877779, "name": "Diligent Farmer", "type": "Group"},
    },
    300001: {
        "id": 300001, "rootPlaceId": 500003, "name": "Dragon Quest RPG",
        "description": "Epic dragon adventure", "created": recent_3,
        "updated": recent_3, "playing": 3200, "visits": 12000000,
        "maxPlayers": 50, "genre": "Adventure",
        "creator": {"id": 7472400, "name": "White Dragon Studio", "type": "Group"},
    },
    300002: {
        "id": 300002, "rootPlaceId": 500004, "name": "White Dragon Arena",
        "description": "PvP dragon battles", "created": recent_1,
        "updated": recent_1, "playing": 8900, "visits": 45000000,
        "maxPlayers": 40, "genre": "Fighting",
        "creator": {"id": 7472400, "name": "White Dragon Studio", "type": "Group"},
    },
}


class MockRobloxHandler(BaseHTTPRequestHandler):
    """Mock handler that mimics Roblox API responses."""

    def log_message(self, format, *args):
        pass  # Suppress request logging

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # GET /v1/users/{userId}
        if path == f"/v1/users/{USER_ID}":
            self._json_response({"id": USER_ID, "name": USERNAME})
            return

        # GET /v2/users/{userId}/games
        if path == f"/v2/users/{USER_ID}/games":
            self._json_response({
                "previousPageCursor": None,
                "nextPageCursor": None,
                "data": USER_GAMES,
            })
            return

        # GET /v2/groups/{groupId}/games
        for gid, games in GROUP_GAMES.items():
            if path == f"/v2/groups/{gid}/games":
                self._json_response({
                    "previousPageCursor": None,
                    "nextPageCursor": None,
                    "data": games,
                })
                return

        # GET /v1/groups/{groupId}
        for gid, info in GROUPS.items():
            if path == f"/v1/groups/{gid}":
                self._json_response(info)
                return

        # GET /v1/games?universeIds=...
        if path == "/v1/games":
            ids_str = params.get("universeIds", [""])[0]
            requested_ids = [int(x) for x in ids_str.split(",") if x.strip()]
            details = [UNIVERSE_DETAILS[uid] for uid in requested_ids if uid in UNIVERSE_DETAILS]
            self._json_response({"data": details})
            return

        self._json_response({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)

        # POST /v1/usernames/users
        if parsed.path == "/v1/usernames/users":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            usernames = body.get("usernames", [])
            results = []
            for u in usernames:
                if u.lower() == USERNAME.lower():
                    results.append({"id": USER_ID, "name": USERNAME, "requestedUsername": u})
            self._json_response({"data": results})
            return

        self._json_response({"error": "Not found"}, 404)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def run_test():
    # Start mock server
    server = HTTPServer(("127.0.0.1", 0), MockRobloxHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    print(f"Mock Roblox API running on {base}")

    # Patch crawler to use our mock server
    import crawler
    crawler.BASE_URL = base
    crawler.USERS_URL = base
    crawler.GROUPS_URL = base
    crawler.REQUEST_DELAY = 0  # no delay for tests

    # Create input CSV
    fd, input_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    fd, output_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)

    try:
        with open(input_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["type", "id"])
            writer.writerow(["user", "zhangyk2010"])       # username resolution
            writer.writerow(["group", "12877779"])          # Diligent Farmer
            writer.writerow(["group", "7472400"])           # White Dragon Studio
            writer.writerow(["group", "35151383"])          # Anime Forge No.1

        print(f"\n{'='*60}")
        print("INPUT CSV:")
        print("="*60)
        with open(input_path) as f:
            print(f.read())

        # Run the crawler
        print("="*60)
        print("CRAWLER OUTPUT:")
        print("="*60)
        original_argv = sys.argv
        sys.argv = ["crawler.py", input_path, "-o", output_path, "--days", "30"]
        try:
            crawler.main()
        finally:
            sys.argv = original_argv

        # Display results
        print(f"\n{'='*60}")
        print("OUTPUT CSV:")
        print("="*60)
        with open(output_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            print("ERROR: No results found!")
            return False

        # Print as a formatted table
        print(f"{'Name':<30} {'Owner':<25} {'Created':<12} {'Playing':>8} {'Visits':>12}")
        print("-" * 90)
        for r in rows:
            print(f"{r['name']:<30} {r['owner_name']:<25} {r['created'][:10]:<12} {r['playing']:>8} {r['visits']:>12}")

        # Assertions
        names = [r["name"] for r in rows]
        print(f"\n{'='*60}")
        print("ASSERTIONS:")
        print("="*60)

        # Should find 4 recent games
        assert len(rows) == 4, f"Expected 4 recent games, got {len(rows)}"
        print(f"  [PASS] Found {len(rows)} recent games")

        # Should include these specific games
        assert "Diligent Farmer" in names, "Missing 'Diligent Farmer'"
        assert "Farmer Simulator 2026" in names, "Missing 'Farmer Simulator 2026'"
        assert "Dragon Quest RPG" in names, "Missing 'Dragon Quest RPG'"
        assert "White Dragon Arena" in names, "Missing 'White Dragon Arena'"
        print("  [PASS] All expected recent games present")

        # Should NOT include old games
        assert "Dragon Tycoon" not in names, "'Dragon Tycoon' should be filtered out (45 days old)"
        assert "Old Test Place" not in names, "'Old Test Place' should be filtered out"
        assert "Crop Wars" not in names, "'Crop Wars' should be filtered out"
        assert "Legacy Dragon Game" not in names, "'Legacy Dragon Game' should be filtered out"
        assert "Anime Forge Battlegrounds" not in names, "'Anime Forge Battlegrounds' should be filtered out"
        print("  [PASS] All old games correctly filtered out")

        # Check owner attribution
        for r in rows:
            if r["name"] == "Diligent Farmer":
                assert r["owner_type"] == "user", f"Expected user owner, got {r['owner_type']}"
                assert r["owner_name"] == "zhangyk2010"
            if r["name"] == "White Dragon Arena":
                assert r["owner_type"] == "group"
                assert r["owner_name"] == "White Dragon Studio"
        print("  [PASS] Owner attribution correct")

        # Check game URLs
        for r in rows:
            assert r["game_url"].startswith("https://www.roblox.com/games/"), f"Bad URL: {r['game_url']}"
        print("  [PASS] Game URLs correctly formatted")

        # Check sorting (newest first)
        dates = [r["created"] for r in rows]
        assert dates == sorted(dates, reverse=True), "Results not sorted by date descending"
        print("  [PASS] Results sorted by creation date (newest first)")

        print(f"\n{'='*60}")
        print("ALL TESTS PASSED!")
        print("="*60)
        return True

    finally:
        os.unlink(input_path)
        os.unlink(output_path)
        server.shutdown()


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
