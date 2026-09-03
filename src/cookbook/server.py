"""Serve the cookbook and persist its shopping list to disk."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from .models import PostItem


def _render_reports(data_file: Path) -> None:
    """Rebuild static report pages from the existing post data."""

    from . import report_html  # Imported here so development reloads can refresh it.

    report_html = importlib.reload(report_html)
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Post data must contain a list: {data_file}")
    posts = [PostItem(**item) for item in payload]
    favicon_path = report_html.write_favicon(data_file)
    html_path = data_file.with_suffix(".html")
    html_path.write_text(
        report_html.render_html(
            posts,
            data_file.stem.removesuffix("_posts"),
            favicon_path.name,
        ),
        encoding="utf-8",
    )
    html_path.with_name("shopping_list.html").write_text(
        report_html.render_shopping_list_html(favicon_path.name), encoding="utf-8"
    )
    html_path.with_name("notes.html").write_text(
        report_html.render_notes_html(posts, favicon_path.name), encoding="utf-8"
    )


def _watch_and_render(data_file: Path) -> None:
    """Rebuild report pages whenever their renderer or source data changes."""

    watched_paths = (Path(__file__).with_name("report_html.py"), data_file)
    modified = {
        path: path.stat().st_mtime_ns if path.exists() else 0 for path in watched_paths
    }
    try:
        _render_reports(data_file)
        print("Reload mode: generated report pages.")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Reload mode: unable to generate report pages: {error}")
    while True:
        time.sleep(0.5)
        current = {
            path: path.stat().st_mtime_ns if path.exists() else 0 for path in watched_paths
        }
        if current == modified:
            continue
        modified = current
        try:
            _render_reports(data_file)
            print("Reload mode: updated report pages. Refresh the browser to view changes.")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            print(f"Reload mode: unable to update report pages: {error}")


def _valid_items(value: Any) -> bool:
    """Return whether value is a safe shopping-list payload."""

    return isinstance(value, list) and all(
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("name"), str)
        and len(item["name"]) <= 120
        and isinstance(item.get("done"), bool)
        for item in value
    )


def _trello_request(
    method: str,
    path: str,
    api_key: str,
    token: str,
    parameters: dict[str, str] | None = None,
) -> Any:
    """Call Trello's REST API and decode its JSON response."""

    values = {"key": api_key, "token": token, **(parameters or {})}
    encoded = urlencode(values).encode("utf-8")
    url = f"https://api.trello.com/1/{path}"
    request = Request(
        f"{url}?{encoded.decode('utf-8')}" if method == "GET" else url,
        data=None if method == "GET" else encoded,
        method=method,
        headers={"Accept": "application/json"},
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def _create_trello_card(items: list[dict[str, Any]]) -> dict[str, str]:
    """Create a shopping-list card in the configured Trello board."""

    api_key = os.getenv("TRELLO_API_KEY", "").strip()
    token = os.getenv("TRELLO_API_TOKEN", "").strip()
    board_name = os.getenv("TRELLO_BOARD_NAME", "My To Do List").strip()
    list_name = os.getenv("TRELLO_LIST_NAME", "").strip()
    if not api_key or not token:
        raise RuntimeError("TRELLO_API_KEY and TRELLO_API_TOKEN are required")

    boards = _trello_request(
        "GET", "members/me/boards", api_key, token, {"fields": "id,name", "filter": "open"}
    )
    board = next((candidate for candidate in boards if candidate.get("name") == board_name), None)
    if board is None:
        raise LookupError(f'Trello board "{board_name}" was not found')

    lists = _trello_request(
        "GET", f"boards/{board['id']}/lists", api_key, token, {"fields": "id,name", "filter": "open"}
    )
    target_list = (
        next((candidate for candidate in lists if candidate.get("name") == list_name), None)
        if list_name
        else next(iter(lists), None)
    )
    if target_list is None:
        detail = f' named "{list_name}"' if list_name else ""
        raise LookupError(f"No open Trello list{detail} was found in the board")

    cards = _trello_request(
        "GET",
        f"lists/{target_list['id']}/cards",
        api_key,
        token,
        {"fields": "id,name,url", "filter": "open"},
    )
    card = next((candidate for candidate in cards if candidate.get("name") == "רשימת קניות"), None)
    action = "updated"
    existing_checklist = None
    if card is None:
        action = "created"
        card = _trello_request(
            "POST",
            "cards",
            api_key,
            token,
            {"idList": target_list["id"], "name": "רשימת קניות"},
        )
    else:
        checklists = _trello_request(
            "GET",
            f"cards/{card['id']}/checklists",
            api_key,
            token,
            {
                "fields": "id,name",
                "checkItems": "all",
                "checkItem_fields": "id,name,state",
            },
        )
        existing_checklist = next(
            (candidate for candidate in checklists if candidate.get("name") == "רשימת קניות"),
            None,
        )
    if card is None or existing_checklist is None:
        checklist = _trello_request(
            "POST",
            f"cards/{card['id']}/checklists",
            api_key,
            token,
            {"name": "רשימת קניות"},
        )
        existing_items: list[dict[str, Any]] = []
    else:
        checklist = existing_checklist
        existing_items = list(checklist.get("checkItems", []))

    for item in items:
        matching_index = next(
            (index for index, candidate in enumerate(existing_items) if candidate.get("name") == item["name"]),
            None,
        )
        if matching_index is None:
            _trello_request(
                "POST",
                f"checklists/{checklist['id']}/checkItems",
                api_key,
                token,
                {"name": item["name"], "checked": "true" if item["done"] else "false"},
            )
            continue
        existing_item = existing_items.pop(matching_index)
        desired_state = "complete" if item["done"] else "incomplete"
        if existing_item.get("state") != desired_state:
            _trello_request(
                "PUT",
                f"cards/{card['id']}/checkItem/{existing_item['id']}",
                api_key,
                token,
                {"state": desired_state},
            )

    for obsolete_item in existing_items:
        _trello_request(
            "DELETE",
            f"checklists/{checklist['id']}/checkItems/{obsolete_item['id']}",
            api_key,
            token,
        )
    return {"id": card["id"], "url": card["url"], "action": action}


def make_handler(root: Path, data_path: Path) -> type[SimpleHTTPRequestHandler]:
    """Create a request handler bound to the cookbook and data paths."""

    class CookbookHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def _json_response(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if urlsplit(self.path).path != "/api/shopping-list":
                super().do_GET()
                return
            if not data_path.exists():
                self._json_response(200, None)
                return
            try:
                items = json.loads(data_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._json_response(500, {"error": "Unable to read shopping list"})
                return
            self._json_response(200, items)

        def do_PUT(self) -> None:
            if urlsplit(self.path).path != "/api/shopping-list":
                self._json_response(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    raise ValueError
                items = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self._json_response(400, {"error": "Invalid JSON"})
                return
            if not _valid_items(items):
                self._json_response(400, {"error": "Invalid shopping list"})
                return
            temporary_path = data_path.with_suffix(f"{data_path.suffix}.tmp")
            temporary_path.write_text(
                json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary_path.replace(data_path)
            self._json_response(200, {"saved": True})

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/trello/cards":
                self._json_response(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    raise ValueError
                items = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self._json_response(400, {"error": "Invalid JSON"})
                return
            if not _valid_items(items) or not items:
                self._json_response(400, {"error": "Invalid shopping list"})
                return
            try:
                load_dotenv(root / ".env", override=True)
                card = _create_trello_card(items)
            except RuntimeError as error:
                self._json_response(503, {"error": str(error)})
                return
            except LookupError as error:
                self._json_response(404, {"error": str(error)})
                return
            except (HTTPError, URLError, TimeoutError):
                self._json_response(502, {"error": "Trello request failed"})
                return
            self._json_response(201, card)

    return CookbookHandler


def main() -> None:
    """Run the local cookbook web server."""

    parser = argparse.ArgumentParser(description="Serve the cookbook locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Automatically rebuild report pages when renderer code or post data changes.",
    )
    args = parser.parse_args()
    root = args.directory.resolve()
    load_dotenv(root / ".env")
    data_path = root / "shopping_list.json"
    report_data_path = root / "lizapanelim_posts.json"
    if args.reload:
        threading.Thread(
            target=_watch_and_render,
            args=(report_data_path,),
            daemon=True,
        ).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root, data_path))
    url = f"http://{args.host}:{args.port}/lizapanelim_posts.html"
    print(f"Cookbook available at {url}")
    print(f"Shopping list saved to {data_path}")
    if not args.no_open:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
