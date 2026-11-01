"""OPDS catalog browsing and download service (spec 015).

Fetches OPDS (Atom) feeds on behalf of the client — so browser CORS rules and
catalog credentials never reach the browser — normalizes navigation and
acquisition entries, and downloads acquisition items into the library where
they flow through the normal scan/import pipeline.

Security posture (spec 015 §Security): the server fetches admin-supplied
URLs; eLM is a self-hosted single-admin app and catalogs legitimately live on
the LAN, so private-range hosts are not blanket-blocked. Mitigations are the
http/https scheme whitelist, a response size cap, a request timeout, and
credentials attached only to their catalog's requests.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.exceptions import OpdsCatalogError, ResourceNotFoundError, ValidationError
from app.logging_config import get_logger
from app.models import Book, OpdsCatalog
from app.scanner import LibraryScanner
from app.schemas import (
    OpdsCatalogCreate,
    OpdsCatalogResponse,
    OpdsCatalogUpdate,
    OpdsDownloadLink,
    OpdsDownloadRequest,
    OpdsEntry,
    OpdsFeed,
)
from app.security import decrypt_value, encrypt_value
from app.services.library_service import LibraryService

logger = get_logger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Fetch limits (spec 015 AC-8/AC-9).
FEED_TIMEOUT_SECONDS = 30.0
FEED_MAX_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120.0
DOWNLOAD_MAX_BYTES = 200 * 1024 * 1024

_ALLOWED_SCHEMES = ("http", "https")


async def fetch_url(
    url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    max_bytes: int = FEED_MAX_BYTES,
    timeout: float = FEED_TIMEOUT_SECONDS,
) -> bytes:
    """Fetch a URL with the size cap and timeout required by spec 015.

    Args:
        url: Absolute http(s) URL.
        username: Optional basic-auth username.
        password: Optional basic-auth password.
        max_bytes: Maximum accepted response body size.
        timeout: Request timeout in seconds.

    Returns:
        Raw response body bytes.

    Raises:
        ValidationError: If the URL scheme is not http/https.
        OpdsCatalogError: On connection failure, timeout, bad status, or an
            oversized body.
    """
    _validate_url_scheme(url)
    auth = (username, password) if username and password else None
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "eLibrary-Manager/1.0 (OPDS)"},
        ) as client:
            async with client.stream("GET", url, auth=auth) as response:
                if response.status_code != 200:
                    raise OpdsCatalogError(
                        f"Catalog returned HTTP {response.status_code}",
                        {"url": url},
                    )
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise OpdsCatalogError(
                            "Catalog response exceeds size limit",
                            {"url": url, "max_bytes": max_bytes},
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
    except OpdsCatalogError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        raise OpdsCatalogError(
            "Failed to reach catalog", {"url": url, "error": str(exc)}
        ) from exc


def _validate_url_scheme(url: str) -> None:
    """Reject URLs whose scheme is not http/https (spec 015 AC-4/AC-11).

    Args:
        url: Candidate URL.

    Raises:
        ValidationError: If the scheme is not http or https.
    """
    scheme = urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValidationError(
            "Only http(s) catalog URLs are supported", {"url": url}
        )


def _local_name(tag: str) -> str:
    """Return an XML tag's local name (namespace-stripped)."""
    return tag.rsplit("}", 1)[-1]


def _child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    """Find the first direct child with the given local name."""
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _link_is_thumbnail(rel: str | None) -> bool:
    """Whether a link rel marks an OPDS thumbnail image."""
    if not rel:
        return False
    return rel in (
        "http://opds-spec.org/image/thumbnail",
        "http://opds-spec.org/thumbnail",
    ) or rel.endswith("/image/thumbnail")


class OpdsService:
    """Browse and download from registered OPDS catalogs."""

    def __init__(self, session: AsyncSession) -> None:
        """Create the service.

        Args:
            session: Active database session.
        """
        self.session = session
        self.scanner = LibraryScanner()

    # ------------------------------------------------------------------ #
    # Catalog CRUD helpers
    # ------------------------------------------------------------------ #

    async def _get_catalog(self, catalog_id: int) -> OpdsCatalog:
        """Load a catalog or raise 404 (spec 015 AC-3/AC-10).

        Args:
            catalog_id: Catalog primary key.

        Returns:
            The OpdsCatalog row.

        Raises:
            ResourceNotFoundError: If no catalog with that id exists.
        """
        catalog = await self.session.get(OpdsCatalog, catalog_id)
        if catalog is None:
            raise ResourceNotFoundError(f"OPDS catalog {catalog_id} not found")
        return catalog

    @staticmethod
    def _credentials(catalog: OpdsCatalog) -> tuple[str | None, str | None]:
        """Decrypt and return the catalog's basic-auth credentials."""
        if not (catalog.username and catalog.password_encrypted):
            return None, None
        try:
            return catalog.username, decrypt_value(catalog.password_encrypted)
        except (ValueError, OSError) as exc:
            raise OpdsCatalogError(
                "Stored catalog credentials could not be decrypted",
                {"catalog_id": catalog.id},
            ) from exc

    @staticmethod
    def to_response(catalog: OpdsCatalog) -> OpdsCatalogResponse:
        """Map a row to its public schema (never exposing credentials)."""
        return OpdsCatalogResponse(
            id=catalog.id,
            name=catalog.name,
            url=catalog.url,
            username=catalog.username,
            has_password=bool(catalog.password_encrypted),
            added_date=catalog.added_date,
            last_browsed=catalog.last_browsed,
        )

    async def list_catalogs(self) -> list[OpdsCatalogResponse]:
        """List all registered catalogs.

        Returns:
            Public catalog schemas ordered by name.
        """
        rows = (
            (
                await self.session.execute(
                    select(OpdsCatalog).order_by(OpdsCatalog.name)
                )
            )
            .scalars()
            .all()
        )
        return [self.to_response(row) for row in rows]

    async def create_catalog(self, data: OpdsCatalogCreate) -> OpdsCatalogResponse:
        """Register a new catalog.

        Args:
            data: Validated create payload.

        Returns:
            The created catalog's public schema.
        """
        _validate_url_scheme(data.url)
        row = OpdsCatalog(
            name=data.name,
            url=data.url,
            username=data.username,
            password_encrypted=(
                encrypt_value(data.password) if data.password else None
            ),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self.to_response(row)

    async def update_catalog(
        self, catalog_id: int, data: OpdsCatalogUpdate
    ) -> OpdsCatalogResponse:
        """Update an existing catalog.

        Args:
            catalog_id: Catalog primary key.
            data: Validated update payload (all fields optional).

        Returns:
            The updated catalog's public schema.

        Raises:
            ResourceNotFoundError: If the catalog does not exist.
        """
        row = await self._get_catalog(catalog_id)
        if data.name is not None:
            row.name = data.name
        if data.url is not None:
            _validate_url_scheme(data.url)
            row.url = data.url
        if data.username is not None:
            row.username = data.username
        if data.password is not None:
            row.password_encrypted = encrypt_value(data.password)
        await self.session.commit()
        await self.session.refresh(row)
        return self.to_response(row)

    async def delete_catalog(self, catalog_id: int) -> None:
        """Delete a catalog.

        Args:
            catalog_id: Catalog primary key.

        Raises:
            ResourceNotFoundError: If the catalog does not exist.
        """
        row = await self._get_catalog(catalog_id)
        await self.session.delete(row)
        await self.session.commit()

    # ------------------------------------------------------------------ #
    # Browse (feed proxy + normalization)
    # ------------------------------------------------------------------ #

    async def browse(self, catalog_id: int, url: str | None = None) -> OpdsFeed:
        """Fetch and normalize an OPDS feed (spec 015 AC-5..AC-11).

        Args:
            catalog_id: Catalog primary key.
            url: Feed URL to fetch; defaults to the catalog root.

        Returns:
            The normalized feed.

        Raises:
            ResourceNotFoundError: Unknown catalog.
            ValidationError: Non-http(s) target URL.
            OpdsCatalogError: Fetch failure, oversized body, or malformed XML.
        """
        catalog = await self._get_catalog(catalog_id)
        target = url or catalog.url
        _validate_url_scheme(target)
        username, password = self._credentials(catalog)
        body = await fetch_url(
            target, username=username, password=password, max_bytes=FEED_MAX_BYTES
        )
        feed = self._parse_feed(body, target)
        catalog.last_browsed = datetime.now(UTC)
        await self.session.commit()
        return feed

    @staticmethod
    def _parse_feed(body: bytes, url: str) -> OpdsFeed:
        """Parse an Atom/OPDS feed body into the normalized schema.

        Args:
            body: Raw XML bytes.
            url: The URL the feed was fetched from.

        Returns:
            The normalized feed.

        Raises:
            OpdsCatalogError: If the body is not well-formed XML.
        """
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as exc:
            raise OpdsCatalogError(
                "Catalog response is not a valid feed", {"url": url}
            ) from exc

        feed_title_el = _child(root, "title")
        entries = []
        for entry_el in root:
            if _local_name(entry_el.tag) != "entry":
                continue
            entries.append(OpdsService._parse_entry(entry_el))
        return OpdsFeed(
            title=feed_title_el.text if feed_title_el is not None else None,
            url=url,
            entries=entries,
        )

    @staticmethod
    def _parse_entry(entry_el: ElementTree.Element) -> OpdsEntry:
        """Normalize a single ``<entry>`` element.

        Args:
            entry_el: The entry element.

        Returns:
            The normalized entry with navigation/acquisition classification.
        """
        title_el = _child(entry_el, "title")
        summary_el = _child(entry_el, "summary") or _child(entry_el, "content")
        id_el = _child(entry_el, "id")

        authors: list[str] = []
        download: OpdsDownloadLink | None = None
        is_navigation = False
        thumbnail_url: str | None = None

        for link_el in entry_el:
            if _local_name(link_el.tag) != "link":
                continue
            rel = link_el.get("rel") or ""
            href = link_el.get("href") or ""
            link_type = link_el.get("type") or ""
            if not href:
                continue
            if "acquisition" in rel:
                if download is None or (
                    download.media_type is None and link_type
                ):
                    download = OpdsDownloadLink(url=href, media_type=link_type or None)
            elif "thumbnail" in rel or _link_is_thumbnail(rel):
                thumbnail_url = href
            elif (
                "subsection" in rel
                or "opds-catalog" in link_type
                or "catalog" in rel
            ):
                is_navigation = True

        for author_el in entry_el:
            if _local_name(author_el.tag) != "author":
                continue
            name_el = _child(author_el, "name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text)

        title = (title_el.text if title_el is not None else None) or "Untitled"
        summary = None
        if summary_el is not None:
            summary = "".join(summary_el.itertext()) or None
        return OpdsEntry(
            id=id_el.text if id_el is not None else None,
            title=title,
            summary=summary,
            authors=authors,
            thumbnail_url=thumbnail_url,
            is_navigation=is_navigation,
            download=download,
        )

    # ------------------------------------------------------------------ #
    # Download (acquisition → library import)
    # ------------------------------------------------------------------ #

    async def download(self, catalog_id: int, request: OpdsDownloadRequest) -> Book:
        """Download an acquisition item and import it as a Book (AC-12..AC-14).

        The file is written to a temp file first and renamed only after the
        full body arrives, so a failed download never leaves a partial file in
        the library.

        Args:
            catalog_id: Catalog primary key (credentials source).
            request: Validated download request (url + filename).

        Returns:
            The imported (or already-existing) Book.

        Raises:
            ResourceNotFoundError: Unknown catalog.
            ValidationError: Unsupported filename extension or bad scheme.
            OpdsCatalogError: Fetch failure or bad status.
            LibraryScannerError: If import fails after a complete download.
        """
        catalog = await self._get_catalog(catalog_id)
        _validate_url_scheme(request.url)

        ext = os.path.splitext(request.filename)[1].lower()
        if ext not in self.scanner.SUPPORTED_FORMATS:
            raise ValidationError(
                "Unsupported book format", {"filename": request.filename}
            )

        library_path = get_config().library_path
        os.makedirs(library_path, exist_ok=True)
        # Sanitize to a bare filename — never let the catalog name a path.
        safe_name = os.path.basename(request.filename.replace("\\", "/"))
        final_path = os.path.join(library_path, safe_name)

        username, password = self._credentials(catalog)
        body = await fetch_url(
            request.url,
            username=username,
            password=password,
            max_bytes=DOWNLOAD_MAX_BYTES,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )

        fd, tmp_path = tempfile.mkstemp(dir=library_path, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
            os.replace(tmp_path, final_path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        service = LibraryService(self.session)
        book = await service.import_book(final_path)
        logger.info("OPDS download imported book %s", book.title)
        return book
