"""Tests for the file-backed cookbook server."""

from typing import Any

from cookbook import server
from cookbook.server import _valid_items


def test_valid_shopping_items() -> None:
    assert _valid_items([{"id": "item-1", "name": "Milk", "done": False}])
    assert _valid_items([])


def test_rejects_malformed_shopping_items() -> None:
    assert not _valid_items({"id": "item-1"})
    assert not _valid_items([{"id": "item-1", "name": "Milk"}])
    assert not _valid_items([{"id": "item-1", "name": "x" * 121, "done": False}])


def test_creates_card_in_named_board_first_open_list(monkeypatch: Any) -> None:
    monkeypatch.setenv("TRELLO_API_KEY", "key")
    monkeypatch.setenv("TRELLO_API_TOKEN", "token")
    monkeypatch.setenv("TRELLO_BOARD_NAME", "My To Do List")
    monkeypatch.delenv("TRELLO_LIST_NAME", raising=False)
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    def fake_request(
        method: str,
        path: str,
        _api_key: str,
        _token: str,
        parameters: dict[str, str] | None = None,
    ) -> Any:
        calls.append((method, path, parameters))
        if path == "members/me/boards":
            return [{"id": "board-1", "name": "My To Do List"}]
        if path == "boards/board-1/lists":
            return [{"id": "list-1", "name": "Tasks"}]
        if path == "lists/list-1/cards":
            return []
        if path == "cards":
            return {"id": "card-1", "url": "https://trello.com/c/card-1"}
        if path == "cards/card-1/checklists":
            return {"id": "checklist-1"}
        return {"id": "check-item-1"}

    monkeypatch.setattr(server, "_trello_request", fake_request)
    result = server._create_trello_card(
        [{"id": "item-1", "name": "Milk", "done": False}]
    )

    assert result == {
        "id": "card-1",
        "url": "https://trello.com/c/card-1",
        "action": "created",
    }
    assert calls[-3:] == [
        (
        "POST",
        "cards",
        {"idList": "list-1", "name": "רשימת קניות"},
        ),
        ("POST", "cards/card-1/checklists", {"name": "רשימת קניות"}),
        (
            "POST",
            "checklists/checklist-1/checkItems",
            {"name": "Milk", "checked": "false"},
        ),
    ]


def test_updates_existing_card_instead_of_creating_another(monkeypatch: Any) -> None:
    monkeypatch.setenv("TRELLO_API_KEY", "key")
    monkeypatch.setenv("TRELLO_API_TOKEN", "token")
    monkeypatch.setenv("TRELLO_BOARD_NAME", "My To Do List")
    monkeypatch.setenv("TRELLO_LIST_NAME", "Today")
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    def fake_request(
        method: str,
        path: str,
        _api_key: str,
        _token: str,
        parameters: dict[str, str] | None = None,
    ) -> Any:
        calls.append((method, path, parameters))
        responses: dict[str, Any] = {
            "members/me/boards": [{"id": "board-1", "name": "My To Do List"}],
            "boards/board-1/lists": [{"id": "list-1", "name": "Today"}],
            "lists/list-1/cards": [
                {"id": "card-1", "name": "רשימת קניות", "url": "https://trello.com/c/card-1"}
            ],
            "cards/card-1/checklists": [
                {
                    "id": "checklist-1",
                    "name": "רשימת קניות",
                    "checkItems": [
                        {"id": "check-item-1", "name": "Milk", "state": "incomplete"}
                    ],
                }
            ],
        }
        if method == "POST" and path == "cards/card-1/checklists":
            return {"id": "checklist-1"}
        return responses[path]

    monkeypatch.setattr(server, "_trello_request", fake_request)
    result = server._create_trello_card(
        [{"id": "item-1", "name": "Milk", "done": False}]
    )

    assert result["id"] == "card-1"
    assert result["action"] == "updated"
    assert not any(method == "POST" and path == "cards" for method, path, _ in calls)
    assert not any(method in {"POST", "PUT", "DELETE"} for method, _, _ in calls)
