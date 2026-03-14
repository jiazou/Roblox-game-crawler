# Roblox API Reference

Base URLs:
- Games API: `https://games.roblox.com`
- Users API: `https://users.roblox.com`
- Groups API: `https://groups.roblox.com`

---

## Resolve username to user ID

**POST** `https://users.roblox.com/v1/usernames/users`

Request body:
```json
{"usernames": ["zhangyk2010"], "excludeBannedUsers": false}
```

Response:
```json
{
  "data": [
    {
      "id": 48032694,
      "name": "zhangyk2010",
      "requestedUsername": "zhangyk2010"
    }
  ]
}
```

---

## Get user info

**GET** `https://users.roblox.com/v1/users/{userId}`

Response:
```json
{
  "id": 48032694,
  "name": "zhangyk2010",
  "displayName": "zhangyk2010"
}
```

---

## Get user's group memberships

**GET** `https://groups.roblox.com/v1/users/{userId}/groups/roles`

Response:
```json
{
  "data": [
    {
      "group": {
        "id": 12877779,
        "name": "Diligent Farmer"
      },
      "role": {
        "id": 12345,
        "name": "Owner",
        "rank": 255
      }
    }
  ]
}
```

Filter for `role.rank == 255` to find groups the user owns.

---

## Get group info

**GET** `https://groups.roblox.com/v1/groups/{groupId}`

Response:
```json
{
  "id": 12877779,
  "name": "Diligent Farmer"
}
```

---

## Get user's games

**GET** `https://games.roblox.com/v2/users/{userId}/games`

Query parameters:
- `sortOrder`: `Desc` (newest first) or `Asc`
- `limit`: max items per page (50)
- `accessFilter`: `2` (all games including private)
- `cursor`: pagination cursor from previous response

Response:
```json
{
  "data": [
    {
      "id": 6108000001,
      "name": "Demon Soul Simulator 2",
      "created": "2026-03-01T12:00:00.000Z",
      "updated": "2026-03-10T00:00:00.000Z"
    }
  ],
  "previousPageCursor": null,
  "nextPageCursor": "eyJpZCI6MTIzfQ=="
}
```

If `nextPageCursor` is not null, pass it as `cursor` to get the next page.

---

## Get group's games

**GET** `https://games.roblox.com/v2/groups/{groupId}/games`

Query parameters:
- `sortOrder`: `Desc` (newest first) or `Asc`
- `limit`: max items per page (100)
- `accessFilter`: `2` (all games including private)
- `cursor`: pagination cursor from previous response

Response: same format as user's games.

---

## Get universe details (batch)

**GET** `https://games.roblox.com/v1/games?universeIds=ID1,ID2,ID3`

Up to 100 IDs per request, comma-separated.

Response:
```json
{
  "data": [
    {
      "id": 6108000001,
      "rootPlaceId": 80000000002,
      "name": "Demon Soul Simulator 2",
      "description": "A game description",
      "created": "2026-03-01T12:00:00.000Z",
      "updated": "2026-03-10T00:00:00.000Z",
      "playing": 1001,
      "visits": 79000001,
      "maxPlayers": 30,
      "genre": "All",
      "creator": {
        "id": 12877779,
        "name": "Diligent Farmer",
        "type": "Group"
      }
    }
  ]
}
```

Use `rootPlaceId` to construct the game URL:
`https://www.roblox.com/games/{rootPlaceId}`
