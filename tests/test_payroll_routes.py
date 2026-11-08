"""آزمون نقش و پیش‌نمایش حقوق؛ بدون دیتابیس واقعی و درخواست بیرونی."""
import json
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import compensation
import payroll_assistant


class PayrollRouteTests(unittest.TestCase):
    def setUp(self):
        self.user = {"id": 2, "role": "salesperson", "salesperson_id": 10}
        app = FastAPI()
        app.include_router(compensation.router)
        app.dependency_overrides[compensation.current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        for patcher in (
            patch.object(compensation, "get_connection", side_effect=AssertionError("Real database disabled")),
            patch("requests.sessions.Session.request", side_effect=AssertionError("External HTTP disabled")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def manager(self):
        self.user = {"id": 1, "role": "ceo", "salesperson_id": None}

    def test_staff_cannot_draft_preview_or_write_facts_sources_and_contract(self):
        with patch.object(compensation, "_payroll_operation") as operation, patch.object(payroll_assistant, "draft_rules") as assistant:
            for role in ("salesperson", "visitor"):
                self.user["role"] = role
                for path in (
                    "/api/compensation/rules-draft",
                    "/api/compensation/rules-preview",
                    "/api/compensation/payroll/10/facts",
                    "/api/compensation/payroll/10/sources?month=1405-07",
                    "/api/compensation/contract/10",
                    "/api/compensation/payroll/10/approve?month=1405-07",
                ):
                    with self.subTest(role=role, path=path):
                        self.assertEqual(self.client.post(path, json={}).status_code, 403)
            operation.assert_not_called()
            assistant.assert_not_called()

    def test_staff_cannot_read_peer_facts_history_or_summary(self):
        with patch.object(compensation, "_payroll_operation", return_value={"items": [], "sources": []}) as operation:
            for path in (
                "/api/compensation/payroll/11/facts?month=1405-07",
                "/api/compensation/contract/11/history",
                "/api/compensation/payroll/11?month=1405-07",
                "/api/compensation/contract/11",
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 403)
            operation.assert_not_called()
            own = self.client.get("/api/compensation/payroll/10/facts?month=1405-07")
            self.assertEqual(own.status_code, 200)
            self.assertEqual(own.json()["items"], [])
            operation.assert_called_once()

    def test_manager_preview_calculates_without_saving(self):
        self.manager()
        with patch.object(compensation, "_payroll_operation") as operation:
            response = self.client.post("/api/compensation/rules-preview", json={
                "rules": {"hourly_rate": 100}, "worked_hours": 2, "verified_visit_days": 0,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provisional_total"], 200)
        self.assertTrue(response.json()["preview_only"])
        self.assertFalse(response.json()["saved"])
        operation.assert_not_called()

    def test_invalid_preview_is_rejected_without_storage(self):
        self.manager()
        with patch.object(compensation, "_payroll_operation") as operation:
            for payload in (
                {"rules": {"hourly_rate": "100 * hours"}},
                {"rules": {}, "worked_hours": "NaN"},
                {"rules": {}, "facts": {}},
            ):
                with self.subTest(payload=payload):
                    response = self.client.post("/api/compensation/rules-preview", json=payload)
                    self.assertEqual(response.status_code, 422)
            operation.assert_not_called()

    def ai_response(self, proposal):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": json.dumps(proposal)}}]}
        return response

    def ai_setting(self, name, default=""):
        return {"LLM_API_KEY": "isolated-test-key", "LLM_BASE_URL": "https://example.invalid/v1",
                "LLM_MODEL": "isolated-test-model"}.get(name, default)

    def test_ai_draft_requests_json_and_never_saves(self):
        self.manager()
        proposal = {"rules": {"hourly_rate": 100}, "questions": ["سقف ساعت موظفی چقدر است؟"], "summary": "پیشنهاد آزمایشی"}
        with patch.object(payroll_assistant, "get_env_live", side_effect=self.ai_setting), patch.object(payroll_assistant.requests, "post", return_value=self.ai_response(proposal)) as request, patch.object(compensation, "_payroll_operation") as operation:
            response = self.client.post("/api/compensation/rules-draft", json={"description": "برای هر ساعت کار تأییدشده صد ریال پرداخت شود"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rules"]["hourly_rate"], 100)
        self.assertTrue(response.json()["preview_only"])
        self.assertFalse(response.json()["saved"])
        self.assertEqual(request.call_args.kwargs["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(request.call_args.kwargs["json"]["temperature"], 0)
        operation.assert_not_called()

    def test_non_object_ai_json_is_rejected_without_server_error_or_storage(self):
        self.manager()
        with patch.object(payroll_assistant, "get_env_live", side_effect=self.ai_setting), patch.object(compensation, "_payroll_operation") as operation:
            for proposal in ([], "متن فاقد ساختار", None, {"rules": []}, {"rules": None}, {"rules": "100 * hours"}):
                with self.subTest(proposal=proposal), patch.object(payroll_assistant.requests, "post", return_value=self.ai_response(proposal)):
                    response = self.client.post("/api/compensation/rules-draft", json={"description": "شرح آزمایشی فرمول حقوق"})
                    self.assertEqual(response.status_code, 502)
            operation.assert_not_called()

    def test_ai_code_in_numeric_rule_is_never_executed_or_saved(self):
        self.manager()
        proposal = {"rules": {"hourly_rate": "__import__('os').system('anything')"}, "questions": []}
        with patch.object(payroll_assistant, "get_env_live", side_effect=self.ai_setting), patch.object(payroll_assistant.requests, "post", return_value=self.ai_response(proposal)), patch("os.system") as executable, patch.object(compensation, "_payroll_operation") as operation:
            response = self.client.post("/api/compensation/rules-draft", json={"description": "شرح آزمایشی فرمول حقوق"})
        self.assertIn(response.status_code, (422, 502))
        executable.assert_not_called()
        operation.assert_not_called()

    def test_invalid_source_verification_is_rejected_before_write(self):
        self.manager()
        with patch.object(compensation, "_payroll_operation") as operation:
            for payload in (
                {"source": "unknown", "complete": True, "note": "توضیح آزمایشی کامل"},
                {"source": "sales", "complete": "true", "note": "توضیح آزمایشی کامل"},
                {"source": "sales", "complete": True, "note": "کوتاه"},
            ):
                with self.subTest(payload=payload):
                    response = self.client.post("/api/compensation/payroll/10/sources?month=1405-07", json=payload)
                    self.assertEqual(response.status_code, 422)
            operation.assert_not_called()

    def test_missing_ai_setting_keeps_manual_entry_without_external_request(self):
        self.manager()
        with patch.object(payroll_assistant, "get_env_live", return_value=""), patch.object(payroll_assistant.requests, "post") as request, patch.object(compensation, "_payroll_operation") as operation:
            response = self.client.post("/api/compensation/rules-draft", json={"description": "شرح آزمایشی فرمول حقوق"})
        self.assertEqual(response.status_code, 503)
        request.assert_not_called()
        operation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
