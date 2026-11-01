"""OPDS catalog routes (spec 015).

All routes live under ``/api/opds`` and are session-gated by AuthMiddleware;
mutating methods additionally pass the CSRF origin check. The browse endpoint
proxies catalog fetches so browser CORS rules and catalog credentials never
reach the client.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logging_config import get_logger
from app.schemas import (
    OpdsCatalogCreate,
    OpdsCatalogResponse,
    OpdsCatalogUpdate,
    OpdsDownloadRequest,
    OpdsFeed,
)
from app.services.opds_service import OpdsService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/opds", tags=["opds"])


@router.get("/catalogs", response_model=list[OpdsCatalogResponse])
async def list_catalogs(db: AsyncSession = Depends(get_db)) -> list[OpdsCatalogResponse]:
    """List registered OPDS catalogs (credentials never included)."""
    service = OpdsService(db)
    return await service.list_catalogs()


@router.post("/catalogs", response_model=OpdsCatalogResponse, status_code=201)
async def create_catalog(
    payload: OpdsCatalogCreate, db: AsyncSession = Depends(get_db)
) -> OpdsCatalogResponse:
    """Register a new OPDS catalog."""
    service = OpdsService(db)
    return await service.create_catalog(payload)


@router.put("/catalogs/{catalog_id}", response_model=OpdsCatalogResponse)
async def update_catalog(
    catalog_id: int,
    payload: OpdsCatalogUpdate,
    db: AsyncSession = Depends(get_db),
) -> OpdsCatalogResponse:
    """Update an existing OPDS catalog."""
    service = OpdsService(db)
    return await service.update_catalog(catalog_id, payload)


@router.delete("/catalogs/{catalog_id}", status_code=204)
async def delete_catalog(
    catalog_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete an OPDS catalog."""
    service = OpdsService(db)
    await service.delete_catalog(catalog_id)


@router.get("/catalogs/{catalog_id}/browse", response_model=OpdsFeed)
async def browse_catalog(
    catalog_id: int,
    url: str | None = Query(None, max_length=1000, description="Feed URL override"),
    db: AsyncSession = Depends(get_db),
) -> OpdsFeed:
    """Fetch and normalize an OPDS feed through the backend proxy."""
    service = OpdsService(db)
    return await service.browse(catalog_id, url)


@router.post("/catalogs/{catalog_id}/download")
async def download_entry(
    catalog_id: int,
    payload: OpdsDownloadRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | str]:
    """Download an acquisition entry into the library and import it.

    Domain failures map through app-level exception handlers:
    ``ResourceNotFoundError`` → 404, ``ValidationError`` → 400,
    ``OpdsCatalogError`` → 502.
    """
    service = OpdsService(db)
    book = await service.download(catalog_id, payload)
    return {"book_id": book.id, "title": book.title}
