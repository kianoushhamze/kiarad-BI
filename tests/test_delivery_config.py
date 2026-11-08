"""Delivery regressions; synthetic dotenv files and mocked DB only."""
from io import StringIO
import os
import unittest
from unittest.mock import patch

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import api
import config


class DeliveryConfigTests(unittest.TestCase):
    def test_quoted_password_is_not_sent_to_driver_with_quotes(self):
        values = dotenv_values(stream=StringIO('POSTGRES_PASSWORD="p@ss # word" # note\n'))
        with patch.dict(os.environ, {}, clear=True), patch.object(config, 'dotenv_values', return_value=values):
            self.assertEqual(config._env('POSTGRES_PASSWORD'), 'p@ss # word')

    def test_export_and_inline_comments_follow_dotenv_rules(self):
        values = dotenv_values(stream=StringIO('export DB_HOST = localhost # local database\n'))
        with patch.dict(os.environ, {}, clear=True), patch.object(config, 'dotenv_values', return_value=values):
            self.assertEqual(config._env('DB_HOST'), 'localhost')

    def test_container_environment_takes_priority(self):
        with patch.dict(os.environ, DB_HOST='postgres'), patch.object(config, 'dotenv_values') as reader:
            self.assertEqual(config._env('DB_HOST'), 'postgres')
            reader.assert_not_called()

    def test_missing_value_uses_default(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(config, 'dotenv_values', return_value={}):
            self.assertEqual(config._env('DB_HOST', 'localhost'), 'localhost')

    def test_health_failure_hides_driver_details(self):
        error = OperationalError('SELECT 1', {}, Exception('internal-host private-driver-details'))
        with patch.object(api.engine, 'connect', side_effect=error):
            response = TestClient(api.app).get('/health')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'Database connection unavailable'})
        self.assertNotIn('internal-host', response.text)

    def test_health_success_checks_database(self):
        with patch.object(api.engine, 'connect') as connect:
            response = TestClient(api.app).get('/health')
        self.assertEqual(response.status_code, 200)
        connect.return_value.__enter__.return_value.execute.assert_called_once()


if __name__ == '__main__':
    unittest.main()
