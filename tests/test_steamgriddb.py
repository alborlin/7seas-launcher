"""Tests for the SteamGridDB API client."""

from unittest.mock import MagicMock

import pytest

from sevenseas.core.steamgriddb import SteamGridDBClient


@pytest.fixture
def client():
    return SteamGridDBClient(api_key="test-key")


def test_search_game(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "success": True,
        "data": [
            {"id": 2254, "name": "Half-Life 2", "types": ["steam"], "verified": True},
            {"id": 9999, "name": "Half-Life 2: Episode One", "types": ["steam"], "verified": True},
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    client._http = MagicMock()
    client._http.get.return_value = mock_resp

    results = client.search_game("Half-Life 2")
    assert len(results) == 2
    assert results[0]["id"] == 2254
    assert results[0]["name"] == "Half-Life 2"
    client._http.get.assert_called_once_with("/search/autocomplete/Half-Life%202")


def test_search_game_no_results(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True, "data": []}
    mock_resp.raise_for_status = MagicMock()
    client._http = MagicMock()
    client._http.get.return_value = mock_resp

    results = client.search_game("xyznonexistent")
    assert results == []


def test_get_artwork_urls(client):
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/grids/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 1, "score": 5, "url": "https://cdn.steamgriddb.com/grid/abc.png"},
            ]}
        elif "/heroes/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 2, "score": 3, "url": "https://cdn.steamgriddb.com/hero/def.png"},
            ]}
        elif "/logos/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 3, "score": 4, "url": "https://cdn.steamgriddb.com/logo/ghi.png"},
            ]}
        elif "/icons/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 4, "score": 2, "url": "https://cdn.steamgriddb.com/icon/jkl.png"},
            ]}
        else:
            resp.json.return_value = {"success": True, "data": []}
        return resp

    client._http = MagicMock()
    client._http.get.side_effect = mock_get

    urls = client.get_artwork_urls(game_id=2254)
    assert urls["grid"] == "https://cdn.steamgriddb.com/grid/abc.png"
    assert urls["hero"] == "https://cdn.steamgriddb.com/hero/def.png"
    assert urls["logo"] == "https://cdn.steamgriddb.com/logo/ghi.png"
    assert urls["icon"] == "https://cdn.steamgriddb.com/icon/jkl.png"


def test_get_artwork_urls_missing_types(client):
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"success": True, "data": []}
        return resp

    client._http = MagicMock()
    client._http.get.side_effect = mock_get

    urls = client.get_artwork_urls(game_id=2254)
    assert urls["grid"] is None
    assert urls["hero"] is None
    assert urls["logo"] is None
    assert urls["icon"] is None


def test_get_artwork_urls_picks_highest_score(client):
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/grids/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 1, "score": 2, "url": "https://cdn.steamgriddb.com/grid/low.png"},
                {"id": 2, "score": 8, "url": "https://cdn.steamgriddb.com/grid/high.png"},
                {"id": 3, "score": 5, "url": "https://cdn.steamgriddb.com/grid/mid.png"},
            ]}
        else:
            resp.json.return_value = {"success": True, "data": []}
        return resp

    client._http = MagicMock()
    client._http.get.side_effect = mock_get

    urls = client.get_artwork_urls(game_id=2254)
    assert urls["grid"] == "https://cdn.steamgriddb.com/grid/high.png"
