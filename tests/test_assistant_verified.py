"""Local, source-backed assistant answers without contacting the external model."""

import unittest
from unittest.mock import patch

from assistant_engine import ChatRequest, chat


class VerifiedAssistantTests(unittest.TestCase):
    def test_common_questions_do_not_call_external_model(self):
        user = {"id": 1, "role": "ceo", "full_name": "Test"}
        questions = {
            "سلام": "verified_greeting",
            "فروش این ماه چقدر بود؟": "verified_sales",
            "بدهکارترین مشتری‌ها کی‌اند؟": "verified_debt",
            "وضعیت انبار چطور است؟": "verified_inventory",
            "تسک‌های عقب‌افتاده چند تا است؟": "verified_tasks",
        }
        with patch("assistant_engine.call_gpt") as external, patch("assistant_engine.save_turn"):
            for question, mode in questions.items():
                with self.subTest(question=question):
                    result = chat(ChatRequest(message=question), user=user)
                    self.assertEqual(result["mode"], mode)
                    self.assertTrue(result["answer"])
            external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
