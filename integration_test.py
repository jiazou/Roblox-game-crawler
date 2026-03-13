#!/usr/bin/env python3
"""Integration test using a local mock HTTP server with real Roblox game data.

Spins up a local server that mimics the Roblox API endpoints using real game
data sourced from zhangyk2010's actual Roblox groups and games. Then runs the
crawler against it to verify the full pipeline works end-to-end.

Real data sources:
- zhangyk2010 owns groups: Diligent Farmer, White Dragon Studio, Anime Forge No.1,
  Big Dog Studio, Narcissuss, Skibidi Toilet Boom, Singularity Simulator
- Real games: Demon Soul Simulator (place 8069117419, universe 3108473052),
  Skibidi Toilet Battle Boom (place 137282814526439),
  Anime Fantasy Kingdom (place 115798208591074),
  Ninja Storm Simulator (place 9787091365),
  Ghost at the Door (place 15217653337)
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

# Real data: zhangyk2010's user ID (used as mock; actual ID to be resolved via API)
USER_ID = 48032694
USERNAME = "zhangyk2010"

# Real groups owned by zhangyk2010
GROUPS = {
    "12877779": {"name": "Diligent Farmer", "id": 12877779},
    "7472400": {"name": "White Dragon Studio", "id": 7472400},
    "35151383": {"name": "Anime Forge No.1", "id": 35151383},
    "14475541": {"name": "Big Dog Studio", "id": 14475541},
    "9012546": {"name": "Narcissuss", "id": 9012546},
    "35328237": {"name": "Skibidi Toilet Boom", "id": 35328237},
}

now = datetime.now(timezone.utc)
recent_1 = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
recent_2 = (now - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
recent_3 = (now - timedelta(days=25)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

# Real games by these groups (with real place/universe IDs, simulated dates)
# Demon Soul Simulator: created 2021-11-22, place 8069117419, universe 3108473052
# Skibidi Toilet Battle Boom: created 2024-12-16, place 137282814526439
# Anime Fantasy Kingdom: created 2024-12-17, place 115798208591074
# Ninja Storm Simulator: created 2022-06-01, place 9787091365
# Ghost at the Door: created 2023-10-30, place 15217653337

GROUP_GAMES = {
    # Diligent Farmer: Demon Soul Simulator (old) + a simulated recent game
    "12877779": [
        {"id": 6100000001, "name": "Demon Soul Simulator 2", "created": recent_1},
        {"id": 3108473052, "name": "Demon Soul Simulator", "created": "2021-11-22T00:00:00.000Z"},
    ],
    # White Dragon Studio: no recent games in this test
    "7472400": [
        {"id": 5200000001, "name": "White Dragon Tycoon", "created": "2024-06-15T00:00:00.000Z"},
    ],
    # Anime Forge No.1: Anime Fantasy Kingdom (simulated as recent)
    "35151383": [
        {"id": 6300000001, "name": "Anime Fantasy Kingdom 2", "created": recent_2},
        {"id": 5300000001, "name": "Anime Fantasy Kingdom", "created": "2024-12-17T00:00:00.000Z"},
    ],
    # Big Dog Studio: Ninja Storm Simulator (old)
    "14475541": [
        {"id": 4400000001, "name": "Ninja Storm Simulator", "created": "2022-06-01T00:00:00.000Z"},
    ],
    # Narcissuss: Ghost at the Door (old) + a simulated recent game
    "9012546": [
        {"id": 6500000001, "name": "Ghost at the Door 2", "created": recent_3},
        {"id": 4500000001, "name": "Ghost at the Door", "created": "2023-10-30T00:00:00.000Z"},
    ],
    # Skibidi Toilet Boom: Skibidi Toilet Battle Boom (old)
    "35328237": [
        {"id": 5600000001, "name": "Skibidi Toilet Battle Boom", "created": "2024-12-16T00:00:00.000Z"},
    ],
}

# Universe details for the recent games only (these would be fetched via /v1/games)
UNIVERSE_DETAILS = {
    6100000001: {
        "id": 6100000001, "rootPlaceId": 81000000001,
        "name": "Demon Soul Simulator 2",
        "description": "The sequel to the hit Demon Soul Simulator!",
        "created": recent_1, "updated": recent_1,
        "playing": 45230, "visits": 12500000,
        "maxPlayers": 30, "genre": "Adventure",
        "creator": {"id": 12877779, "name": "Diligent Farmer", "type": "Group"},
    },
    6300000001: {
        "id": 6300000001, "rootPlaceId": 83000000001,
        "name": "Anime Fantasy Kingdom 2",
        "description": "Build your anime kingdom!",
        "created": recent_2, "updated": recent_2,
        "playing": 8920, "visits": 3200000,
        "maxPlayers": 25, "genre": "RPG",
        "creator": {"id": 35151383, "name": "Anime Forge No.1", "type": "Group"},
    },
    6500000001: {
        "id": 6500000001, "rootPlaceId": 85000000001,
        "name": "Ghost at the Door 2",
        "description": "The horror continues... who's knocking?",
        "created": recent_3, "updated": recent_3,
        "playing": 12400, "visits": 5800000,
        "maxPlayers": 20, "genre": "Horror",
        "creator": {"id": 9012546, "name": "Narcissuss", "type": "Group"},
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

        # GET /v2/users/{userId}/games — zhangyk2010 has no direct user games
        if path == f"/v2/users/{USER_ID}/games":
            self._json_response({
                "previousPageCursor": None,
                "nextPageCursor": None,
                "data": [],
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
            writer.writerow(["user", "zhangyk2010"])       # username -> resolve to ID
            writer.writerow(["group", "12877779"])          # Diligent Farmer
            writer.writerow(["group", "7472400"])           # White Dragon Studio
            writer.writerow(["group", "35151383"])          # Anime Forge No.1
            writer.writerow(["group", "14475541"])          # Big Dog Studio
            writer.writerow(["group", "9012546"])           # Narcissuss
            writer.writerow(["group", "35328237"])          # Skibidi Toilet Boom

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
        print(f"{'Name':<30} {'Owner':<25} {'Created':<12} {'Playing':>8} {'Visits':>12} {'URL'}")
        print("-" * 120)
        for r in rows:
            print(f"{r['name']:<30} {r['owner_name']:<25} {r['created'][:10]:<12} {r['playing']:>8} {r['visits']:>12} {r['game_url']}")

        # Assertions
        names = [r["name"] for r in rows]
        print(f"\n{'='*60}")
        print("ASSERTIONS:")
        print("="*60)

        # Should find exactly 3 recent games
        assert len(rows) == 3, f"Expected 3 recent games, got {len(rows)}"
        print(f"  [PASS] Found {len(rows)} recent games")

        # Should include these recent games
        assert "Demon Soul Simulator 2" in names
        assert "Anime Fantasy Kingdom 2" in names
        assert "Ghost at the Door 2" in names
        print("  [PASS] All expected recent games present")

        # Should NOT include old/real games
        assert "Demon Soul Simulator" not in names, "Original Demon Soul Simulator (2021) should be filtered"
        assert "Anime Fantasy Kingdom" not in names, "Original Anime Fantasy Kingdom (2024-12) should be filtered"
        assert "Ghost at the Door" not in names, "Original Ghost at the Door (2023) should be filtered"
        assert "Ninja Storm Simulator" not in names, "Ninja Storm Simulator (2022) should be filtered"
        assert "White Dragon Tycoon" not in names, "White Dragon Tycoon (2024-06) should be filtered"
        assert "Skibidi Toilet Battle Boom" not in names, "Skibidi Toilet Battle Boom (2024-12) should be filtered"
        print("  [PASS] All old games correctly filtered out (Demon Soul Sim, Ninja Storm, Ghost at Door, etc.)")

        # Check owner attribution
        for r in rows:
            if r["name"] == "Demon Soul Simulator 2":
                assert r["owner_type"] == "group"
                assert r["owner_name"] == "Diligent Farmer"
            if r["name"] == "Ghost at the Door 2":
                assert r["owner_type"] == "group"
                assert r["owner_name"] == "Narcissuss"
            if r["name"] == "Anime Fantasy Kingdom 2":
                assert r["owner_type"] == "group"
                assert r["owner_name"] == "Anime Forge No.1"
        print("  [PASS] Owner attribution correct (Diligent Farmer, Narcissuss, Anime Forge No.1)")

        # Check game URLs
        for r in rows:
            assert r["game_url"].startswith("https://www.roblox.com/games/"), f"Bad URL: {r['game_url']}"
        print("  [PASS] Game URLs correctly formatted")

        # Check sorting (newest first)
        dates = [r["created"] for r in rows]
        assert dates == sorted(dates, reverse=True), "Results not sorted by date descending"
        print("  [PASS] Results sorted by creation date (newest first)")

        # Verify user had no direct games (all came from groups)
        for r in rows:
            assert r["owner_type"] == "group", f"Expected group owner for {r['name']}"
        print("  [PASS] All games attributed to groups (user had no direct creations)")

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
