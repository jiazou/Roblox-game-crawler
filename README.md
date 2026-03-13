# Roblox Game Crawler

Finds all Roblox games (experiences) owned by specified users or groups that were created within a given time window (default: last 30 days).

## Setup

```bash
pip install -r requirements.txt
```

## Usage

1. Create an input CSV file with columns `type` and `id`:

```csv
type,id
user,12345
group,67890
```

2. Run the crawler:

```bash
python crawler.py input.csv -o output.csv
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-o`, `--output` | Output CSV file path | `output.csv` |
| `--days` | Number of days to look back | `30` |

### Examples

```bash
# Find games created in the last 30 days
python crawler.py example_input.csv

# Find games created in the last 60 days, custom output
python crawler.py input.csv --days 60 -o recent_games.csv
```

## Output

The output CSV contains the following columns:

| Column | Description |
|--------|-------------|
| `universe_id` | Roblox universe ID |
| `name` | Game name |
| `owner_type` | `user` or `group` |
| `owner_id` | Owner's Roblox ID |
| `owner_name` | Owner's display name |
| `created` | Creation timestamp |
| `updated` | Last update timestamp |
| `description` | Game description |
| `playing` | Current player count |
| `visits` | Total visit count |
| `max_players` | Max players per server |
| `genre` | Game genre |
| `game_url` | Direct link to the game |

## API Endpoints Used

- `games.roblox.com/v2/users/{id}/games` — games by user
- `games.roblox.com/v2/groups/{id}/games` — games by group
- `games.roblox.com/v1/games?universeIds=...` — universe details (creation date)
- `users.roblox.com/v1/users/{id}` — username lookup
- `groups.roblox.com/v1/groups/{id}` — group name lookup
