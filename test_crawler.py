"""Unit tests for crawler.py using mocked API responses."""

import csv
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import crawler


# --- Fixtures ---

@pytest.fixture
def cutoff_date():
    return datetime.now(timezone.utc) - timedelta(days=30)


@pytest.fixture
def recent_date():
    """A date within the last 30 days."""
    dt = datetime.now(timezone.utc) - timedelta(days=5)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.fixture
def old_date():
    """A date older than 30 days."""
    dt = datetime.now(timezone.utc) - timedelta(days=60)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@pytest.fixture
def input_csv_path():
    """Create a temporary input CSV file."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def output_csv_path():
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


# --- parse_datetime ---

def test_parse_datetime_z_suffix():
    dt = crawler.parse_datetime("2025-06-15T12:30:00.000Z")
    assert dt.year == 2025
    assert dt.month == 6
    assert dt.day == 15
    assert dt.tzinfo is not None


def test_parse_datetime_offset():
    dt = crawler.parse_datetime("2025-06-15T12:30:00+00:00")
    assert dt.year == 2025


# --- read_input_csv ---

def test_read_input_csv_numeric_ids(input_csv_path):
    with open(input_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "id"])
        writer.writerow(["user", "111"])
        writer.writerow(["group", "222"])
        writer.writerow(["user", "333"])

    user_ids, group_ids = crawler.read_input_csv(input_csv_path)
    assert user_ids == [111, 333]
    assert group_ids == [222]


@patch("crawler.resolve_username")
def test_read_input_csv_username_resolution(mock_resolve, input_csv_path):
    mock_resolve.return_value = 12345
    with open(input_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "id"])
        writer.writerow(["user", "zhangyk2010"])

    user_ids, group_ids = crawler.read_input_csv(input_csv_path)
    assert user_ids == [12345]
    mock_resolve.assert_called_once_with("zhangyk2010")


@patch("crawler.resolve_username")
def test_read_input_csv_username_unresolved(mock_resolve, input_csv_path):
    mock_resolve.return_value = None
    with open(input_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "id"])
        writer.writerow(["user", "nonexistent_user"])

    user_ids, group_ids = crawler.read_input_csv(input_csv_path)
    assert user_ids == []


def test_read_input_csv_invalid_group_id(input_csv_path):
    with open(input_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "id"])
        writer.writerow(["group", "not_a_number"])

    user_ids, group_ids = crawler.read_input_csv(input_csv_path)
    assert group_ids == []


def test_read_input_csv_case_insensitive_headers(input_csv_path):
    with open(input_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Type", "ID"])
        writer.writerow(["User", "100"])

    user_ids, group_ids = crawler.read_input_csv(input_csv_path)
    assert user_ids == [100]


# --- resolve_username ---

@patch("crawler.requests.post")
def test_resolve_username_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": 99999, "name": "testuser"}]}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    result = crawler.resolve_username("testuser")
    assert result == 99999


@patch("crawler.requests.post")
def test_resolve_username_not_found(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    result = crawler.resolve_username("nonexistent")
    assert result is None


# --- get_user_games ---

@patch("crawler.make_request")
def test_get_user_games_single_page(mock_req, recent_date):
    mock_req.return_value = {
        "data": [{"id": 1001, "created": recent_date}],
        "nextPageCursor": None,
    }
    result = crawler.get_user_games(111)
    assert len(result) == 1
    assert result[0]["id"] == 1001


@patch("crawler.make_request")
def test_get_user_games_pagination(mock_req, recent_date):
    mock_req.side_effect = [
        {"data": [{"id": 1001, "created": recent_date}], "nextPageCursor": "abc"},
        {"data": [{"id": 1002, "created": recent_date}], "nextPageCursor": None},
    ]
    result = crawler.get_user_games(111)
    assert len(result) == 2


@patch("crawler.make_request")
def test_get_user_games_cutoff_filter(mock_req, recent_date, old_date, cutoff_date):
    mock_req.return_value = {
        "data": [
            {"id": 1001, "created": recent_date},
            {"id": 1002, "created": old_date},
        ],
        "nextPageCursor": "abc",
    }
    result = crawler.get_user_games(111, cutoff_date)
    assert len(result) == 1
    assert result[0]["id"] == 1001
    # Should not paginate further after hitting old game
    mock_req.assert_called_once()


@patch("crawler.make_request")
def test_get_user_games_api_failure(mock_req):
    mock_req.return_value = None
    result = crawler.get_user_games(111)
    assert result == []


# --- get_group_games ---

@patch("crawler.make_request")
def test_get_group_games_single_page(mock_req, recent_date):
    mock_req.return_value = {
        "data": [{"id": 2001, "created": recent_date}],
        "nextPageCursor": None,
    }
    result = crawler.get_group_games(222)
    assert len(result) == 1


@patch("crawler.make_request")
def test_get_group_games_cutoff_filter(mock_req, recent_date, old_date, cutoff_date):
    mock_req.return_value = {
        "data": [
            {"id": 2001, "created": recent_date},
            {"id": 2002, "created": old_date},
        ],
        "nextPageCursor": "xyz",
    }
    result = crawler.get_group_games(222, cutoff_date)
    assert len(result) == 1
    assert result[0]["id"] == 2001


# --- get_universe_details ---

@patch("crawler.make_request")
def test_get_universe_details_batch(mock_req, recent_date):
    mock_req.return_value = {
        "data": [
            {"id": 1001, "name": "Game A", "created": recent_date},
            {"id": 1002, "name": "Game B", "created": recent_date},
        ]
    }
    result = crawler.get_universe_details([1001, 1002])
    assert len(result) == 2


@patch("crawler.make_request")
def test_get_universe_details_empty(mock_req):
    result = crawler.get_universe_details([])
    assert result == []
    mock_req.assert_not_called()


# --- get_username / get_group_name ---

@patch("crawler.make_request")
def test_get_username(mock_req):
    mock_req.return_value = {"name": "TestUser", "id": 111}
    assert crawler.get_username(111) == "TestUser"


@patch("crawler.make_request")
def test_get_username_fallback(mock_req):
    mock_req.return_value = None
    assert crawler.get_username(111) == "User 111"


@patch("crawler.make_request")
def test_get_group_name(mock_req):
    mock_req.return_value = {"name": "Cool Group", "id": 222}
    assert crawler.get_group_name(222) == "Cool Group"


@patch("crawler.make_request")
def test_get_group_name_fallback(mock_req):
    mock_req.return_value = None
    assert crawler.get_group_name(222) == "Group 222"


# --- write_output_csv ---

def test_write_output_csv(output_csv_path):
    games = [
        {
            "universe_id": 1001,
            "name": "Test Game",
            "owner_type": "user",
            "owner_id": 111,
            "owner_name": "TestUser",
            "created": "2026-03-01T00:00:00.000Z",
            "updated": "2026-03-10T00:00:00.000Z",
            "description": "A test game",
            "playing": 50,
            "visits": 10000,
            "max_players": 20,
            "genre": "All",
            "game_url": "https://www.roblox.com/games/5001",
        }
    ]
    crawler.write_output_csv(output_csv_path, games)

    with open(output_csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["name"] == "Test Game"
    assert rows[0]["universe_id"] == "1001"
    assert rows[0]["game_url"] == "https://www.roblox.com/games/5001"


# --- End-to-end with mocks ---

@patch("crawler.make_request")
@patch("crawler.resolve_username")
def test_full_pipeline(mock_resolve, mock_req, input_csv_path, output_csv_path):
    """End-to-end test: CSV input -> username resolution -> game fetch -> detail fetch -> CSV output."""
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    old = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Input CSV with a username
    mock_resolve.return_value = 42
    with open(input_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "id"])
        writer.writerow(["user", "zhangyk2010"])

    # Mock API responses in order:
    # 1. get_username(42)
    # 2. get_user_games page 1
    # 3. get_universe_details
    mock_req.side_effect = [
        {"name": "zhangyk2010", "id": 42},  # get_username
        {  # get_user_games
            "data": [
                {"id": 5001, "created": recent},
                {"id": 5002, "created": old},
            ],
            "nextPageCursor": None,
        },
        {  # get_universe_details
            "data": [
                {
                    "id": 5001,
                    "rootPlaceId": 9001,
                    "name": "Recent Game",
                    "description": "A new game",
                    "created": recent,
                    "updated": recent,
                    "playing": 100,
                    "visits": 5000,
                    "maxPlayers": 30,
                    "genre": "Adventure",
                },
            ],
        },
    ]

    # Run main with patched sys.argv
    import sys
    original_argv = sys.argv
    sys.argv = ["crawler.py", input_csv_path, "-o", output_csv_path, "--days", "30"]
    try:
        crawler.main()
    finally:
        sys.argv = original_argv

    # Verify output
    with open(output_csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["name"] == "Recent Game"
    assert rows[0]["owner_name"] == "zhangyk2010"
    assert rows[0]["game_url"] == "https://www.roblox.com/games/9001"
