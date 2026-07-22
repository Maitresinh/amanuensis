"""Compatibility adapter for the Ephemera HTTP API.

The adapter isolates the legacy service behind Amanuensis contracts. It does not
know about Grimmory paths and only writes completed files into an explicit
staging directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
import re
import tempfile
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..acquisition import (
    CatalogueQuery,
    ProviderError,
    RemoteDownload,
    RemoteState,
    RetryableProviderError,
    SearchCandidate,
    SearchPage,
)


# Compatibility names retained for callers of the first adapter release.
AdapterError = ProviderError
RetryableAdapterError = RetryableProviderError


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value if item)
    if value:
        return (str(value),)
    return ()


def _safe_filename(value: str, fallback: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip().strip(".")
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", name)
    return name or fallback


class EphemeraAdapter:
    name = "ephemera-api"

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        base = base_url.rstrip("/")
        self.base_url = base if base.endswith("/api") else f"{base}/api"
        self.timeout = timeout

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: list[tuple[str, str]] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, method=method)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                parsed = json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            error_type = RetryableAdapterError if exc.code == 429 or exc.code >= 500 else AdapterError
            raise error_type(f"Ephemera HTTP {exc.code}: {detail}") from exc
        except (TimeoutError, URLError) as exc:
            raise RetryableAdapterError(f"Ephemera is unavailable: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AdapterError("Ephemera returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise AdapterError("Ephemera returned a non-object response")
        return parsed

    def search(self, query: CatalogueQuery) -> SearchPage:
        params: list[tuple[str, str]] = [
            ("q", query.text),
            ("page", str(query.page)),
            ("sort", query.sort.value),
            ("desc", str(query.descending).lower()),
        ]
        for key, values in (
            ("content", query.content_types),
            ("ext", query.formats),
            ("lang", query.languages),
            ("src", query.sources),
        ):
            params.extend((key, value) for value in values)
        if query.author:
            params.append(("author", query.author))
        if query.title:
            params.append(("title", query.title))
        payload = self._request_json("GET", "/search", query=params)
        raw_items = payload.get("results") or payload.get("items") or payload.get("books") or []
        candidates: list[SearchCandidate] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                candidates.append(
                    SearchCandidate(
                        identifier=str(item.get("md5") or ""),
                        title=str(item.get("title") or item.get("filename") or ""),
                        authors=_as_tuple(item.get("authors")),
                        publisher=item.get("publisher"),
                        description=item.get("description"),
                        cover_url=item.get("coverUrl"),
                        filename=item.get("filename"),
                        language=item.get("language"),
                        format=item.get("format"),
                        size=str(item["size"]) if item.get("size") is not None else None,
                        year=str(item["year"]) if item.get("year") is not None else None,
                        content_type=item.get("contentType"),
                        source=item.get("source"),
                        download_status=item.get("downloadStatus"),
                        attributes={key: value for key, value in item.items() if key not in {
                            "md5", "title", "authors", "publisher", "description", "coverUrl",
                            "filename", "language", "format", "size", "year", "contentType",
                            "source", "downloadStatus",
                        }},
                    )
                )
            except ValueError:
                continue
        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
        total = _optional_int(
            pagination.get("total")
            or pagination.get("estimated_total_results")
            or payload.get("total")
        )
        per_page = _optional_int(pagination.get("per_page"))
        total_pages = _optional_int(pagination.get("totalPages") or payload.get("totalPages"))
        if total_pages is None and total is not None and per_page:
            total_pages = max(1, (total + per_page - 1) // per_page)
        return SearchPage(
            tuple(candidates),
            page=int(pagination.get("page") or payload.get("page") or query.page),
            total=total,
            total_pages=total_pages,
        )

    def queue(self, candidate: SearchCandidate) -> RemoteDownload:
        payload = self._request_json("POST", f"/download/{candidate.identifier}", payload={})
        state = payload.get("status") or "queued"
        if state == "already_downloaded":
            state = "available"
        if state == "already_in_queue":
            existing = payload.get("existing") if isinstance(payload.get("existing"), dict) else {}
            state = existing.get("status") or "queued"
            payload = {**payload, **existing}
        return self._normalise_download(candidate.identifier, {**payload, "status": state})

    def status(self, identifier: str) -> RemoteDownload:
        payload = self._request_json("GET", f"/queue/{identifier}")
        item = payload.get("download") if isinstance(payload.get("download"), dict) else payload
        return self._normalise_download(identifier, item)

    def retry(self, identifier: str) -> RemoteDownload:
        payload = self._request_json("POST", f"/download/{identifier}/retry", payload={})
        if payload.get("status") or payload.get("state"):
            return self._normalise_download(identifier, payload)
        return self.status(identifier)

    def cancel(self, identifier: str) -> RemoteDownload:
        payload = self._request_json("DELETE", f"/download/{identifier}")
        return self._normalise_download(identifier, {**payload, "status": "cancelled"})

    def retrieve(
        self,
        candidate: SearchCandidate,
        destination: Path,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        request = Request(
            f"{self.base_url}/download/{candidate.identifier}/file",
            method="GET",
            headers={"Accept": "application/octet-stream"},
        )
        try:
            with urlopen(request, timeout=max(self.timeout, 120.0)) as response:
                header_name = _content_disposition_filename(response.headers.get("Content-Disposition"))
                fallback = f"{candidate.identifier}.{(candidate.format or 'bin').lower()}"
                filename = _safe_filename(header_name or candidate.filename or candidate.title, fallback)
                if not Path(filename).suffix and candidate.format:
                    filename = f"{filename}.{candidate.format.lower()}"
                final_path = destination / filename
                if final_path.exists():
                    if _file_md5(final_path) == candidate.identifier:
                        return final_path
                    final_path = destination / f"{final_path.stem}-{candidate.identifier[:8]}{final_path.suffix}"
                return self._stream_verified(response, final_path, candidate.identifier, chunk_size)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            error_type = RetryableAdapterError if exc.code == 429 or exc.code >= 500 else AdapterError
            raise error_type(f"Ephemera file HTTP {exc.code}: {detail}") from exc
        except (TimeoutError, URLError) as exc:
            raise RetryableAdapterError(f"Ephemera file transfer failed: {exc}") from exc

    def _stream_verified(
        self, source: BinaryIO, final_path: Path, expected_md5: str, chunk_size: int
    ) -> Path:
        digest = hashlib.md5(usedforsecurity=False)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{final_path.name}.", suffix=".part",
                dir=final_path.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                while chunk := source.read(chunk_size):
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if digest.hexdigest() != expected_md5:
                raise AdapterError(
                    f"download checksum mismatch: expected {expected_md5}, got {digest.hexdigest()}"
                )
            os.replace(temporary, final_path)
            return final_path
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    @staticmethod
    def _normalise_download(identifier: str, payload: dict[str, Any]) -> RemoteDownload:
        raw_state = str(payload.get("status") or payload.get("state") or "unknown").lower()
        aliases = {"done": "available", "completed": "available", "already_downloaded": "available"}
        raw_state = aliases.get(raw_state, raw_state)
        next_retry = _timestamp(payload.get("nextRetryAt"))
        if raw_state == "queued" and next_retry is not None:
            raw_state = "delayed"
        try:
            state = RemoteState(raw_state)
        except ValueError:
            state = RemoteState.UNKNOWN
        return RemoteDownload(
            identifier=identifier,
            state=state,
            progress=float(payload.get("progress") or 0),
            error=payload.get("error"),
            next_retry_at=next_retry,
            filename=payload.get("filename"),
            attributes=dict(payload),
        )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", value, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
