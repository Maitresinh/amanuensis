from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZipFile

from amanuensis.extraction import ExtractionStatus, extract_text
from amanuensis.indexing import segment_units
from amanuensis.search_store import SQLiteSearchStore


class TextExtractionTests(TestCase):
    def test_epub_follows_spine_and_produces_stable_source_text(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "fixture.epub")
            _write_epub(path)

            result = extract_text("book-epub", path)

        self.assertEqual(ExtractionStatus.INDEXABLE, result.status)
        self.assertEqual(["epub:1", "epub:2"], [unit.unit_id for unit in result.units])
        self.assertEqual("Chapitre Deux", result.units[0].label)
        self.assertEqual(
            "Chapitre Deux\n\nLes villes flottantes utilisent l'energie solaire.",
            result.units[0].text,
        )
        self.assertIn("Chapitre Un", result.units[1].text)

    def test_pdf_text_layer_is_extracted_by_page(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "text.pdf")
            _write_pdf(path, "Bonjour depuis la couche texte")

            result = extract_text("book-pdf", path)

        self.assertEqual(ExtractionStatus.INDEXABLE, result.status)
        self.assertEqual(1, len(result.units))
        self.assertEqual("Page 1", result.units[0].label)
        self.assertIn("Bonjour depuis la couche texte", result.units[0].text)

    def test_image_only_pdf_is_not_sent_to_ocr_implicitly(self):
        from pypdf import PdfWriter

        with TemporaryDirectory() as directory:
            path = Path(directory, "image-only.pdf")
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with path.open("wb") as output:
                writer.write(output)

            result = extract_text("scan", path)

        self.assertEqual(ExtractionStatus.OCR_REQUIRED, result.status)
        self.assertEqual((), result.units)


class PassageStorageTests(TestCase):
    def test_segments_are_exact_source_slices_and_survive_store_reopen(self):
        text = " ".join(f"mot{i}" for i in range(400))
        with TemporaryDirectory() as directory:
            source = Path(directory, "source.txt")
            source.write_text(text, encoding="utf-8")
            result = extract_text("book-1", source)
            documents = segment_units(
                result.units,
                corpus_ids=frozenset({"corpus-a"}),
                target_chars=300,
                overlap_chars=40,
            )
            unit = result.units[0]
            for document in documents:
                passage = document.passage
                self.assertEqual(unit.text[passage.start : passage.end], document.text)

            database = Path(directory, "search.db")
            SQLiteSearchStore(database).replace_book(
                result,
                documents,
                title="Livre test",
                corpus_ids=frozenset({"corpus-a"}),
            )
            reopened = SQLiteSearchStore(database)

            stored_units = reopened.units_for_books(frozenset({"book-1"}))
            scope = reopened.resolve_scope(corpus_id="corpus-a")

        self.assertEqual(text, stored_units[0].text)
        self.assertEqual(frozenset({"book-1"}), scope.book_ids)
        self.assertEqual("corpus-a", scope.corpus_id)


def _write_epub(path: Path) -> None:
    container = """<?xml version="1.0"?>
    <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
    </container>"""
    package = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
      <manifest>
        <item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>
        <item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine><itemref idref="two"/><itemref idref="one"/></spine>
    </package>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr(
            "OEBPS/one.xhtml",
            "<html><body><h1>Chapitre Un</h1><p>La foret reste silencieuse.</p></body></html>",
        )
        archive.writestr(
            "OEBPS/two.xhtml",
            "<html><body><h1>Chapitre Deux</h1><p>Les villes flottantes utilisent l'energie solaire.</p></body></html>",
        )


def _write_pdf(path: Path, text: str) -> None:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)
