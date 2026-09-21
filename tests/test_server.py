"""Tests for the cookbook server."""

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


def test_database_shopping_api(tmp_path, monkeypatch) -> None:
    import io
    import json

    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import sessionmaker

    from cookbook.database import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    handler_type = server.make_handler(tmp_path, factory)
    handler = object.__new__(handler_type)
    assert handler.guess_type("image.webp") == "image/webp"
    handler.path = "/api/shopping-list"
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))
    legacy = tmp_path / "shopping_list.json"
    legacy.write_text("legacy file remains untouched")
    handler.do_GET()
    assert responses.pop() == (200, {"items": [], "revision": 0})

    def put(payload, revision=0):
        body = json.dumps({"items": payload, "revision": revision}).encode()
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.do_PUT()
        return responses.pop()

    items = [{"id": "a", "name": "Milk", "done": False, "quantity": "2"}]
    assert put(items) == (200, {"revision": 1})
    handler.do_GET()
    assert responses.pop() == (200, {"items": items, "revision": 1})
    assert put(items * 2)[0] == 400
    assert put([{**items[0], "quantity": 2}])[0] == 400
    handler.do_GET()
    assert responses.pop() == (200, {"items": items, "revision": 1})
    assert put(items)[0] == 409
    assert put([], 1)[0] == 200
    handler.do_GET()
    assert responses.pop() == (200, {"items": [], "revision": 2})
    assert legacy.read_text() == "legacy file remains untouched"

    def unavailable(*args):
        raise SQLAlchemyError("private connection details")

    monkeypatch.setattr(server, "save_shopping_list", unavailable)
    assert put(items) == (503, {"error": "Unable to save shopping list"})
    monkeypatch.setattr(server, "load_shopping_state", unavailable)
    handler.do_GET()
    assert responses.pop() == (503, {"error": "Unable to read shopping list"})
    engine.dispose()


def test_not_recipe_api_hides_post_and_regenerates_report(tmp_path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cookbook.database import Base
    from cookbook.models import Post, Recipe
    from cookbook.post_repository import insert_missing_recipes

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    item = Recipe(
        id="database-recipe", image_url="",
        caption="caption", timestamp_utc="2026-01-01T00:00:00+00:00", title="A recipe",
    )
    item.post = Post(shortcode="database-recipe", url="https://example.com/recipe", typename="GraphImage", is_video=False)
    insert_missing_recipes(factory, [item])

    handler_type = server.make_handler(tmp_path, factory)
    handler = object.__new__(handler_type)
    responses = []
    handler._json_response = lambda status, payload: responses.append((status, payload))

    handler.path = "/api/recipes/missing-recipe/not-recipe"
    handler.do_POST()
    assert responses.pop() == (404, {"error": "Not found"})

    handler.path = "/api/recipes/database-recipe/not-recipe"
    handler.do_POST()
    assert responses.pop() == (200, {})
    assert "A recipe" not in (tmp_path / "index.html").read_text()
    engine.dispose()


def test_reports_use_database_posts_and_preserve_legacy_json(tmp_path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cookbook.database import Base
    from cookbook.models import Post, Recipe
    from cookbook.post_repository import (
        insert_missing_recipes,
        load_recipes,
        mark_not_recipe,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    legacy = tmp_path / "lizapanelim_posts.json"
    legacy.write_text("invalid legacy JSON must not be read")
    report = tmp_path / "index.html"
    item = Recipe(
        id="database-recipe", image_url="",
        caption="Database recipe caption", timestamp_utc="2026-01-01T00:00:00+00:00",
        title="Database recipe title",
    )
    item.post = Post(shortcode="database-recipe", url="https://example.com/recipe", typename="GraphImage", is_video=False)
    item.image_url = "https://expired.example/recipe.jpg"
    insert_missing_recipes(factory, [item])
    server._render_reports(report, load_recipes(factory, reverse=False), {item.id})
    assert "Database recipe title" in report.read_text()
    assert "recipes/photos/database-recipe" in report.read_text()
    assert "expired.example" not in report.read_text()
    assert load_recipes(factory, reverse=False)[0].image_url == item.image_url
    assert (tmp_path / "notes.html").exists()
    assert (tmp_path / "shopping_list.html").exists()
    mark_not_recipe(factory, item.post.shortcode)
    server._render_reports(report, load_recipes(factory, reverse=False), {item.id})
    assert "Database recipe title" not in report.read_text()
    assert legacy.read_text() == "invalid legacy JSON must not be read"
    engine.dispose()


def test_reload_retries_database_failure_and_only_renders_changes(tmp_path, monkeypatch, capsys) -> None:
    import pytest
    from sqlalchemy.exc import SQLAlchemyError

    snapshots = iter([SQLAlchemyError("secret"), [], [], ["changed"]])
    rendered = []
    polls = 0

    def load(*args, **kwargs):
        snapshot = next(snapshots)
        if isinstance(snapshot, Exception):
            raise snapshot
        return snapshot

    def sleep(_seconds):
        nonlocal polls
        polls += 1
        if polls == 4:
            raise KeyboardInterrupt

    monkeypatch.setattr(server, "load_recipes", load)
    monkeypatch.setattr(server, "photo_ids", lambda factory: set())
    monkeypatch.setattr(server, "_render_reports", lambda path, posts, photos: rendered.append(posts))
    monkeypatch.setattr(server.time, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        server._watch_and_render(tmp_path / "report.html", None)
    assert rendered == [[], ["changed"]]
    assert "secret" not in capsys.readouterr().out


def test_report_order_honors_config_and_reload_changes(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cookbook.database import Base
    from cookbook.models import Recipe
    from cookbook.post_repository import insert_missing_recipes

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    recipes = [Recipe(
        id=name, image_url="", caption="", timestamp_utc=date,
    ) for name, date in [("newest", "2026-02-01"), ("oldest", "2026-01-01")]]
    insert_missing_recipes(factory, recipes)

    def order():
        return [recipe.id for recipe in server._load_report_recipes(tmp_path, factory)]

    assert order() == ["newest", "oldest"]
    config = tmp_path / "cookbook.toml"
    config.write_text('username = "example"\nreverse = true\n')
    assert order() == ["oldest", "newest"]
    config.write_text('username = "example"\nreverse = false\n')
    assert order() == ["newest", "oldest"]
    engine.dispose()


def test_static_serving_blocks_local_data_and_backups(tmp_path):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import urlopen

    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from cookbook.database import Base

    (tmp_path / 'index.html').write_text('Cookbook')
    (tmp_path / '.env').write_text('private fixture')
    backups = tmp_path / '.private-backups'
    backups.mkdir()
    (backups / 'backup.dump').write_bytes(b'private fixture')
    # Legacy cached photos on disk are no longer served: photos come from the database.
    assets = tmp_path / 'lizapanelim_posts_assets'
    assets.mkdir()
    (assets / 'test.jpg').write_bytes(b'image fixture')
    (assets / 'secret.jpg').symlink_to(backups / 'backup.dump')
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(tmp_path, factory))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        with urlopen(base + '/') as response:
            assert response.read() == b'Cookbook'
        for path in ['/.env', '/.private-backups/backup.dump', '/lizapanelim_posts_assets/',
                     '/lizapanelim_posts_assets/test.jpg',
                     '/lizapanelim_posts_assets/secret.jpg', '/%2eenv',
                     '/recipes/apple_cake.html', '/recipes/nested/apple_cake.html',
                     '/recipes/assets/apple-cake.jpg']:
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
        engine.dispose()


def test_recipe_page_served_from_database(tmp_path, monkeypatch) -> None:
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import urlopen

    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from cookbook.database import Base
    from cookbook.recipe_page_repository import insert_recipe_page

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    insert_recipe_page(factory, "apple_cake", "<html>Apple cake story</html>")
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(tmp_path, factory))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        with urlopen(base + '/recipes/apple_cake.html') as response:
            assert response.read() == b"<html>Apple cake story</html>"
            assert response.headers["Content-Type"] == "text/html; charset=utf-8"
        with pytest.raises(HTTPError) as error:
            urlopen(base + '/recipes/missing.html')
        assert error.value.code == 404

        def unavailable(*args):
            raise SQLAlchemyError("private connection details")

        monkeypatch.setattr(server, "load_recipe_page", unavailable)
        with pytest.raises(HTTPError) as error:
            urlopen(base + '/recipes/apple_cake.html')
        assert error.value.code == 503
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
        engine.dispose()


def test_recipe_image_served_from_database(tmp_path, monkeypatch) -> None:
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import urlopen

    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from cookbook.database import Base
    from cookbook.recipe_image_repository import insert_recipe_image

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    insert_recipe_image(factory, "apple-cake.jpg", "image/jpeg", b"recipe image fixture")
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(tmp_path, factory))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        with urlopen(base + '/recipes/assets/apple-cake.jpg') as response:
            assert response.read() == b"recipe image fixture"
            assert response.headers["Content-Type"] == "image/jpeg"
        with pytest.raises(HTTPError) as error:
            urlopen(base + '/recipes/assets/missing.jpg')
        assert error.value.code == 404

        def unavailable(*args):
            raise SQLAlchemyError("private connection details")

        monkeypatch.setattr(server, "load_recipe_image", unavailable)
        with pytest.raises(HTTPError) as error:
            urlopen(base + '/recipes/assets/apple-cake.jpg')
        assert error.value.code == 503
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
        engine.dispose()


def _factory():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cookbook.models import Recipe, RecipeState

    engine = create_engine("sqlite://")
    for model in (Recipe, RecipeState):
        model.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_warns_loudly_when_the_database_is_empty() -> None:
    """Regression: deleting Docker storage silently produced an empty cookbook."""
    warning = server.empty_database_warning(_factory())

    assert warning is not None
    assert "make backup" in warning and ".private-backups" in warning
    assert "cookbook-import-post-store" in warning


def test_no_warning_once_the_database_has_recipes_or_saved_edits() -> None:
    from cookbook.models import Recipe, RecipeState

    with_recipe = _factory()
    with with_recipe() as session:
        session.add(Recipe(id="r1", image_url="", caption="", timestamp_utc="t"))
        session.commit()
    assert server.empty_database_warning(with_recipe) is None

    with_state = _factory()
    with with_state() as session:
        session.add(RecipeState(id=1, revision=1, payload={"overrides": {}, "custom": []}))
        session.commit()
    assert server.empty_database_warning(with_state) is None


def test_no_warning_when_the_database_cannot_be_read() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    assert server.empty_database_warning(sessionmaker(bind=create_engine("sqlite://"))) is None


def test_recipe_photo_served_from_database_including_legacy_saved_urls(tmp_path) -> None:
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import urlopen

    import pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from cookbook.database import Base
    from cookbook.recipe_photo_repository import insert_recipe_photo

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    insert_recipe_photo(factory, "BCP_gsMu-WY", "image/jpeg", b"photo bytes")
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(tmp_path, factory))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        # Saved recipe edits hold the old cache URL, so it must keep resolving.
        for path in ['/recipes/photos/BCP_gsMu-WY', '/lizapanelim_posts_assets/BCP_gsMu-WY.jpg']:
            with urlopen(base + path) as response:
                assert response.read() == b"photo bytes"
                assert response.headers["Content-Type"] == "image/jpeg"
        for path in ['/recipes/photos/missing', '/lizapanelim_posts_assets/missing.jpg',
                     '/recipes/photos/nested/BCP_gsMu-WY']:
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
        engine.dispose()
