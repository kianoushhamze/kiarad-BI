"""Catalog file validation tests; no files or database rows are created."""
import unittest

from fastapi import HTTPException
from crud_api import CATALOG_MAX_FILE_BYTES, UPLOAD_ROOT, _catalog_file_path, _validate_catalog_content


class CatalogUploadValidationTests(unittest.TestCase):
    def test_valid_pdf_is_accepted(self):
        ext, mime, name = _validate_catalog_content("pdf", "catalog.pdf", b"%PDF-1.7\nbody")
        self.assertEqual((ext, mime, name), (".pdf", "application/pdf", "catalog.pdf"))

    def test_extension_and_content_mismatch_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            _validate_catalog_content("image", "fake.png", b"not an image")
        self.assertEqual(error.exception.status_code, 400)

    def test_wrong_media_type_for_extension_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            _validate_catalog_content("pdf", "photo.jpg", b"\xff\xd8\xffdata")
        self.assertEqual(error.exception.status_code, 415)

    def test_oversized_file_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            _validate_catalog_content("pdf", "large.pdf", b"%PDF-" + b"x" * CATALOG_MAX_FILE_BYTES)
        self.assertEqual(error.exception.status_code, 400)

    def test_path_segments_are_removed_from_original_name(self):
        _, _, name = _validate_catalog_content("pdf", "../../private/catalog.pdf", b"%PDF-1.7")
        self.assertEqual(name, "catalog.pdf")

    def test_public_file_url_resolves_inside_upload_root(self):
        path = _catalog_file_path("/api/files/catalog/file.pdf")
        self.assertEqual(path, (UPLOAD_ROOT / "catalog" / "file.pdf").resolve())

    def test_public_file_url_cannot_escape_upload_root(self):
        with self.assertRaises(ValueError):
            _catalog_file_path("/api/files/../../private/file.pdf")


if __name__ == "__main__":
    unittest.main()
