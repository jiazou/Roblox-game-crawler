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
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger("crawler")

BASE_URL = "https://games.roblox.com"
USERS_URL = "https://users.roblox.com"
GROUPS_URL = "https://groups.roblox.com"

# Max universe IDs per batch request
UNIVERSE_BATCH_SIZE = 100

# Delay between API requests to avoid rate limiting (seconds)
REQUEST_DELAY = 0.5

# Retry settings
MAX_RETRIES = 7
RETRY_BACKOFF = 2  # seconds, doubled each retry


def _truncate(text, max_len=1000):
    """Truncate text for logging, adding an indicator if truncated."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... ({len(text) - max_len} more chars)"


def make_request(url, params=None, method="GET", json_body=None):
    """Make an HTTP request with retry logic and rate limiting."""
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug("%s %s params=%s", method, url, params)
            resp = requests.request(method, url, params=params, json=json_body, timeout=15)
            logger.debug("  -> %s %s (%d bytes)", resp.status_code, resp.reason, len(resp.content))
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * (2 ** attempt)
                logger.warning("  Rate limited, waiting %ds...", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            logger.debug("  -> body: %s", _truncate(json.dumps(body)))
            time.sleep(REQUEST_DELAY)
            return body
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (2 ** attempt)
                logger.warning("  Request failed (%s), retrying in %ds...", e, wait)
                time.sleep(wait)
            else:
                logger.error("  Request failed after %d attempts: %s", MAX_RETRIES, e)
                return None
    return None


def resolve_username(username):
    """Resolve a Roblox username to a user ID."""
    result = make_request(
        f"{USERS_URL}/v1/usernames/users",
        method="POST",
        json_body={"usernames": [username], "excludeBannedUsers": False},
    )
    if result and result.get("data"):
        return result["data"][0]["id"]
    logger.warning("Username '%s' not found", username)
    return None


def get_games(url, cutoff_date=None):
    """Fetch all games/universes from a paginated Roblox endpoint.

    Stops paginating once games older than cutoff_date are encountered
    (relies on Desc sort order by creation date).
    """
    universes = []
    cursor = None

    while True:
        # User game listings only support limit=50; group listings support 100
        limit = 100 if "/groups/" in url else 50
        params = {"sortOrder": "Desc", "limit": limit}
        # accessFilter is only supported on group game listings
        if "/groups/" in url:
            params["accessFilter"] = 2
        if cursor:
            params["cursor"] = cursor

        data = make_request(url, params)
        if not data:
            break

        page_items = data.get("data", [])
        logger.info("  Page returned %d game(s)", len(page_items))
        hit_old_game = False
        for item in page_items:
            created_str = item.get("created", "")
            if cutoff_date and created_str:
                if parse_datetime(created_str) < cutoff_date:
                    logger.info("    Skipping old game id=%s created=%s", item.get("id"), created_str)
                    hit_old_game = True
                    continue
            logger.info("    Keeping game id=%s name=%s created=%s", item.get("id"), item.get("name"), created_str)
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
        logger.info("  Fetching details for batch of %d universe(s): %s", len(batch), ids_param)
        data = make_request(f"{BASE_URL}/v1/games", {"universeIds": ids_param})
        if data and "data" in data:
            for d in data["data"]:
                logger.info("    Universe %s: name=%s created=%s", d.get("id"), d.get("name"), d.get("created"))
            all_details.extend(data["data"])
        else:
            logger.warning("  No data returned for batch")

    return all_details


def get_user_groups(user_id):
    """Fetch all groups owned by a user.

    Uses the groups API to get all groups a user belongs to, then filters
    for groups where the user has the Owner role (rank 255).
    Returns a list of (group_id, group_name) tuples.
    """
    data = make_request(f"{GROUPS_URL}/v1/users/{user_id}/groups/roles")
    if not data:
        return []

    owned_groups = []
    for entry in data.get("data", []):
        role = entry.get("role", {})
        group = entry.get("group", {})
        logger.debug("  Group %s (%s) — role=%s rank=%s",
                      group.get("id"), group.get("name"), role.get("name"), role.get("rank"))
        if role.get("rank") == 255:
            owned_groups.append((group["id"], group.get("name", f"Group {group['id']}")))

    logger.info("  User %s owns %d group(s) out of %d total memberships",
                user_id, len(owned_groups), len(data.get("data", [])))
    return owned_groups


def get_name(url, fallback):
    """Fetch a display name from a Roblox API endpoint."""
    data = make_request(url)
    return data.get("name", fallback) if data else fallback


def read_input_csv(filepath):
    """Read input CSV and return lists of user IDs and group IDs.

    Expected CSV format:
        type,id
        user,12345
        user,zhangyk2010
        group,67890

    The 'type' column should be 'user' or 'group'.
    The 'id' column can be a numeric Roblox ID or a username (for users).
    Usernames are resolved to IDs via the Roblox API.
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

            if entry_id.isdigit():
                entry_id = int(entry_id)
            elif entry_type == "user":
                # Treat non-numeric ID as a username and resolve it
                print(f"Resolving username '{entry_id}'...")
                resolved = resolve_username(entry_id)
                if resolved is None:
                    print(f"Warning: Could not resolve username '{entry_id}' (row {row_num}), skipping")
                    continue
                print(f"  Resolved '{entry_id}' -> user ID {resolved}")
                entry_id = resolved
            else:
                print(f"Warning: Skipping row {row_num}, invalid group ID: {entry_id}")
                continue

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
    # Strip fractional seconds for broad Python compatibility, then parse.
    dt_str = dt_str.replace("Z", "+00:00")
    dt_str = re.sub(r"\.\d+", "", dt_str)
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
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v for INFO, -vv for DEBUG with full request/response details)",
    )
    args = parser.parse_args()

    # Configure logging based on verbosity
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"Finding games created after {cutoff_date.strftime('%Y-%m-%d %H:%M UTC')}")

    # Read input
    user_ids, group_ids = read_input_csv(args.input_csv)
    print(f"Loaded {len(user_ids)} user(s) and {len(group_ids)} group(s) from {args.input_csv}")

    if not user_ids and not group_ids:
        print("No valid user or group IDs found in input. Exiting.")
        sys.exit(0)

    # Auto-discover groups owned by each user
    group_ids_set = set(group_ids)
    for user_id in user_ids:
        print(f"Discovering groups owned by user ID {user_id}...")
        owned = get_user_groups(user_id)
        new_count = 0
        for gid, gname in owned:
            if gid not in group_ids_set:
                group_ids.append(gid)
                group_ids_set.add(gid)
                new_count += 1
                print(f"  Found group: {gname} (ID: {gid})")
        if new_count == 0 and not owned:
            print("  No owned groups found")
        elif new_count == 0:
            print(f"  All {len(owned)} owned group(s) already in input")
        else:
            print(f"  Added {new_count} new group(s)")

    print(f"Total: {len(user_ids)} user(s) and {len(group_ids)} group(s) to crawl")

    # Collect all universe listings with their owner info
    universe_owner_map = {}  # universe_id -> (owner_type, owner_id, owner_name)

    # Process users
    for user_id in user_ids:
        username = get_name(f"{USERS_URL}/v1/users/{user_id}", f"User {user_id}")
        print(f"Fetching games for user {username} (ID: {user_id})...")
        games = get_games(f"{BASE_URL}/v2/users/{user_id}/games", cutoff_date)
        print(f"  Found {len(games)} game(s)")
        for game in games:
            uid = game.get("id")
            if uid:
                universe_owner_map[uid] = ("user", user_id, username)

    # Process groups
    for group_id in group_ids:
        group_name = get_name(f"{GROUPS_URL}/v1/groups/{group_id}", f"Group {group_id}")
        print(f"Fetching games for group {group_name} (ID: {group_id})...")
        games = get_games(f"{BASE_URL}/v2/groups/{group_id}/games", cutoff_date)
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
        print(f"  - {r['name']} (by {r['owner_name']}, created {r['created'][:10]}) {r['game_url']}")

    # Write output
    write_output_csv(args.output, results)
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
