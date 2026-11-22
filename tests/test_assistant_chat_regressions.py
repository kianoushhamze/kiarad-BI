"""Regression coverage for conversation history and chat fast paths."""
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

import assistant_engine as assistant


class AssistantChatRegressions(unittest.TestCase):
    def test_history_returns_latest_turns_in_order_for_current_role(self):
        database = create_engine('sqlite://')
        self.addCleanup(database.dispose)
        with database.begin() as conn:
            conn.execute(text('CREATE TABLE assistant_messages (id INTEGER, user_id INTEGER, role TEXT, content TEXT, intent TEXT)'))
            conn.execute(text("""INSERT INTO assistant_messages VALUES
                (1, 1, 'user', 'old', 'chat:visitor'),
                (2, 1, 'user', 'manager-only', 'chat:ceo'),
                (3, 1, 'user', 'question', 'chat:visitor'),
                (4, 1, 'assistant', 'answer', 'chat:visitor'),
                (5, 2, 'user', 'other user', 'chat:visitor')"""))

        with patch.object(assistant, 'engine', database):
            self.assertEqual(assistant.load_history(1, limit=2, role='visitor'), [
                {'role': 'user', 'content': 'question'},
                {'role': 'assistant', 'content': 'answer'},
            ])

    def test_greeting_does_not_require_company_reports(self):
        with patch.object(assistant.engine, 'connect', side_effect=AssertionError('unexpected database read')), \
             patch.object(assistant, 'save_turn'), patch.object(assistant, 'call_gpt') as model:
            result = assistant.chat(assistant.ChatRequest(message='سلام!'), {'id': 1, 'role': 'ceo'})
        self.assertEqual(result['mode'], 'verified_greeting')
        model.assert_not_called()

    def test_general_question_does_not_prefetch_reports_or_replay_old_answers(self):
        with patch.object(assistant.engine, 'connect', side_effect=AssertionError('unexpected report read')), \
             patch.object(assistant, 'load_history', return_value=[
                 {'role': 'user', 'content': 'شروع آموزش'},
                 {'role': 'assistant', 'content': 'پاسخ دارای دادهٔ داخلی'},
             ]), patch.object(assistant, 'save_turn'), patch.object(assistant, 'call_gpt', return_value='پاسخ آموزشی') as model:
            result = assistant.chat(assistant.ChatRequest(message='برای فروش محصول چه آموزشی پیشنهاد می‌دهی؟'),
                                    {'id': 1, 'role': 'visitor', 'salesperson_id': None})
        self.assertEqual(result['answer'], 'پاسخ آموزشی')
        _, context, history, _, _ = model.call_args.args
        self.assertEqual(context['scope'], 'personal')
        self.assertIn('access_note', context)
        self.assertEqual(history, [{'role': 'user', 'content': 'شروع آموزش'}])

    def test_learning_followup_does_not_force_internal_tools(self):
        def complete(payload, headers):
            self.assertNotIn('tool_choice', payload)
            return {'choices': [{'message': {'content': 'پاسخ آموزشی'}}]}

        with patch.object(assistant, 'get_env_live', return_value='test-model'), \
             patch.object(assistant, '_chat_completion', side_effect=complete):
            answer = assistant.call_gpt('ادامه آموزش مارکتینگ و فروش',
                                        {}, [{'role': 'user', 'content': 'آموزش'}], 'ceo', '')
        self.assertEqual(answer, 'پاسخ آموزشی')

    def test_company_sales_missing_and_zero_are_distinct(self):
        for amount, expected in ((None, 'sales_data_required'), (0, 'verified_sales')):
            with self.subTest(amount=amount), patch.object(assistant.engine, 'connect'), \
                 patch.object(assistant, 'build_live_context', return_value={'sales_month': amount}), \
                 patch.object(assistant, 'save_turn'), patch.object(assistant, 'call_gpt') as model:
                result = assistant.chat(assistant.ChatRequest(message='فروش این ماه چقدره؟'), {'id': 1, 'role': 'ceo'})
                self.assertEqual(result['mode'], expected)
                model.assert_not_called()
