"""Deterministic text extraction for text-bearing library files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
import posixpath
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .search import SourceUnit


class ExtractionStatus(StrEnum):
    INDEXABLE = "indexable"
    EMPTY = "empty"
    OCR_REQUIRED = "ocr_required"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    book_id: str
    path: Path
    format: str
    status: ExtractionStatus
    units: tuple[SourceUnit, ...] = ()
    message: str = ""


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "dl",
    "dt",
    "dd",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tr",
    "ul",
}
_IGNORED_TAGS = {"script", "style", "svg"}


class _ReadableHTMLParser(HTMLParser):
    """Create one stable plain-text representation of an HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self._in_title = False
        self._heading_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2"}:
            self._heading_depth += 1
        if tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self.ignored_depth = max(0, self.ignored_depth - 1)
            return
        if self.ignored_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in {"h1", "h2"}:
            self._heading_depth = max(0, self._heading_depth - 1)
        if tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self.parts and not self.parts[-1].endswith((" ", "\n")):
            self.parts.append(" ")
        self.parts.append(text)
        if self._in_title:
            self.title_parts.append(text)
        if self._heading_depth:
            self.heading_parts.append(text)

    def result(self) -> tuple[str, str]:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        label_parts = self.heading_parts or self.title_parts
        return text, " ".join(label_parts).strip()


def extract_text(book_id: str, path: Path | str) -> ExtractionResult:
    """Extract canonical source units without invoking OCR."""

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".epub":
        return _extract_epub(book_id, source)
    if suffix == ".pdf":
        return _extract_pdf(book_id, source)
    if suffix in {".txt", ".md"}:
        text = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        units = (SourceUnit(book_id, "text:1", 1, source.stem, text),) if text.strip() else ()
        return ExtractionResult(
            book_id,
            source,
            suffix[1:],
            ExtractionStatus.INDEXABLE if units else ExtractionStatus.EMPTY,
            units,
            "" if units else "Le fichier texte ne contient aucun texte indexable.",
        )
    return ExtractionResult(
        book_id,
        source,
        suffix.removeprefix(".") or "unknown",
        ExtractionStatus.UNSUPPORTED,
        message="Format non pris en charge par l'index de texte.",
    )


def _extract_epub(book_id: str, path: Path) -> ExtractionResult:
    try:
        with ZipFile(path) as archive:
            opf_path = _epub_opf_path(archive)
            opf_root = ElementTree.fromstring(archive.read(opf_path))
            base = posixpath.dirname(opf_path)
            manifest: dict[str, tuple[str, str]] = {}
            for element in opf_root.iter():
                if _local_name(element.tag) != "item":
                    continue
                identifier = element.attrib.get("id", "")
                href = element.attrib.get("href", "")
                if identifier and href:
                    manifest[identifier] = (href, element.attrib.get("media-type", ""))
            spine = [
                element.attrib.get("idref", "")
                for element in opf_root.iter()
                if _local_name(element.tag) == "itemref"
            ]
            members = [
                manifest[item_id]
                for item_id in spine
                if item_id in manifest and _is_html_manifest_item(manifest[item_id])
            ]
            if not members:
                members = sorted(
                    (item for item in manifest.values() if _is_html_manifest_item(item)),
                    key=lambda item: item[0],
                )
            units: list[SourceUnit] = []
            for order, (href, _media_type) in enumerate(members, start=1):
                member = posixpath.normpath(posixpath.join(base, href))
                parser = _ReadableHTMLParser()
                parser.feed(archive.read(member).decode("utf-8", errors="replace"))
                text, label = parser.result()
                if not text:
                    continue
                units.append(
                    SourceUnit(
                        book_id=book_id,
                        unit_id=f"epub:{order}",
                        order=order,
                        label=label or Path(href).stem,
                        text=text,
                    )
                )
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError) as exc:
        return ExtractionResult(
            book_id,
            path,
            "epub",
            ExtractionStatus.EMPTY,
            message=f"EPUB illisible: {exc}",
        )
    return ExtractionResult(
        book_id,
        path,
        "epub",
        ExtractionStatus.INDEXABLE if units else ExtractionStatus.EMPTY,
        tuple(units),
        "" if units else "L'EPUB ne contient aucun chapitre textuel indexable.",
    )


def _epub_opf_path(archive: ZipFile) -> str:
    try:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        for element in container.iter():
            if _local_name(element.tag) == "rootfile" and element.attrib.get("full-path"):
                return element.attrib["full-path"]
    except (KeyError, ElementTree.ParseError):
        pass
    candidates = sorted(name for name in archive.namelist() if name.lower().endswith(".opf"))
    if not candidates:
        raise KeyError("aucun paquet OPF")
    return candidates[0]


def _is_html_manifest_item(item: tuple[str, str]) -> bool:
    href, media_type = item
    return media_type in {"application/xhtml+xml", "text/html"} or href.lower().endswith(
        (".xhtml", ".html", ".htm")
    )


def _extract_pdf(book_id: str, path: Path) -> ExtractionResult:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        units: list[SourceUnit] = []
        for order, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text(extraction_mode="layout") or ""
            except (KeyError, TypeError):
                try:
                    text = page.extract_text() or ""
                except KeyError:
                    text = ""
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if not text.strip():
                continue
            units.append(SourceUnit(book_id, f"pdf:{order}", order, f"Page {order}", text))
    except (ImportError, OSError, ValueError) as exc:
        return ExtractionResult(
            book_id,
            path,
            "pdf",
            ExtractionStatus.EMPTY,
            message=f"PDF illisible: {exc}",
        )
    if not units:
        return ExtractionResult(
            book_id,
            path,
            "pdf",
            ExtractionStatus.OCR_REQUIRED,
            message="Aucune couche texte detectee; un OCR explicite serait necessaire.",
        )
    return ExtractionResult(
        book_id,
        path,
        "pdf",
        ExtractionStatus.INDEXABLE,
        tuple(units),
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
