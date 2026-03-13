#!/usr/bin/env python3
"""Roblox Game Crawler

Given a CSV of Roblox user IDs and group IDs, finds all games (experiences)
owned by those accounts or groups that were created in the last month.
Outputs results to a CSV file.

Usage:
    python crawler.py input.csv -o output.csv
    python crawler.py input.csv --days 60    # look back 60 days instead of 30
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://games.roblox.com"
USERS_URL = "https://users.roblox.com"
GROUPS_URL = "https://groups.roblox.com"

# Max universe IDs per batch request
UNIVERSE_BATCH_SIZE = 100

# Delay between API requests to avoid rate limiting (seconds)
REQUEST_DELAY = 0.5

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubled each retry


def make_request(url, params=None):
    """Make a GET request with retry logic and rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"  Request failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Request failed after {MAX_RETRIES} attempts: {e}")
                return None
    return None


def resolve_username(username):
    """Resolve a Roblox username to a user ID."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                f"{USERS_URL}/v1/usernames/users",
                json={"usernames": [username], "excludeBannedUsers": False},
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("data"):
                return result["data"][0]["id"]
            return None
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
    return None


def get_user_games(user_id, cutoff_date=None):
    """Fetch all games/universes created by a user.

    If cutoff_date is provided, stops paginating once games older than the
    cutoff are encountered (relies on Desc sort order by creation date).
    """
    universes = []
    cursor = None

    while True:
        params = {"sortOrder": "Desc", "limit": 50, "accessFilter": 2}
        if cursor:
            params["cursor"] = cursor

        data = make_request(f"{BASE_URL}/v2/users/{user_id}/games", params)
        if not data:
            break

        hit_old_game = False
        for item in data.get("data", []):
            if cutoff_date and item.get("created"):
                created_dt = parse_datetime(item["created"])
                if created_dt < cutoff_date:
                    hit_old_game = True
                    continue
            universes.append(item)

        cursor = data.get("nextPageCursor")
        if not cursor or hit_old_game:
            break

    return universes


def get_group_games(group_id, cutoff_date=None):
    """Fetch all games/universes owned by a group.

    If cutoff_date is provided, stops paginating once games older than the
    cutoff are encountered (relies on Desc sort order by creation date).
    """
    universes = []
    cursor = None

    while True:
        params = {"sortOrder": "Desc", "limit": 100, "accessFilter": 2}
        if cursor:
            params["cursor"] = cursor

        data = make_request(f"{BASE_URL}/v2/groups/{group_id}/games", params)
        if not data:
            break

        hit_old_game = False
        for item in data.get("data", []):
            if cutoff_date and item.get("created"):
                created_dt = parse_datetime(item["created"])
                if created_dt < cutoff_date:
                    hit_old_game = True
                    continue
            universes.append(item)

        cursor = data.get("nextPageCursor")
        if not cursor or hit_old_game:
            break

    return universes


def get_universe_details(universe_ids):
    """Fetch detailed info (including creation date) for a batch of universes."""
    if not universe_ids:
        return []

    all_details = []
    for i in range(0, len(universe_ids), UNIVERSE_BATCH_SIZE):
        batch = universe_ids[i : i + UNIVERSE_BATCH_SIZE]
        ids_param = ",".join(str(uid) for uid in batch)
        data = make_request(f"{BASE_URL}/v1/games", {"universeIds": ids_param})
        if data and "data" in data:
            all_details.extend(data["data"])

    return all_details


def get_group_name(group_id):
    """Fetch the name of a group."""
    data = make_request(f"{GROUPS_URL}/v1/groups/{group_id}")
    if data:
        return data.get("name", f"Group {group_id}")
    return f"Group {group_id}"


def get_username(user_id):
    """Fetch the username for a user ID."""
    data = make_request(f"{USERS_URL}/v1/users/{user_id}")
    if data:
        return data.get("name", f"User {user_id}")
    return f"User {user_id}"


def read_input_csv(filepath):
    """Read input CSV and return lists of user IDs and group IDs.

    Expected CSV format:
        type,id
        user,12345
        group,67890

    The 'type' column should be 'user' or 'group'.
    The 'id' column should be a numeric Roblox ID.
    """
    user_ids = []
    group_ids = []

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate headers
        if not reader.fieldnames:
            print("Error: Input CSV is empty")
            sys.exit(1)

        headers_lower = [h.strip().lower() for h in reader.fieldnames]
        if "type" not in headers_lower or "id" not in headers_lower:
            print("Error: Input CSV must have 'type' and 'id' columns")
            sys.exit(1)

        # Map actual header names
        type_col = reader.fieldnames[headers_lower.index("type")]
        id_col = reader.fieldnames[headers_lower.index("id")]

        for row_num, row in enumerate(reader, start=2):
            entry_type = row[type_col].strip().lower()
            entry_id = row[id_col].strip()

            if not entry_id.isdigit():
                print(f"Warning: Skipping row {row_num}, invalid ID: {entry_id}")
                continue

            entry_id = int(entry_id)
            if entry_type == "user":
                user_ids.append(entry_id)
            elif entry_type == "group":
                group_ids.append(entry_id)
            else:
                print(f"Warning: Skipping row {row_num}, unknown type: {entry_type}")

    return user_ids, group_ids


def write_output_csv(filepath, games):
    """Write discovered games to a CSV file."""
    fieldnames = [
        "universe_id",
        "name",
        "owner_type",
        "owner_id",
        "owner_name",
        "created",
        "updated",
        "description",
        "playing",
        "visits",
        "max_players",
        "genre",
        "game_url",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for game in games:
            writer.writerow(game)


def parse_datetime(dt_str):
    """Parse a Roblox API datetime string to a timezone-aware datetime."""
    # Roblox uses ISO 8601 format like "2024-01-15T12:00:00.000Z"
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str)


def main():
    parser = argparse.ArgumentParser(
        description="Crawl Roblox for games created by specified users/groups in the last month"
    )
    parser.add_argument("input_csv", help="Path to input CSV with user/group IDs")
    parser.add_argument(
        "-o", "--output", default="output.csv", help="Output CSV path (default: output.csv)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Look back this many days for new games (default: 30)",
    )
    args = parser.parse_args()

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"Finding games created after {cutoff_date.strftime('%Y-%m-%d %H:%M UTC')}")

    # Read input
    user_ids, group_ids = read_input_csv(args.input_csv)
    print(f"Loaded {len(user_ids)} user(s) and {len(group_ids)} group(s) from {args.input_csv}")

    if not user_ids and not group_ids:
        print("No valid user or group IDs found in input. Exiting.")
        sys.exit(0)

    # Collect all universe listings with their owner info
    universe_owner_map = {}  # universe_id -> (owner_type, owner_id, owner_name)

    # Process users
    for user_id in user_ids:
        username = get_username(user_id)
        print(f"Fetching games for user {username} (ID: {user_id})...")
        games = get_user_games(user_id, cutoff_date)
        print(f"  Found {len(games)} game(s)")
        for game in games:
            uid = game.get("id")
            if uid:
                universe_owner_map[uid] = ("user", user_id, username)

    # Process groups
    for group_id in group_ids:
        group_name = get_group_name(group_id)
        print(f"Fetching games for group {group_name} (ID: {group_id})...")
        games = get_group_games(group_id, cutoff_date)
        print(f"  Found {len(games)} game(s)")
        for game in games:
            uid = game.get("id")
            if uid:
                universe_owner_map[uid] = ("group", group_id, group_name)

    if not universe_owner_map:
        print("No games found for any of the specified users/groups.")
        sys.exit(0)

    print(f"\nFetching details for {len(universe_owner_map)} universe(s)...")

    # Get detailed info for all universes
    universe_ids = list(universe_owner_map.keys())
    details = get_universe_details(universe_ids)

    # Filter by creation date and build output
    results = []
    for detail in details:
        created_str = detail.get("created")
        if not created_str:
            continue

        created_dt = parse_datetime(created_str)
        if created_dt < cutoff_date:
            continue

        uid = detail["id"]
        owner_type, owner_id, owner_name = universe_owner_map.get(
            uid, ("unknown", 0, "Unknown")
        )

        root_place_id = detail.get("rootPlaceId", "")
        game_url = f"https://www.roblox.com/games/{root_place_id}" if root_place_id else ""

        results.append(
            {
                "universe_id": uid,
                "name": detail.get("name", ""),
                "owner_type": owner_type,
                "owner_id": owner_id,
                "owner_name": owner_name,
                "created": created_str,
                "updated": detail.get("updated", ""),
                "description": detail.get("description", ""),
                "playing": detail.get("playing", 0),
                "visits": detail.get("visits", 0),
                "max_players": detail.get("maxPlayers", 0),
                "genre": detail.get("genre", ""),
                "game_url": game_url,
            }
        )

    # Sort by creation date descending
    results.sort(key=lambda x: x["created"], reverse=True)

    print(f"\nFound {len(results)} game(s) created in the last {args.days} days:")
    for r in results:
        print(f"  - {r['name']} (by {r['owner_name']}, created {r['created'][:10]})")

    # Write output
    write_output_csv(args.output, results)
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
