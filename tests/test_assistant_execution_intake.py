import unittest
from unittest.mock import patch
from fastapi import HTTPException
from assistant_engine import chat, ChatRequest
from assistant_operations import prepare


class ExecutionIntakeTests(unittest.TestCase):
    def test_contract_clarification_does_not_claim_source_inaccessible(self):
        with patch('assistant_engine.load_history', return_value=[]), patch('assistant_engine.save_turn'), patch('assistant_engine.call_gpt') as model:
            result=chat(ChatRequest(message='تو ماژول قراردادهای پنل منظورم بود'), {'id':1,'role':'ceo'})
        self.assertEqual(result['mode'],'contract_intake')
        self.assertIn('نام هر نفر',result['answer'])
        model.assert_not_called()

    def test_content_without_timezone_never_creates_proposal(self):
        with patch('assistant_operations.engine.begin') as database:
            with self.assertRaises(HTTPException) as error:
                prepare({'operation':'create_content_draft','payload':{'channel':'instagram','title':'آزمون','body':'محتوا','scheduled_at':'2026-11-04T10:00:00'}},{'id':1,'role':'ceo'})
        self.assertEqual(error.exception.status_code,422)
        database.assert_not_called()
