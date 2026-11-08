"""Pure payroll examples: explicit policy, exact arithmetic, no database."""

import json
from decimal import Decimal
import unittest

from payroll_engine import PayrollValidationError, calculate_payroll, normalize_rules


def target(**changes):
    value = {"target_type": "product", "item_identifier": "7", "item_title": "کالای آزمون",
             "target_amount": 0, "target_quantity": 0, "commission_percent": 10,
             "target_gate": "all", "commission_basis": "whole"}
    value.update(changes)
    return value


def fact(key="sale-1", kind="sale", amount=1000, quantity=10, product_id=7, brand="برند آزمون"):
    return {"event_key": key, "kind": kind, "amount": amount, "quantity": quantity,
            "product_id": product_id, "brand": brand}


class PayrollEngineValidationTests(unittest.TestCase):
    def test_normalization_is_json_safe_and_preserves_explicit_zero(self):
        rules = normalize_rules({"min_monthly_hours": 0, "hourly_rate": Decimal("0.10"),
                                 "overtime_multiplier": 0, "targets": [target()]})
        self.assertEqual(rules["min_monthly_hours"], 0)
        self.assertEqual(rules["overtime_multiplier"], 0)
        self.assertEqual(rules["targets"][0]["item_identifier"], "7")
        json.dumps(rules, allow_nan=False)

    def test_invalid_numbers_are_rejected(self):
        for value in [float("nan"), float("inf"), "-Infinity", "NaN", -1, True, None, {}, "پنج"]:
            with self.subTest(value=repr(value)), self.assertRaises(PayrollValidationError):
                normalize_rules({"hourly_rate": value})

    def test_out_of_range_rates_and_hours_are_rejected(self):
        for changes in [{"settlement_commission_percent": 101}, {"min_monthly_hours": 745},
                        {"overtime_multiplier": -1}, {"hourly_rate": "1e999"},
                        {"targets": [target(commission_percent=101)]}]:
            with self.subTest(changes=changes), self.assertRaises(PayrollValidationError):
                normalize_rules(changes)

    def test_fractional_target_count_and_invalid_policy_are_rejected(self):
        for changes in [{"targets": [target(target_quantity=1.5)]},
                        {"targets": [target(target_type="anything")]},
                        {"targets": [target(target_type=[])]},
                        {"targets": [target(target_gate="either")]},
                        {"commission_overlap": "random"}, {"targets": {}}]:
            with self.subTest(changes=changes), self.assertRaises(PayrollValidationError):
                normalize_rules(changes)

    def test_invalid_workdays_and_facts_are_rejected(self):
        for hours, days, facts in [(-1, 0, []), (0, 1.5, []), (0, 32, []),
                                   (0, 0, {}), (0, 0, [fact(key="")]),
                                   (0, 0, [fact(kind="unknown")]),
                                   (0, 0, [fact(kind=[])]),
                                   (0, 0, [fact(amount=-1)]),
                                   (0, 0, [fact(quantity=-1)])]:
            with self.subTest(hours=hours, days=days, facts=facts), self.assertRaises(PayrollValidationError):
                calculate_payroll({}, hours, days, facts)


class PayrollEngineSalaryTests(unittest.TestCase):
    def test_shortfall_is_indicator_without_penalty_or_assumed_minimum(self):
        result = calculate_payroll({"hourly_rate": 100, "min_monthly_hours": 176}, 160, 0)
        self.assertEqual(result["base_pay"], 16000)
        self.assertEqual(result["shortfall_hours"], 16)
        self.assertEqual(result["provisional_total"], 16000)
        self.assertEqual(result["blockers"], [])

    def test_no_threshold_means_regular_hours_without_assumed_overtime(self):
        result = calculate_payroll({"hourly_rate": 100, "min_monthly_hours": 0}, 200, 0)
        self.assertEqual(result["regular_hours"], 200)
        self.assertEqual(result["overtime_hours"], 0)
        self.assertEqual(result["base_pay"], 20000)
        self.assertTrue(result["can_approve"])

    def test_overtime_has_explicit_multiplier_and_no_double_count(self):
        result = calculate_payroll({"hourly_rate": 100, "min_monthly_hours": 176,
                                    "overtime_multiplier": 1.4}, 180, 0)
        self.assertEqual(result["regular_hours"], 176)
        self.assertEqual(result["overtime_hours"], 4)
        self.assertEqual(result["base_pay"], 17600)
        self.assertEqual(result["overtime_pay"], 560)
        self.assertEqual(result["provisional_total"], 18160)

    def test_overtime_without_approved_policy_is_blocked(self):
        result = calculate_payroll({"hourly_rate": 100, "min_monthly_hours": 176}, 180, 0)
        self.assertIn("overtime_policy_missing", {v["code"] for v in result["blockers"]})
        self.assertFalse(result["can_approve"])
        self.assertEqual(result["overtime_pay"], 0)

    def test_visit_allowance_and_component_sums_round_half_up(self):
        result = calculate_payroll({"hourly_rate": "0.005", "daily_mission_allowance": "0.005"}, 1, 1)
        self.assertEqual(result["base_pay"], 0.01)
        self.assertEqual(result["verified_visit_allowance"], 0.01)
        self.assertEqual(result["provisional_total"], 0.02)

    def test_decimal_inputs_do_not_have_binary_float_rounding(self):
        result = calculate_payroll({"hourly_rate": "2.675"}, "1", 0)
        self.assertEqual(result["provisional_total"], 2.68)
        result = calculate_payroll({"hourly_rate": "0.1"}, "0.2", 0)
        self.assertEqual(result["provisional_total"], 0.02)

    def test_natural_language_or_code_is_never_executed_as_formula(self):
        for value in ["100 * hours", "__import__('os').system('anything')", "پنج درصد فروش"]:
            with self.subTest(value=value), self.assertRaises(PayrollValidationError):
                normalize_rules({"hourly_rate": value})


class PayrollEngineCommissionTests(unittest.TestCase):
    def calculate(self, targets=None, facts=None, **changes):
        rules = {"targets": [target()] if targets is None else targets, "sales_scope": "personal", **changes}
        return calculate_payroll(rules, 0, 0, [fact()] if facts is None else facts,
                                 {"sales": True, "collections": True, "mileage": True})

    def test_sale_and_return_sign_is_applied_exactly_once(self):
        for return_amount, return_quantity in [(200, 2), (-200, -2)]:
            with self.subTest(return_amount=return_amount):
                result = self.calculate(facts=[fact(), fact("return-1", "return", return_amount, return_quantity)])
                self.assertEqual(result["sales_commission"], 80)
                self.assertEqual(result["blockers"], [])

    def test_zero_commission_needs_no_source(self):
        result = calculate_payroll({"targets": [target(commission_percent=0)]}, 0, 0)
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["sales_commission"], 0)

    def test_missing_sources_block_active_variable_fees(self):
        result = calculate_payroll({"targets": [target()], "sales_scope": "personal", "settlement_commission_percent": 1,
                                    "per_km_rate": 1}, 0, 0)
        self.assertEqual({v["code"] for v in result["blockers"]},
                         {"sales_source_incomplete", "collections_source_incomplete", "mileage_source_incomplete"})
        self.assertFalse(result["can_approve"])

    def test_empty_complete_source_is_valid_zero(self):
        result = self.calculate(facts=[])
        self.assertEqual(result["sales_commission"], 0)
        self.assertTrue(result["can_approve"])

    def test_truthy_non_boolean_completeness_is_not_approval(self):
        result = calculate_payroll({"targets": [target()]}, 0, 0, [], {"sales": "true"})
        self.assertFalse(result["can_approve"])

    def test_duplicate_event_blocks_and_does_not_pay_twice(self):
        result = self.calculate(facts=[fact(), fact()])
        self.assertEqual(result["source_event_count"], 1)
        self.assertEqual(result["sales_commission"], 100)
        self.assertEqual(result["blockers"][0]["code"], "duplicate_event")

    def test_missing_gate_and_basis_block_instead_of_guessing(self):
        result = self.calculate(targets=[target(target_gate=None, commission_basis=None)])
        self.assertEqual(result["sales_commission"], 0)
        self.assertEqual(result["blockers"][0]["code"], "target_policy_missing")

    def test_missing_fixed_identifier_blocks(self):
        result = self.calculate(targets=[target(item_identifier="")])
        self.assertEqual(result["blockers"][0]["code"], "target_identifier_missing")

    def test_all_and_any_target_gates_are_explicit(self):
        for gate, expected in [("all", 0), ("any", 100)]:
            with self.subTest(gate=gate):
                result = self.calculate(targets=[target(target_amount=500, target_quantity=20, target_gate=gate)])
                self.assertEqual(result["sales_commission"], expected)

    def test_equal_threshold_is_reached(self):
        result = self.calculate(targets=[target(target_amount=1000, target_quantity=10)])
        self.assertTrue(result["commission_details"][0]["target_reached"])
        self.assertEqual(result["sales_commission"], 100)

    def test_excess_basis_only_pays_above_monetary_target(self):
        result = self.calculate(targets=[target(target_amount=600, commission_basis="excess")])
        self.assertEqual(result["sales_commission"], 40)

    def test_quantity_only_excess_requires_valuation_policy(self):
        result = self.calculate(targets=[target(target_quantity=5, commission_basis="excess")])
        self.assertEqual(result["sales_commission"], 0)
        self.assertEqual(result["blockers"][0]["code"], "quantity_excess_policy_missing")

    def test_net_negative_sales_are_blocked_without_debt_guess(self):
        result = self.calculate(facts=[fact(), fact("return-1", "return", 1500, 15)])
        self.assertEqual(result["sales_commission"], 0)
        self.assertIn("negative_net_sales", {v["code"] for v in result["blockers"]})

    def test_product_and_brand_overlap_requires_explicit_policy(self):
        targets = [target(), target(target_type="brand", item_identifier="برند آزمون", commission_percent=5)]
        result = self.calculate(targets=targets)
        self.assertEqual(result["sales_commission"], 0)
        self.assertIn("commission_overlap_policy_missing", {v["code"] for v in result["blockers"]})

    def test_highest_and_sum_overlap_policies(self):
        targets = [target(), target(target_type="brand", item_identifier="برند آزمون", commission_percent=5)]
        for policy, expected in [("highest", 100), ("sum", 150)]:
            with self.subTest(policy=policy):
                result = self.calculate(targets=targets, commission_overlap=policy)
                self.assertEqual(result["sales_commission"], expected)
                self.assertEqual(result["blockers"], [])

    def test_highest_is_per_product_not_whole_contract(self):
        targets = [target(commission_percent=20),
                   target(target_type="brand", item_identifier="برند آزمون", commission_percent=10)]
        result = self.calculate(targets=targets, facts=[fact(), fact("sale-2", amount=1000, product_id=8)],
                                commission_overlap="highest")
        self.assertEqual(result["sales_commission"], 300)

    def test_unreached_target_has_no_overlap_payment(self):
        targets = [target(target_amount=2000),
                   target(target_type="brand", item_identifier="برند آزمون", commission_percent=5)]
        result = self.calculate(targets=targets)
        self.assertEqual(result["sales_commission"], 50)
        self.assertEqual(result["blockers"], [])

    def test_collection_partial_and_reversal_uses_net_received_amount(self):
        for reversal in [100, -100]:
            result = self.calculate(targets=[], settlement_commission_percent=2,
                                    facts=[fact("receipt-1", "collection", 400),
                                           fact("receipt-2", "collection", 300),
                                           fact("reversal-1", "collection_reversal", reversal)])
            self.assertEqual(result["collection_commission"], 12)
            self.assertEqual(result["net_collected_amount"], 600)

    def test_net_negative_collection_is_blocked_without_debt_guess(self):
        result = self.calculate(targets=[], settlement_commission_percent=2,
                                facts=[fact("reversal-1", "collection_reversal", 100)])
        self.assertEqual(result["collection_commission"], 0)
        self.assertIn("negative_net_collections", {v["code"] for v in result["blockers"]})

    def test_mileage_uses_approved_kilometers_not_fact_money(self):
        result = self.calculate(targets=[], per_km_rate=2000,
                                facts=[fact("mission-1", "mileage", amount=9999, quantity="12.5")])
        self.assertEqual(result["mileage_allowance"], 25000)
        self.assertEqual(result["approved_kilometers"], 12.5)

    def test_repeatability_input_immutability_and_complete_statement_sum(self):
        rules = {"hourly_rate": 100, "min_monthly_hours": 2, "overtime_multiplier": 1.4,
                 "daily_mission_allowance": 50, "targets": [target()],
                 "settlement_commission_percent": 2, "per_km_rate": 3, "sales_scope": "personal"}
        facts = [fact(), fact("receipt-1", "collection", 500), fact("mission-1", "mileage", quantity=10)]
        original = json.dumps({"rules": rules, "facts": facts}, ensure_ascii=False)
        result = calculate_payroll(rules, 3, 2, facts,
                                   {"sales": True, "collections": True, "mileage": True})
        again = calculate_payroll(rules, 3, 2, facts,
                                  {"sales": True, "collections": True, "mileage": True})
        self.assertEqual(result, again)
        self.assertEqual(json.dumps({"rules": rules, "facts": facts}, ensure_ascii=False), original)
        self.assertEqual(result["provisional_total"], 580)
        self.assertEqual(sum(Decimal(str(result[key])) for key in
                             ["base_pay", "overtime_pay", "verified_visit_allowance", "sales_commission",
                              "collection_commission", "mileage_allowance"]), Decimal("580"))
        json.dumps(result, allow_nan=False)


class PayrollEngineFixedAndTierTests(unittest.TestCase):
    def codes(self, result):
        return {item["code"] for item in result["blockers"]}

    def tier_result(self, amount, **changes):
        rules = {"salary_mode": "commission_only", "sales_scope": "personal",
                 "commission_tier_basis": "marginal",
                 "sales_tiers": [{"up_to_amount": 1000, "percent": 5},
                                 {"up_to_amount": 2000, "percent": 7},
                                 {"up_to_amount": None, "percent": 10}], **changes}
        return calculate_payroll(rules, 0, 0, [fact(amount=amount)],
                                 {"sales": True, "company_sales": False})

    def test_fixed_full_salary_does_not_use_hourly_rate(self):
        result = calculate_payroll({"salary_mode": "fixed", "fixed_monthly_amount": 150000000,
                                    "fixed_proration": "full", "hourly_rate": 9999}, 20, 0)
        self.assertEqual(result["base_pay"], 150000000)
        self.assertEqual(result["fixed_pay"], 150000000)
        self.assertEqual(result["blockers"], [])

    def test_fixed_salary_requires_explicit_proration(self):
        result = calculate_payroll({"salary_mode": "fixed", "fixed_monthly_amount": 150000000}, 0, 0)
        self.assertIn("fixed_proration_missing", self.codes(result))
        self.assertEqual(result["base_pay"], 0)

    def test_fixed_workdays_prorate_from_explicit_approved_days(self):
        result = calculate_payroll({"salary_mode": "fixed", "fixed_monthly_amount": 150000000,
                                    "fixed_proration": "working_days", "required_workdays": 25,
                                    "worked_days": 20}, 0, 0)
        self.assertEqual(result["fixed_pay"], 120000000)
        self.assertEqual(result["blockers"], [])

    def test_fixed_workdays_need_required_days_and_complete_source(self):
        rules = {"salary_mode": "fixed", "fixed_monthly_amount": 150000000,
                 "fixed_proration": "working_days"}
        self.assertIn("required_workdays_missing", self.codes(calculate_payroll(rules, 0, 0)))
        rules["required_workdays"] = 25
        self.assertIn("workdays_source_incomplete", self.codes(calculate_payroll(rules, 0, 0)))

    def test_fixed_workday_facts_use_deduplicated_full_day_documents(self):
        rules = {"salary_mode": "fixed", "fixed_monthly_amount": 150000000,
                 "fixed_proration": "working_days", "required_workdays": 25}
        result = calculate_payroll(rules, 0, 0, [{"event_key": "day-1", "kind": "workday"},
                                               {"event_key": "day-2", "kind": "workday", "quantity": 0.5}],
                                   {"workdays": True})
        self.assertEqual(result["worked_days"], 1.5)
        self.assertEqual(result["fixed_pay"], 9000000)
        self.assertTrue(result["can_approve"])

    def test_fixed_more_than_required_days_does_not_invent_extra_payment(self):
        result = calculate_payroll({"salary_mode": "fixed", "fixed_monthly_amount": 100,
                                    "fixed_proration": "working_days", "required_workdays": 20,
                                    "worked_days": 25}, 0, 0)
        self.assertEqual(result["fixed_pay"], 100)

    def test_commission_only_never_adds_accidental_hourly_salary(self):
        result = calculate_payroll({"salary_mode": "commission_only", "hourly_rate": 10000,
                                    "min_monthly_hours": 176}, 200, 0)
        self.assertEqual(result["base_pay"], 0)
        self.assertEqual(result["overtime_pay"], 0)
        self.assertEqual(result["blockers"], [])

    def test_marginal_tiers_pay_only_incremental_difference(self):
        result = self.tier_result(2500)
        self.assertEqual(result["sales_commission"], 170)
        self.assertEqual(result["blockers"], [])
        self.assertEqual([item["applied_amount"] for item in result["tier_details"]], [1000, 1000, 500])

    def test_attained_tier_is_distinct_explicit_policy(self):
        result = self.tier_result(2500, commission_tier_basis="attained")
        self.assertEqual(result["sales_commission"], 250)

    def test_marginal_tier_return_and_signed_return_match(self):
        rules = {"salary_mode": "commission_only", "sales_scope": "personal",
                 "commission_tier_basis": "marginal",
                 "sales_tiers": [{"up_to_amount": 1000, "percent": 5},
                                 {"up_to_amount": None, "percent": 10}]}
        for amount in [500, -500]:
            result = calculate_payroll(rules, 0, 0, [fact(amount=2000),
                                                    fact("return-1", "return", amount, 1)], {"sales": True})
            self.assertEqual(result["sales_commission"], 100)
            self.assertEqual(result["blockers"], [])

    def test_company_tier_with_complete_company_source_is_allowed(self):
        rules = {"salary_mode": "commission_only", "sales_scope": "company",
                 "commission_tier_basis": "marginal",
                 "sales_tiers": [{"up_to_amount": None, "percent": 1}]}
        result = calculate_payroll(rules, 0, 0, [fact()], {"sales": True, "company_sales": True})
        self.assertEqual(result["sales_commission"], 10)
        self.assertEqual(result["blockers"], [])

    def test_tier_boundary_and_zero_sales(self):
        self.assertEqual(self.tier_result(1000)["sales_commission"], 50)
        self.assertEqual(self.tier_result(2000)["sales_commission"], 120)
        self.assertEqual(self.tier_result(0)["sales_commission"], 0)

    def test_tier_basis_and_post_target_rate_are_never_invented(self):
        result = self.tier_result(2500, commission_tier_basis=None)
        self.assertIn("commission_tier_policy_missing", self.codes(result))
        self.assertEqual(result["sales_commission"], 0)
        result = self.tier_result(2500, sales_tiers=[{"up_to_amount": 1000, "percent": 5}])
        self.assertIn("commission_tier_coverage_missing", self.codes(result))
        self.assertEqual(result["sales_commission"], 50)

    def test_company_scope_requires_explicit_company_source(self):
        result = self.tier_result(1000, sales_scope="company")
        self.assertIn("company_sales_source_incomplete", self.codes(result))
        self.assertFalse(result["can_approve"])
        result = self.tier_result(1000, sales_scope=None)
        self.assertIn("sales_scope_missing", self.codes(result))

    def test_tiers_and_product_targets_require_overlap_policy(self):
        result = self.tier_result(1000, targets=[target()])
        self.assertIn("commission_overlap_policy_missing", self.codes(result))
        self.assertEqual(self.tier_result(1000, targets=[target()], commission_overlap="highest")["sales_commission"], 100)
        self.assertEqual(self.tier_result(1000, targets=[target()], commission_overlap="sum")["sales_commission"], 150)

    def test_normalized_rules_keep_all_new_dimensions(self):
        rules = normalize_rules({"salary_mode": "fixed", "fixed_monthly_amount": "150000000",
                                 "fixed_proration": "working_days", "required_workdays": 25,
                                 "worked_days": 20, "sales_scope": "personal",
                                 "commission_tier_basis": "marginal",
                                 "sales_tiers": [{"up_to_amount": None, "percent": 1}]})
        self.assertEqual(rules["fixed_monthly_amount"], 150000000)
        self.assertEqual(rules["sales_tiers"], [{"up_to_amount": None, "percent": 1}])
        self.assertEqual(rules["required_workdays"], 25)
        self.assertEqual(rules["worked_days"], 20)
        self.assertEqual(rules["sales_scope"], "personal")
        self.assertEqual(rules["commission_tier_basis"], "marginal")
        json.dumps(rules, allow_nan=False)

    def test_invalid_salary_and_tier_configuration_is_rejected(self):
        for changes in [{"salary_mode": "formula"}, {"worked_days": -1},
                        {"required_workdays": 32}, {"fixed_proration": "assume"},
                        {"sales_tiers": [{"up_to_amount": 200, "percent": 1}, {"up_to_amount": 100, "percent": 2}]},
                        {"sales_tiers": [{"up_to_amount": None, "percent": 1}, {"up_to_amount": 100, "percent": 2}]},
                        {"sales_tiers": [{"percent": 1}]},
                        {"sales_tiers": [{"up_to_amount": None, "percent": 101}]}]:
            with self.subTest(changes=changes), self.assertRaises(PayrollValidationError):
                normalize_rules(changes)


class PayrollEngineContentExamplesTests(unittest.TestCase):
    def bonus(self, **changes):
        return {"monthly_amount": 20000000, "per_post_amount": 5000000, "required_posts": 4,
                "required_stories": 30, "story_requirement": "gate_full", **changes}

    def content_facts(self, posts=4, stories=30):
        return [{"event_key": "approved-posts", "kind": "content_post", "quantity": posts},
                {"event_key": "approved-stories", "kind": "content_story", "quantity": stories}]

    def test_each_approved_post_is_500_thousand_tomans_capped_at_four_posts(self):
        rules = {"salary_mode": "commission_only", "content_bonus": self.bonus()}
        for posts, expected in [(1, 5000000), (2, 10000000), (4, 20000000), (5, 20000000)]:
            with self.subTest(posts=posts):
                result = calculate_payroll(rules, 0, 0, self.content_facts(posts), {"content": True})
                self.assertEqual(result["content_pay"], expected)
                self.assertEqual(result["blockers"], [])

    def test_example_13_million_day_salary_plus_2_million_content_plus_one_percent_personal_sales(self):
        # Synthetic arithmetic example in rials; this does not approve anyone's contract.
        rules = {"salary_mode": "fixed", "fixed_monthly_amount": 130000000,
                 "fixed_proration": "working_days", "required_workdays": 25, "worked_days": 20,
                 "sales_scope": "personal", "commission_tier_basis": "marginal",
                 "sales_tiers": [{"up_to_amount": None, "percent": 1}], "content_bonus": self.bonus()}
        facts = self.content_facts() + [fact(amount=100000000)]
        result = calculate_payroll(rules, 0, 0, facts, {"sales": True, "content": True})
        self.assertEqual(result["fixed_pay"], 104000000)  # 13 million tomans * 20 / 25.
        self.assertEqual(result["content_pay"], 20000000)
        self.assertEqual(result["sales_commission"], 1000000)
        self.assertEqual(result["provisional_total"], 125000000)
        self.assertEqual(result["blockers"], [])

    def test_missing_story_policy_or_pending_story_target_cannot_approve(self):
        for story_requirement, expected in [(None, "content_story_policy_missing"),
                                             ("gate_full", "content_story_target_pending")]:
            with self.subTest(story_requirement=story_requirement):
                result = calculate_payroll({"salary_mode": "commission_only", "content_bonus": self.bonus(story_requirement=story_requirement)},
                                           0, 0, self.content_facts(stories=20), {"content": True})
                self.assertIn(expected, {item["code"] for item in result["blockers"]})
                self.assertFalse(result["can_approve"])

    def test_duplicate_content_never_pays_twice(self):
        facts = self.content_facts(posts=1)
        facts.append(dict(facts[0]))
        result = calculate_payroll({"salary_mode": "commission_only", "content_bonus": self.bonus()},
                                   0, 0, facts, {"content": True})
        self.assertEqual(result["content_posts"], 1)
        self.assertEqual(result["content_pay"], 5000000)
        self.assertIn("duplicate_event", {item["code"] for item in result["blockers"]})

    def test_content_with_missing_source_is_never_final_even_with_all_targets(self):
        result = calculate_payroll({"salary_mode": "commission_only", "content_bonus": self.bonus()},
                                   0, 0, self.content_facts(), {})
        self.assertIn("content_source_incomplete", {item["code"] for item in result["blockers"]})
        self.assertFalse(result["can_approve"])


class PayrollEngineBundleTests(unittest.TestCase):
    def test_only_complete_post_and_story_bundles_are_paid_and_monthly_cap_applies(self):
        bonus={'monthly_amount':20000000,'per_post_amount':5000000,'required_posts':4,'required_stories':30,'story_requirement':'per_bundle','stories_per_bundle':7}
        for posts,stories,expected in [(4,0,0),(4,6,0),(4,7,5000000),(4,14,10000000),(4,28,20000000),(1,30,5000000),(8,70,20000000)]:
            with self.subTest(posts=posts,stories=stories):
                result=calculate_payroll({'salary_mode':'commission_only','content_bonus':bonus},0,0,
                    [{'event_key':'posts','kind':'content_post','quantity':posts},{'event_key':'stories','kind':'content_story','quantity':stories}],{'content':True})
                self.assertEqual(result['content_pay'],expected)
                self.assertEqual(result['blockers'],[])

    def test_bundle_requires_explicit_positive_whole_story_count(self):
        for count in (None,0,-1,1.5,True):
            with self.subTest(count=count),self.assertRaises(PayrollValidationError):
                normalize_rules({'content_bonus':{'story_requirement':'per_bundle','stories_per_bundle':count}})


class PayrollEngineRewardTests(unittest.TestCase):
    def test_reward_is_independent_of_salary_sales_commission_and_content_pay(self):
        rules = {"hourly_rate": 100, "sales_scope": "personal", "commission_tier_basis": "marginal",
                 "sales_tiers": [{"up_to_amount": None, "percent": 10}],
                 "content_bonus": {"monthly_amount": 50, "per_post_amount": 50,
                                   "required_posts": 1, "required_stories": 0,
                                   "story_requirement": "independent"},
                 "bonus_note": "پاداش جداگانهٔ مدیریت"}
        facts = [fact(amount=100), {"event_key": "reward-first", "kind": "reward", "amount": 50},
                 {"event_key": "reward-second", "kind": "reward", "amount": 25},
                 {"event_key": "content-first", "kind": "content_post", "quantity": 1}]
        result = calculate_payroll(rules, 1, 0, facts, {"sales": True, "content": True, "rewards": True})
        self.assertEqual((result["base_pay"], result["sales_commission"], result["content_pay"], result["reward_pay"]),
                         (100, 10, 50, 75))
        self.assertEqual(result["provisional_total"], 235)
        self.assertEqual(result["blockers"], [])

    def test_reward_without_attestation_blocks_and_negative_reward_is_invalid(self):
        result = calculate_payroll({}, 0, 0, [{"event_key": "reward-first", "kind": "reward", "amount": 50}])
        self.assertEqual(result["reward_pay"], 50)
        self.assertIn("rewards_source_incomplete", {item["code"] for item in result["blockers"]})
        self.assertFalse(result["can_approve"])
        with self.assertRaises(PayrollValidationError):
            calculate_payroll({}, 0, 0, [{"event_key": "reward-negative", "kind": "reward", "amount": -1}],
                              {"rewards": True})

    def test_duplicate_reward_is_not_paid_twice(self):
        reward = {"event_key": "reward-first", "kind": "reward", "amount": 50}
        result = calculate_payroll({}, 0, 0, [reward, dict(reward)], {"rewards": True})
        self.assertEqual(result["reward_pay"], 50)
        self.assertIn("duplicate_event", {item["code"] for item in result["blockers"]})

    def test_bonus_note_is_retained_and_has_strict_length_and_type(self):
        self.assertEqual(normalize_rules({"bonus_note": "  توضیح مدیر  "})["bonus_note"], "توضیح مدیر")
        self.assertEqual(len(normalize_rules({"bonus_note": "ا" * 1000})["bonus_note"]), 1000)
        for value in ["ا" * 1001, None, {}, 42]:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(PayrollValidationError):
                normalize_rules({"bonus_note": value})


if __name__ == "__main__":
    unittest.main()
