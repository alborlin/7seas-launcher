"""Tests for the game library service."""

import pytest

from sevenseas.core.library import LibraryService, Game


def test_add_game(db):
    lib = LibraryService(db)
    game = lib.add_game(title="Elden Ring", slug="elden-ring", source_url="https://example.com")
    assert game.id is not None
    assert game.title == "Elden Ring"
    assert game.slug == "elden-ring"
    assert game.status == "new"


def test_add_duplicate_slug_returns_existing(db):
    lib = LibraryService(db)
    first = lib.add_game(title="Game", slug="game")
    second = lib.add_game(title="Game 2", slug="game")
    assert second.id == first.id


def test_get_by_id(db):
    lib = LibraryService(db)
    created = lib.add_game(title="Test", slug="test")
    fetched = lib.get_by_id(created.id)
    assert fetched is not None
    assert fetched.title == "Test"


def test_get_by_id_returns_none_for_missing(db):
    lib = LibraryService(db)
    assert lib.get_by_id(9999) is None


def test_get_installed(db):
    lib = LibraryService(db)
    lib.add_game(title="A", slug="a")
    g2 = lib.add_game(title="B", slug="b")
    lib.update_status(g2.id, "installed")
    installed = lib.get_installed()
    assert len(installed) == 1
    assert installed[0].slug == "b"


def test_get_by_status(db):
    lib = LibraryService(db)
    lib.add_game(title="A", slug="a")
    lib.add_game(title="B", slug="b")
    new_games = lib.get_by_status("new")
    assert len(new_games) == 2


def test_update_status(db):
    lib = LibraryService(db)
    game = lib.add_game(title="X", slug="x")
    lib.update_status(game.id, "downloading")
    updated = lib.get_by_id(game.id)
    assert updated.status == "downloading"


def test_update_game_fields(db):
    lib = LibraryService(db)
    game = lib.add_game(title="X", slug="x")
    lib.update_game(game.id, install_path="/home/user/Games/X", exe_path="game.exe")
    updated = lib.get_by_id(game.id)
    assert updated.install_path == "/home/user/Games/X"
    assert updated.exe_path == "game.exe"


def test_delete_game(db):
    lib = LibraryService(db)
    game = lib.add_game(title="Del", slug="del")
    lib.delete_game(game.id)
    assert lib.get_by_id(game.id) is None
