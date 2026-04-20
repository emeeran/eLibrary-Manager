"""Tests for API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_list_empty_library(client: AsyncClient):
    """Test listing books when library is empty."""
    response = await client.get("/api/books")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert len(response.json()["books"]) == 0


@pytest.mark.asyncio
async def test_get_nonexistent_book(client: AsyncClient):
    """Test getting non-existent book."""
    response = await client.get("/api/books/999")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ai_providers_endpoint(client: AsyncClient):
    """Test AI providers status endpoint."""
    response = await client.get("/api/ai/providers")

    assert response.status_code == 200
    assert "providers" in response.json()
    assert "active_provider" in response.json()


@pytest.mark.asyncio
async def test_ai_provider_active_endpoint(client: AsyncClient):
    """Test get active AI provider endpoint."""
    response = await client.get("/api/ai/providers/active")

    assert response.status_code == 200
    assert "active_provider" in response.json()


@pytest.mark.asyncio
async def test_library_stats(client: AsyncClient):
    """Test library statistics endpoint."""
    response = await client.get("/api/stats")

    assert response.status_code == 200
    assert "total_books" in response.json()
    assert response.json()["total_books"] >= 0


@pytest.mark.asyncio
async def test_library_scan(client: AsyncClient, temp_library):
    """Test library scan endpoint."""
    response = await client.post("/api/library/scan")

    assert response.status_code == 200
    assert "imported" in response.json()
    assert "total" in response.json()
