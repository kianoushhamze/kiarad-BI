"""Unit tests for marketing_intel pure helpers (demand pct + question dedup).
No DB or network access is required.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketing_intel import (  # noqa: E402
    classify_topic,
    compute_kerman_sales_pct,
    demand_tier,
    dedup_questions,
    extract_questions,
    normalize_question,
    web_signal_score,
)


class NormalizeAndDedupTests(unittest.TestCase):
    def test_normalize_strips_punctuation_and_whitespace(self):
        self.assertEqual(
            normalize_question("بهترین   شامپو ضد شوره؟"),
            normalize_question("بهترین شامپو ضد شوره?!"),
        )
        self.assertEqual(normalize_question("  چگونه  ریزش مو را درمان کنم؟ "), "چگونه ریزش مو را درمان کنم")

    def test_dedup_removes_existing_duplicates(self):
        existing = ["مشکل پوست صورت چیست؟"]
        candidates = ["مشکل پوست صورت چیست", "ریزش مو چگونه درمان میشود؟", "ریزش  مو چگونه درمان میشود؟"]
        out = dedup_questions(candidates, existing)
        self.assertEqual(out, ["ریزش مو چگونه درمان میشود؟"])

    def test_dedup_removes_intra_batch_duplicates_and_blank(self):
        out = dedup_questions(["سوال تکراری؟", "سوال تکراری!", "", "سوال تازه"], [])
        self.assertEqual(out, ["سوال تکراری؟", "سوال تازه"])

    def test_dedup_is_case_and_punctuation_insensitive(self):
        out = dedup_questions(["BEST shampoo?"], ["best   shampoo!"])
        self.assertEqual(out, [])


class ComputeKermanSalesPctTests(unittest.TestCase):
    def test_basic_share_rounds_to_two_decimals(self):
        pcts, total = compute_kerman_sales_pct({"A": 30.0, "B": 70.0})
        self.assertAlmostEqual(pcts["A"], 30.0, places=2)
        self.assertAlmostEqual(pcts["B"], 70.0, places=2)
        self.assertEqual(total, 100.0)

    def test_no_data_returns_empty_not_fake_zeroes(self):
        pcts, total = compute_kerman_sales_pct({})
        self.assertEqual(pcts, {})
        self.assertEqual(total, 0.0)

    def test_single_product_is_100_percent(self):
        pcts, _ = compute_kerman_sales_pct({"X": 5})
        self.assertAlmostEqual(pcts["X"], 100.0, places=2)

    def test_all_zero_quantities_yield_no_fake_percentages(self):
        pcts, total = compute_kerman_sales_pct({"A": 0})
        self.assertEqual(pcts, {})
        self.assertEqual(total, 0.0)


class DemandTierTests(unittest.TestCase):
    def test_high_sales_share_is_bigger_opportunity(self):
        self.assertEqual(demand_tier(5.0, 0), "فرصت فروش بیشتر")

    def test_low_share_low_signal_is_smaller(self):
        self.assertEqual(demand_tier(0.1, 0), "فرصت فروش کمتر")

    def test_mid_share_with_strong_web_signal_upgrades(self):
        self.assertEqual(demand_tier(0.6, 4), "فرصت فروش بیشتر")

    def test_missing_values_are_treated_as_zero(self):
        self.assertEqual(demand_tier(None, None), "فرصت فروش کمتر")


class QuestionExtractionTests(unittest.TestCase):
    def test_extracts_question_like_titles(self):
        titles = ["چگونه ریزش مو را درمان کنیم؟", "خرید شامپو کیاراد", "بهترین شامپو ضد شوره چیست"]
        out = extract_questions(titles)
        self.assertIn("چگونه ریزش مو را درمان کنیم؟", out)
        self.assertIn("بهترین شامپو ضد شوره چیست", out)
        self.assertNotIn("خرید شامپو کیاراد", out)

    def test_drops_own_brand_and_short_noise(self):
        out = extract_questions(["کیاراد", "کیاراد چیست؟", "ab"])
        self.assertEqual(out, [])

    def test_topic_classification(self):
        self.assertEqual(classify_topic("بهترین شامپو ضد شوره"), "مو")
        self.assertEqual(classify_topic("درمان جوش صورت"), "پوست")
        self.assertEqual(classify_topic("سلام"), "عمومی")

    def test_web_signal_is_bounded_0_10(self):
        self.assertEqual(web_signal_score(50), 10)
        self.assertEqual(web_signal_score(0), 0)
        self.assertEqual(web_signal_score(-3), 0)


if __name__ == "__main__":
    unittest.main()
