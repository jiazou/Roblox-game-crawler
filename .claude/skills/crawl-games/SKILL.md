---
name: crawl-games
description: Crawl Roblox APIs to find newly created games for tracked users and groups. Use when the user wants to discover new Roblox games/experiences.
allowed-tools: Bash(curl *), Bash(cat *), Read, Write, Edit, Glob
argument-hint: "[--days N]"
---

# Roblox Game Crawler Skill

You are a Roblox game crawler. Your job is to fetch data from the Roblox APIs,
find games created recently, and write results to `output.csv`.

## Arguments

- `$ARGUMENTS` may contain `--days N` to override the default 30-day lookback.
  If not provided, default to 30 days.

## Reference

See [api-reference.md](api-reference.md) for Roblox API endpoint documentation.

## Step-by-step process

### 1. Read the input file

Read `input.csv` in the project root. It has columns `type` and `id`:
- `type` is `user` or `group`
- `id` is a numeric Roblox ID or a username (for users)

### 2. Resolve usernames to user IDs

For any user row where `id` is not numeric, resolve it using the username
lookup API (see api-reference.md). Log each resolution.

### 3. Discover groups owned by each user

For each user ID, fetch their group memberships and find groups where the user
has rank 255 (Owner). Add these group IDs to the crawl list. Log each
discovered group.

### 4. Fetch games for each user and group

For each user and group, fetch their games list using the games API.
Use pagination if `nextPageCursor` is present.

**Important**: Use `sortOrder=Desc` so newest games come first. Once you
encounter a game created before the cutoff date, stop paginating — all
remaining games are older.

### 5. Fetch universe details

Collect all universe IDs from step 4. Fetch detailed info (creation date,
visit count, player count, etc.) using the universe details API. Batch up
to 100 IDs per request.

### 6. Filter and output

Filter to games created within the lookback window. Write results to
`output.csv` with these columns:

```
universe_id,name,owner_type,owner_id,owner_name,created,updated,description,playing,visits,max_players,genre,game_url
```

The `game_url` is `https://www.roblox.com/games/{rootPlaceId}`.

Sort results by creation date descending.

## How to make API calls

Use `curl` for all HTTP requests. Always use `-s` (silent) and include
`-w '\nHTTP_STATUS:%{http_code}'` to capture the status code.

**For GET requests:**
```bash
curl -s -w '\nHTTP_STATUS:%{http_code}' "https://games.roblox.com/v2/groups/12345/games?sortOrder=Desc&limit=100&accessFilter=2"
```

**For POST requests:**
```bash
curl -s -w '\nHTTP_STATUS:%{http_code}' -X POST -H "Content-Type: application/json" \
  -d '{"usernames":["zhangyk2010"],"excludeBannedUsers":false}' \
  "https://users.roblox.com/v1/usernames/users"
```

## Logging requirements

For EVERY API call, log to the user:
1. The full URL being fetched
2. The HTTP status code received
3. A summary of what the response contained (e.g. "returned 5 games",
   "found 3 owned groups", etc.)
4. If filtering: which items were kept vs skipped, and why

## Adapting to API changes

**This is critical.** The Roblox API response format may change over time.
When you receive a response:

1. **Inspect the actual JSON structure** before extracting fields
2. If the response structure doesn't match what api-reference.md describes,
   **adapt** — look at the actual field names and nested structure
3. Log any format differences you notice so the user is aware
4. If a response is completely unexpected (e.g. HTML instead of JSON, or an
   error message), report it clearly and try to continue with other items

Do NOT blindly assume field names. Always check what the API actually returned.

## Rate limiting

- Wait 0.5 seconds between requests (use `sleep 0.5` between curl calls)
- If you get HTTP 429 (rate limited), wait 2 seconds and retry (up to 3 times
  with exponential backoff: 2s, 4s, 8s)

## Error handling

- If a request fails, retry up to 3 times with exponential backoff
- If a user/group returns no data, log it and continue to the next one
- Never silently skip errors — always tell the user what happened
