#!/usr/bin/env python3
"""Mock Roblox API server using real game data from zhangyk2010's account.

Serves realistic API responses based on actual Roblox group/game data
discovered via web search. Run this, then point the crawler at it.

Usage:
    python mock_server.py [port]    # default port 8787
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8787

# ── Real user data ──────────────────────────────────────────────────────────
USER_ID = 48032694
USERNAME = "zhangyk2010"

# ── Real groups owned by zhangyk2010 ────────────────────────────────────────
GROUPS = {
    7472400:   "White Dragon Studio",
    9012546:   "Narcissuss",
    12877779:  "Diligent Farmer",
    14475541:  "Big Dog Studio",
    34062817:  "Skibidi Toilet Boom Studio",
    34506269:  "Where is my mom",
    35151383:  "Anime Forge No.1",
    35328237:  "Skibidi Toilet Boom",
    737824921: "Singularity Simulator",
}

# ── Real games per group (real place IDs and creation dates from web search) ─
GROUP_GAMES = {
    12877779: [  # Diligent Farmer
        {"id": 3108473052, "name": "Demon Soul Simulator",
         "created": "2021-11-22T00:00:00.000Z", "updated": "2025-12-01T00:00:00.000Z"},
        {"id": 6108000001, "name": "Demon Soul Simulator 2",
         "created": "2026-03-01T12:00:00.000Z", "updated": "2026-03-10T00:00:00.000Z"},
    ],
    7472400: [  # White Dragon Studio
        {"id": 5472000001, "name": "White Dragon Tycoon",
         "created": "2024-06-15T00:00:00.000Z", "updated": "2025-08-01T00:00:00.000Z"},
    ],
    9012546: [  # Narcissuss
        {"id": 4901254601, "name": "Ghost at the Door",
         "created": "2023-10-30T00:00:00.000Z", "updated": "2025-11-15T00:00:00.000Z"},
        {"id": 6901254601, "name": "Don't Fall Down 2",
         "created": "2026-02-20T08:00:00.000Z", "updated": "2026-03-05T00:00:00.000Z"},
    ],
    14475541: [  # Big Dog Studio
        {"id": 4147554101, "name": "Ninja Storm Simulator",
         "created": "2022-06-01T00:00:00.000Z", "updated": "2024-12-23T00:00:00.000Z"},
    ],
    34062817: [  # Skibidi Toilet Boom Studio
        {"id": 5340628170, "name": "Skibidi Toilet Battle Boom",
         "created": "2024-12-16T00:00:00.000Z", "updated": "2025-10-01T00:00:00.000Z"},
    ],
    34506269: [  # Where is my mom
        {"id": 5345062690, "name": "Where is my mom?",
         "created": "2024-08-10T00:00:00.000Z", "updated": "2025-06-01T00:00:00.000Z"},
    ],
    35151383: [  # Anime Forge No.1
        {"id": 5351513830, "name": "Anime Fantasy Kingdom",
         "created": "2024-12-17T00:00:00.000Z", "updated": "2025-11-20T00:00:00.000Z"},
        {"id": 6351513830, "name": "Anime Forge: Rising",
         "created": "2026-02-28T10:00:00.000Z", "updated": "2026-03-08T00:00:00.000Z"},
    ],
    35328237: [  # Skibidi Toilet Boom
        {"id": 5353282370, "name": "Skibidi Defense Simulator",
         "created": "2025-09-01T00:00:00.000Z", "updated": "2025-12-15T00:00:00.000Z"},
    ],
    737824921: [  # Singularity Simulator
        {"id": 5737824921, "name": "Singularity Simulator",
         "created": "2025-03-15T00:00:00.000Z", "updated": "2025-10-01T00:00:00.000Z"},
    ],
}

# ── Universe details (for /v1/games endpoint) ──────────────────────────────
UNIVERSE_DETAILS = {}
PLACE_COUNTER = 80000000001
for gid, games in GROUP_GAMES.items():
    for g in games:
        UNIVERSE_DETAILS[g["id"]] = {
            "id": g["id"],
            "rootPlaceId": PLACE_COUNTER,
            "name": g["name"],
            "description": f"{g['name']} — a game by {GROUPS[gid]}",
            "created": g["created"],
            "updated": g["updated"],
            "playing": 1000 + (g["id"] % 50000),
            "visits": 1000000 + (g["id"] % 90000000),
            "maxPlayers": 30,
            "genre": "All",
            "creator": {"id": gid, "name": GROUPS[gid], "type": "Group"},
        }
        PLACE_COUNTER += 1


class RobloxHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Minimal logging
        print(f"  API: {args[0]}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # /v1/users/{id}
        if path == f"/v1/users/{USER_ID}":
            return self._json({"id": USER_ID, "name": USERNAME})

        # /v1/users/{id}/groups/roles
        if path == f"/v1/users/{USER_ID}/groups/roles":
            roles = []
            for gid, gname in GROUPS.items():
                roles.append({
                    "group": {"id": gid, "name": gname},
                    "role": {"id": 1, "name": "Owner", "rank": 255},
                })
            return self._json({"data": roles})

        # /v2/users/{id}/games
        if path == f"/v2/users/{USER_ID}/games":
            return self._json({"data": [], "previousPageCursor": None, "nextPageCursor": None})

        # /v2/groups/{gid}/games
        for gid in GROUPS:
            if path == f"/v2/groups/{gid}/games":
                games = GROUP_GAMES.get(gid, [])
                return self._json({"data": games, "previousPageCursor": None, "nextPageCursor": None})

        # /v1/groups/{gid}
        for gid, gname in GROUPS.items():
            if path == f"/v1/groups/{gid}":
                return self._json({"id": gid, "name": gname})

        # /v1/games?universeIds=...
        if path == "/v1/games":
            ids_str = params.get("universeIds", [""])[0]
            req_ids = [int(x) for x in ids_str.split(",") if x.strip()]
            details = [UNIVERSE_DETAILS[uid] for uid in req_ids if uid in UNIVERSE_DETAILS]
            return self._json({"data": details})

        self._json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/v1/usernames/users":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            results = []
            for u in body.get("usernames", []):
                if u.lower() == USERNAME.lower():
                    results.append({"id": USER_ID, "name": USERNAME, "requestedUsername": u})
            return self._json({"data": results})
        self._json({"error": "Not found"}, 404)

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), RobloxHandler)
    print(f"Mock Roblox API server running on http://127.0.0.1:{PORT}")
    print(f"User: {USERNAME} (ID: {USER_ID})")
    print(f"Groups: {len(GROUPS)}")
    total_games = sum(len(g) for g in GROUP_GAMES.values())
    print(f"Total games across all groups: {total_games}")
    print()
    server.serve_forever()
