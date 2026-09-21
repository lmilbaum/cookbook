"""Recipe card photos live in the database, not in *_posts_assets/ files."""

from __future__ import annotations

import sys

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from migration_helpers import load_migration
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from cookbook import main as cli
from cookbook import recipe_photo_fetch, recipe_photo_import
from cookbook.database import Base
from cookbook.models import Post, Recipe, RecipePhoto
from cookbook.post_repository import load_recipes
from cookbook.recipe_photo_repository import (
    insert_recipe_photo,
    load_recipe_photo,
    photo_ids,
)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _recipe(code: str, image_url: str = "https://cdn.example/x.jpg") -> Recipe:
    recipe = Recipe(id=code, image_url=image_url, caption="", timestamp_utc="2026-01-01")
    recipe.post = Post(shortcode=code, url="https://example.com", typename="GraphImage", is_video=False)
    return recipe


def test_photo_is_stored_once_and_never_replaced(factory) -> None:
    assert insert_recipe_photo(factory, "a", "image/jpeg", b"first")
    assert not insert_recipe_photo(factory, "a", "image/png", b"second")
    assert load_recipe_photo(factory, "a") == (b"first", "image/jpeg")
    assert load_recipe_photo(factory, "missing") is None
    assert photo_ids(factory) == {"a"}


def test_only_recipes_without_a_photo_are_downloaded(factory, monkeypatch) -> None:
    insert_recipe_photo(factory, "stored", "image/jpeg", b"kept")
    downloaded = []

    def download(recipe):
        downloaded.append(recipe.id)
        return (b"fresh", "image/jpeg") if recipe.id != "broken" else None

    monkeypatch.setattr(recipe_photo_fetch, "download_photo", download)
    recipes = [_recipe("stored"), _recipe("new"), _recipe("broken"), _recipe("local", image_url="")]
    assert recipe_photo_fetch.store_missing_photos(factory, recipes) == 1
    assert downloaded == ["new", "broken"]
    assert photo_ids(factory) == {"stored", "new"}
    assert load_recipe_photo(factory, "stored") == (b"kept", "image/jpeg")


def test_download_falls_back_to_instagram_media_endpoint(monkeypatch) -> None:
    requested = []

    class Response:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    def urlopen(request, timeout):
        requested.append(request.full_url)
        if "media" not in request.full_url:
            raise OSError("expired")
        return Response(b"image")

    monkeypatch.setattr(recipe_photo_fetch, "urlopen", urlopen)
    assert recipe_photo_fetch.download_photo(_recipe("abc", "https://cdn.example/x.png?sig=1")) == (b"image", "image/png")
    assert requested == ["https://cdn.example/x.png?sig=1", "https://www.instagram.com/p/abc/media/?size=l"]


def test_cli_stores_recipes_and_photos_without_writing_report_files(factory, tmp_path, monkeypatch) -> None:
    (tmp_path / "cookbook.toml").write_text('username = "example"\nlimit = 5\nreverse = false\n')
    monkeypatch.setattr(sys, "argv", ["cookbook", "--config", str(tmp_path / "cookbook.toml")])
    monkeypatch.setattr(cli, "create_session_factory", lambda: factory)
    monkeypatch.setattr(cli, "_fetch_posts_with_fallback", lambda *args: [_recipe("new")])
    monkeypatch.setattr(recipe_photo_fetch, "download_photo", lambda recipe: (b"image", "image/jpeg"))
    before = {path.name for path in tmp_path.iterdir()}

    cli.main()

    assert [recipe.id for recipe in load_recipes(factory, reverse=False)] == ["new"]
    assert load_recipe_photo(factory, "new") == (b"image", "image/jpeg")
    assert {path.name for path in tmp_path.iterdir()} == before


def test_cli_strict_window_mode_writes_nothing(factory, tmp_path, monkeypatch) -> None:
    (tmp_path / "cookbook.toml").write_text('username = "example"\nlimit = 5\nignore_cached_posts = true\n')
    monkeypatch.setattr(sys, "argv", ["cookbook", "--config", str(tmp_path / "cookbook.toml")])
    monkeypatch.setattr(cli, "create_session_factory", lambda: factory)
    monkeypatch.setattr(cli, "_fetch_posts_with_fallback", lambda *args: [_recipe("new")])
    monkeypatch.setattr(recipe_photo_fetch, "download_photo", lambda recipe: (b"image", "image/jpeg"))
    cli.main()
    assert load_recipes(factory, reverse=False) == []
    assert photo_ids(factory) == set()


def test_import_command_loads_existing_asset_files_and_keeps_them(factory, tmp_path, monkeypatch, capsys) -> None:
    assets = tmp_path / "lizapanelim_posts_assets"
    assets.mkdir()
    (assets / "BCP_gsMu-WY.jpg").write_bytes(b"jpg")
    (assets / "other.png").write_bytes(b"png")
    (assets / "notes.txt").write_text("not a photo")
    insert_recipe_photo(factory, "other", "image/png", b"database copy wins")
    monkeypatch.setattr(sys, "argv", ["import", "--directory", str(assets)])
    monkeypatch.setattr(recipe_photo_import, "create_session_factory", lambda: factory)
    monkeypatch.setattr(recipe_photo_import, "load_dotenv", lambda: None)

    recipe_photo_import.main()

    assert load_recipe_photo(factory, "BCP_gsMu-WY") == (b"jpg", "image/jpeg")
    assert load_recipe_photo(factory, "other") == (b"database copy wins", "image/png")
    assert "Imported 1 of 2" in capsys.readouterr().out
    assert sorted(path.name for path in assets.iterdir()) == ["BCP_gsMu-WY.jpg", "notes.txt", "other.png"]


def test_migration_creates_the_table_the_model_expects() -> None:
    engine = create_engine("sqlite://")
    migration = load_migration("20260921_01_recipe_photos.py")
    assert migration.down_revision == "20260919_03"
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    columns = {column["name"] for column in inspect(engine).get_columns("recipe_photos")}
    assert columns == {column.name for column in RecipePhoto.__table__.columns}
    engine.dispose()
