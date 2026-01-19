"""Tests for FastAPI provider routes."""

from __future__ import annotations

import pytest


class TestProviderRoutes:
    """Tests for FastAPI provider routes."""

    def test_list_providers(self, api_client):
        response = api_client.get("/providers/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_provider_config(self, api_client):
        response = api_client.get("/providers/pixabay")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "pixabay"
        assert data["name"] == "Pixabay"

    def test_get_nonexistent_provider(self, api_client):
        response = api_client.get("/providers/nonexistent")
        assert response.status_code == 404

    def test_cache_stats(self, api_client):
        response = api_client.get("/providers/cache/stats")
        assert response.status_code == 200

        data = response.json()
        assert "memory" in data

    def test_clear_cache(self, api_client):
        response = api_client.post("/providers/cache/clear")
        assert response.status_code == 200
