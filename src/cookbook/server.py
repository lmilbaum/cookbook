"""Serve database-backed cookbook reports and shopping lists."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import threading
import time
import webbrowser
from dataclasses import replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO, ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .config import load_config
from .database import create_session_factory
from .import_service import ImportService
from .models import Recipe, RecipeState
from .post_import_job import import_post_by_url
from .post_repository import load_recipes, mark_not_recipe
from .recipe_image_repository import load_recipe_image
from .recipe_page_repository import load_recipe_page
from .recipe_photo_repository import load_recipe_photo, photo_ids
from .recipe_state_repository import (
    RecipeStateConflict,
    load_recipe_state,
    save_recipe_state,
)
from .shopping_list_repository import (
    ShoppingListConflict,
    load_shopping_state,
    save_shopping_list,
    valid_items,
)
from .type_repository import (
    DuplicateType,
    create_type,
    delete_type,
    get_type,
    list_types,
    rename_type,
)

_HOME_PAGE_NAME = "index.html"
_PHOTO_URL = "recipes/photos/{}"


def _render_reports(report_path: Path, recipes: list[Recipe], photos: set[str]) -> None:
    """Rebuild static pages from a database snapshot.

    ``photos`` holds the ids of recipes with a stored photo; their cards point at
    the photo route instead of the (expiring) Instagram image URL.
    """

    from . import site_pages  # Imported here so development reloads can refresh it.

    site_pages = importlib.reload(site_pages)
    recipes = [
        replace(recipe, image_url=_PHOTO_URL.format(quote(recipe.id, safe="")))
        if recipe.id in photos else recipe
        for recipe in recipes
    ]
    favicon_path = site_pages.write_favicon(report_path)
    report_path.write_text(
        site_pages.render_html(recipes, favicon_path.name),
        encoding="utf-8",
    )
    report_path.with_name("shopping_list.html").write_text(
        site_pages.render_shopping_list_html(favicon_path.name), encoding="utf-8"
    )
    report_path.with_name("notes.html").write_text(
        site_pages.render_notes_html(recipes, favicon_path.name), encoding="utf-8"
    )



def _load_report_recipes(root: Path, factory: sessionmaker[Session]) -> list[Recipe]:
    """Use the same recipe ordering as the importer when configuration exists."""

    config_path = root / "cookbook.toml"
    reverse = load_config(config_path).reverse if config_path.exists() else False
    return load_recipes(factory, reverse=reverse)


def _watch_and_render(report_path: Path, factory: sessionmaker[Session]) -> None:
    """Poll database posts, photos and renderer code, rebuilding only when they change."""

    renderer_path = Path(__file__).with_name("site_pages.py")
    previous: tuple[int, list[Recipe], set[str]] | None = None
    while True:
        try:
            current = (
                renderer_path.stat().st_mtime_ns,
                _load_report_recipes(report_path.parent, factory),
                photo_ids(factory),
            )
            if current != previous:
                _render_reports(report_path, current[1], current[2])
                previous = current
                print("Reload mode: updated report pages. Refresh the browser to view changes.")
        except SQLAlchemyError:
            print("Reload mode: unable to read cookbook posts from the database.")
        except (OSError, TypeError, ValueError) as error:
            print(f"Reload mode: unable to update report pages: {error}")
        time.sleep(1)


def _valid_items(value: Any) -> bool:
    """Return whether value is a safe shopping-list payload."""

    return valid_items(value)


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


_RECIPE_PAGE_PATH = re.compile(r"^/recipes/([^/]+)\.html$")
_RECIPE_IMAGE_PATH = re.compile(r"^/recipes/assets/([^/]+)$")
_RECIPE_PHOTO_PATH = re.compile(r"^/recipes/photos/([^/]+)$")
# Saved recipe edits still point at the old cached files, e.g. /lizapanelim_posts_assets/<id>.jpg.
_LEGACY_PHOTO_PATH = re.compile(r"^/[^/]+_posts_assets/([^/]+)\.(?:jpg|jpeg|png|webp)$")
_NOT_RECIPE_PATH = re.compile(r"^/api/recipes/([^/]+)/not-recipe$")
_TYPES_PATH = re.compile(r"^/api/recipe-types(?:/(\d+))?$")


def make_handler(root: Path, factory: sessionmaker[Session]) -> type[SimpleHTTPRequestHandler]:
    """Create a request handler bound to the cookbook directory and database."""

    imports = ImportService(
        root,
        lambda: _render_reports(
            root / _HOME_PAGE_NAME, _load_report_recipes(root, factory), photo_ids(factory)
        ),
    )

    class CookbookHandler(SimpleHTTPRequestHandler):
        extensions_map: ClassVar[dict[str, str]] = {**SimpleHTTPRequestHandler.extensions_map, ".webp": "image/webp"}

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def send_head(self) -> BinaryIO | None:
            """Serve generated pages and images without exposing local data files."""
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                path = self.path = f"/{_HOME_PAGE_NAME}"
            candidate = (root / path.lstrip("/")).resolve()
            allowed = False
            if candidate.is_relative_to(root.resolve()):
                relative = candidate.relative_to(root.resolve())
                allowed = relative.as_posix() in {
                    _HOME_PAGE_NAME, "shopping_list.html", "notes.html", "favicon.svg",
                }
            if not allowed or not candidate.is_file():
                self.send_error(404, "Not found")
                return None
            return super().send_head()

        def _json_response(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _handle_types(self, method: str) -> bool:
            """Serve /api/recipe-types[/<id>]; return False if the path is not a types route."""

            match = _TYPES_PATH.fullmatch(urlsplit(self.path).path)
            if not match:
                return False
            type_id = int(match.group(1)) if match.group(1) else None
            allowed = {"GET", "POST"} if type_id is None else {"GET", "PUT", "DELETE"}
            if method not in allowed:
                self._json_response(405, {"error": "Method not allowed"})
                return True
            name = None
            if method in {"POST", "PUT"}:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 10_000:
                        raise ValueError
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict) or set(body) != {"name"}:
                        raise ValueError
                    name = body["name"]
                except (ValueError, UnicodeDecodeError):
                    self._json_response(400, {"error": "Expected a JSON object with a name"})
                    return True
            try:
                if method == "GET" and type_id is None:
                    self._json_response(200, list_types(factory))
                elif method == "GET":
                    record = get_type(factory, type_id)
                    self._json_response(*((200, record) if record else (404, {"error": "Not found"})))
                elif method == "POST":
                    self._json_response(201, create_type(factory, name))
                elif method == "PUT":
                    record = rename_type(factory, type_id, name)
                    self._json_response(*((200, record) if record else (404, {"error": "Not found"})))
                else:
                    deleted = delete_type(factory, type_id)
                    self._json_response(*((200, {}) if deleted else (404, {"error": "Not found"})))
            except DuplicateType:
                self._json_response(409, {"error": "A type with this name already exists"})
            except ValueError:
                self._json_response(400, {"error": "Invalid type name"})
            except SQLAlchemyError:
                self._json_response(503, {"error": "Unable to access types"})
            return True

        def do_DELETE(self) -> None:
            if not self._handle_types("DELETE"):
                self._json_response(404, {"error": "Not found"})

        def do_GET(self) -> None:
            if self._handle_types("GET"):
                return
            request_path = unquote(urlsplit(self.path).path)
            recipe_image_match = _RECIPE_IMAGE_PATH.fullmatch(request_path)
            recipe_photo_match = _RECIPE_PHOTO_PATH.fullmatch(request_path) or _LEGACY_PHOTO_PATH.fullmatch(request_path)
            if recipe_image_match or recipe_photo_match:
                try:
                    image = (
                        load_recipe_image(factory, recipe_image_match.group(1))
                        if recipe_image_match
                        else load_recipe_photo(factory, recipe_photo_match.group(1))
                    )
                except SQLAlchemyError:
                    self.send_error(503, "Unable to read recipe image")
                    return
                if image is None:
                    self.send_error(404, "Not found")
                    return
                data, content_type = image
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            recipe_page_match = _RECIPE_PAGE_PATH.fullmatch(request_path)
            if recipe_page_match:
                try:
                    html = load_recipe_page(factory, recipe_page_match.group(1))
                except SQLAlchemyError:
                    self.send_error(503, "Unable to read recipe page")
                    return
                if html is None:
                    self.send_error(404, "Not found")
                    return
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if urlsplit(self.path).path == "/api/import-post":
                self._json_response(200, imports.status())
                return
            if urlsplit(self.path).path == "/api/recipe-state":
                try:
                    payload = load_recipe_state(factory)
                except SQLAlchemyError:
                    self._json_response(503, {"error": "Unable to read recipe state"})
                    return
                self._json_response(200, payload)
                return
            if urlsplit(self.path).path != "/api/shopping-list":
                super().do_GET()
                return
            try:
                items = load_shopping_state(factory)
            except SQLAlchemyError:
                self._json_response(503, {"error": "Unable to read shopping list"})
                return
            self._json_response(200, items)

        def do_PUT(self) -> None:
            if self._handle_types("PUT"):
                return
            if urlsplit(self.path).path == "/api/recipe-state":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1_000_000:
                        raise ValueError
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict) or set(payload) != {"state", "revision"}:
                        raise ValueError
                    revision = save_recipe_state(factory, payload["state"], payload["revision"])
                except RecipeStateConflict:
                    self._json_response(409, {"error": "Recipe state changed; reload before saving"})
                    return
                except (ValueError, UnicodeDecodeError):
                    self._json_response(400, {"error": "Invalid recipe state"})
                    return
                except SQLAlchemyError:
                    self._json_response(503, {"error": "Unable to save recipe state"})
                    return
                self._json_response(200, {"revision": revision})
                return
            if urlsplit(self.path).path != "/api/shopping-list":
                self._json_response(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
                    raise ValueError
                items = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self._json_response(400, {"error": "Invalid JSON"})
                return
            if (not isinstance(items, dict) or set(items) != {"items", "revision"}
                or type(items["revision"]) is not int or items["revision"] < 0
                or not _valid_items(items["items"])):
                self._json_response(400, {"error": "Invalid shopping list"})
                return
            try:
                revision = save_shopping_list(factory, items["items"], items["revision"])
            except ShoppingListConflict:
                self._json_response(409, {"error": "Shopping list changed; reload before saving"})
                return
            except SQLAlchemyError:
                self._json_response(503, {"error": "Unable to save shopping list"})
                return
            self._json_response(200, {"revision": revision})

        def do_POST(self) -> None:
            if self._handle_types("POST"):
                return
            not_recipe_match = _NOT_RECIPE_PATH.fullmatch(unquote(urlsplit(self.path).path))
            if not_recipe_match:
                try:
                    marked = mark_not_recipe(factory, not_recipe_match.group(1))
                except SQLAlchemyError:
                    self._json_response(503, {"error": "Unable to update recipe"})
                    return
                if not marked:
                    self._json_response(404, {"error": "Not found"})
                    return
                try:
                    imports.refresh()
                except (SQLAlchemyError, OSError, TypeError, ValueError):
                    pass  # The change is persisted; the report will pick it up on the next render.
                self._json_response(200, {})
                return
            if urlsplit(self.path).path == "/api/import-post":
                try:
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        raise ValueError
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 100 or json.loads(self.rfile.read(length)) != {}:
                        raise ValueError
                except ValueError:
                    self._json_response(400, {"error": "Expected an empty JSON object"})
                    return
                started = imports.start()
                self._json_response(202 if started else 409, imports.status())
                return
            if urlsplit(self.path).path == "/api/import-instagram-url":
                try:
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        raise ValueError
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 10_000:
                        raise ValueError
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict) or "url" not in body or not isinstance(body["url"], str):
                        raise ValueError
                    url = body["url"].strip()
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    self._json_response(400, {"error": "Expected a JSON object with a url"})
                    return
                result = import_post_by_url(root, factory, url)
                if result is None:
                    self._json_response(503, {"error": "Failed to import post from Instagram"})
                    return
                shortcode, source, source_name = result
                try:
                    imports.refresh()
                except (SQLAlchemyError, OSError, TypeError, ValueError):
                    pass
                self._json_response(200, {"id": shortcode, "source": source, "sourceName": source_name})
                return
            if urlsplit(self.path).path != "/api/trello/cards":
                self._json_response(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
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


def empty_database_warning(factory: sessionmaker[Session]) -> str | None:
    """Explain how to recover if the database holds no recipes and no saved edits.

    An empty database is normal on a first run but is also what remains after
    Docker storage or the data folder is deleted, so say so loudly at startup.
    """

    try:
        with factory() as session:
            recipes = session.scalar(select(func.count()).select_from(Recipe))
            states = session.scalar(select(func.count()).select_from(RecipeState))
    except SQLAlchemyError:
        return None
    if recipes or states:
        return None
    return (
        "WARNING: the database has no recipes and no saved recipe edits. If this is "
        "unexpected (for example the database folder or Docker storage was deleted), "
        "restore the newest dump in .private-backups/ with pg_restore, or re-import "
        "posts with: uv run cookbook-import-post-store --store <posts_items directory>. "
        "Create backups regularly with: make backup"
    )


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
        help="Automatically rebuild report pages when renderer code or database posts change.",
    )
    args = parser.parse_args()
    root = args.directory.resolve()
    load_dotenv(root / ".env")
    factory = create_session_factory()
    if warning := empty_database_warning(factory):
        print(warning, file=sys.stderr)
    report_path = root / _HOME_PAGE_NAME
    _render_reports(report_path, _load_report_recipes(report_path.parent, factory), photo_ids(factory))
    if args.reload:
        threading.Thread(
            target=_watch_and_render,
            args=(report_path, factory),
            daemon=True,
        ).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root, factory))
    url = f"http://{args.host}:{args.port}/"
    print(f"Cookbook available at {url}")
    print("Shopping list saved to the database.")
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
