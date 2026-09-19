"""Guard the migration history against accidental edits and forks.

An applied migration must never be edited: databases that already ran it would
silently differ from a fresh install. Add a new revision instead, and record its
hash below only once it has been applied anywhere real.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from alembic.script import ScriptDirectory

_MIGRATIONS = Path(__file__).parents[1] / "migrations"
_VERSIONS = _MIGRATIONS / "versions"

# SHA-256 of every migration that has already been applied.
_FROZEN = {
    "20260908_01_migration_baseline.py": "beb3fc34f99a562be76e4ff856e49c8b49748185827664ea0b6f1224ebda38fa",
    "20260910_01_create_posts.py": "2048138c5f335ac562532d4f401da114387532aa26fdab3be5d3b30b532969d7",
    "20260910_02_add_post_recipe_status.py": "0c24cb76aeb2904e3065afa4b29ddcdc9fe720c032f6e77fba7bd89295f1eb7c",
    "20260911_01_shopping_lists.py": "151c88d8daa512580ad6e5ca914d30fa2b12797b2cb934abeb206558ca8ef782",
    "20260913_01_recipe_state.py": "24e4d8497455868ee09f76e71c617db6995d60d20022ddaff68775d51bc293c6",
    "20260914_01_shopping_revision.py": "84ad3db06672fa4711d7d5f54d68618c5ebba5c599d51084dc88791b7cc4b84c",
    "20260915_01_recipe_pages.py": "a642149b1f4762a3bf41a3a7af2e6588caca1aca2b318edfa2cfbecfb79527ec",
    "20260915_02_recipe_images.py": "690e5845857d011d9cde157dfca3d41ea8152e171955694c9da22b739a7fb0b6",
    "20260917_01_add_post_source.py": "7cb80b929a94f1c1fd7ec0d239904a68434d41051eb4b5c5bc9892a9d8cee833",
    "20260917_02_split_post_and_recipe.py": "6a1d55283b2a516249ce43099e49cffd105ad5957560330e3406427da82c21a4",
    "20260917_03_reclassify_recipe_source.py": "d497cf6b03d9475d771697ff1ab530cec1119fcce278f37aee9446446bdba4cb",
    "20260918_01_decouple_posts_from_recipes.py": "b416cb0fafeeb440e84761e4cea7fe63efeeae7c77d58175d2be639514a6b0c1",
    "20260919_01_types.py": "f1df0d743efbcc22439ff5eb8c492989861d415361086a7468deca676b031b62",
    "20260919_02_rename_tables_to_match_models.py": "00169e9c5e816ef729de735d43807d437d4570e6fb19d740eb080f2e754d8135",
    "20260919_03_rename_source_other_to_unknown.py": "2da047ffa54b2040ea80e884cc82828994b4c4715319fe9a3c857eac5761e945",
}


def _script() -> ScriptDirectory:
    return ScriptDirectory(str(_MIGRATIONS))


def test_applied_migrations_are_unchanged() -> None:
    for name, expected in _FROZEN.items():
        actual = hashlib.sha256((_VERSIONS / name).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{name} was modified. Never edit an applied migration; add a new revision instead."
        )


def test_no_applied_migration_was_removed_or_renamed() -> None:
    missing = sorted(name for name in _FROZEN if not (_VERSIONS / name).exists())
    assert not missing, f"Applied migrations are missing: {missing}"


def test_history_is_a_single_linear_chain() -> None:
    script = _script()
    assert len(script.get_heads()) == 1, (
        f"Multiple heads {script.get_heads()}: a new migration must set down_revision "
        "to the current head, not to an older revision."
    )
    revisions = list(script.walk_revisions())  # newest first
    for revision in revisions:
        assert not isinstance(revision.down_revision, tuple), f"{revision.revision} merges branches"
    assert revisions[-1].down_revision is None
    assert len(revisions) == len(list(_VERSIONS.glob("2*.py")))


def test_file_names_follow_the_chain_order() -> None:
    chain = [r.revision for r in reversed(list(_script().walk_revisions()))]
    by_name = sorted(p.name for p in _VERSIONS.glob("2*.py"))
    assert [name[:11] for name in by_name] == chain, (
        "Migration file names must sort in the same order as their down_revision chain."
    )
