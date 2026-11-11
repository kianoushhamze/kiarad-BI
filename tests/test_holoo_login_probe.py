"""An unsuccessful login must fail the deployment probe, without real ERP calls."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class LoginProbeTests(unittest.TestCase):
    def probe(self, primary, legacy):
        main = ModuleType('holoo_router')
        old = ModuleType('holoo_sync')
        main.login_holoo = Mock(return_value=primary)
        old.holoo_login = Mock(return_value=legacy)
        output = io.StringIO()
        code = 0
        with patch.dict(sys.modules, {'holoo_router': main, 'holoo_sync': old}), redirect_stdout(output):
            try:
                runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_holoo_login.py'))
            except SystemExit as error:
                code = error.code
        return code, output.getvalue(), old.holoo_login

    def test_primary_false_fails_before_legacy(self):
        code, output, legacy = self.probe(None, 'synthetic-secret-not-for-output')
        self.assertEqual(code, 1)
        legacy.assert_not_called()
        self.assertIn('"login_ok": false', output)
        self.assertNotIn('synthetic-secret', output)

    def test_legacy_false_fails(self):
        code, output, _ = self.probe('synthetic-secret-not-for-output', None)
        self.assertEqual(code, 1)
        self.assertIn('"legacy_login_ok": false', output)
        self.assertNotIn('synthetic-secret', output)

    def test_both_success_return_zero_without_tokens(self):
        code, output, _ = self.probe('synthetic-secret-not-for-output', 'synthetic-secret-not-for-output')
        self.assertEqual(code, 0)
        self.assertIn('"login_ok": true', output)
        self.assertNotIn('synthetic-secret', output)
