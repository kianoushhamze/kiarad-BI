"""Chat attachment validation tests; no messages or files are written."""
import unittest

from api import _CHAT_ALLOWED_TYPES, _CHAT_MAX_FILE_BYTES, _valid_chat_file


class ChatAttachmentValidationTests(unittest.TestCase):
    def test_allowed_types_match_the_user_interface(self):
        self.assertEqual(set(_CHAT_ALLOWED_TYPES), {
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".docx", ".xlsx", ".csv", ".txt"
        })
        self.assertEqual(_CHAT_MAX_FILE_BYTES, 10 * 1024 * 1024)

    def test_magic_bytes_are_checked(self):
        self.assertTrue(_valid_chat_file(".pdf", b"%PDF-1.7\nbody"))
        self.assertTrue(_valid_chat_file(".png", b"\x89PNG\r\n\x1a\nbody"))
        self.assertFalse(_valid_chat_file(".pdf", b"plain text"))
        self.assertFalse(_valid_chat_file(".png", b"%PDF-1.7"))

    def test_binary_content_is_rejected_as_text(self):
        self.assertFalse(_valid_chat_file(".txt", b"hello\x00world"))


if __name__ == "__main__":
    unittest.main()
