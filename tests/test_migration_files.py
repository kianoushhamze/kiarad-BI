import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("release_migrations", Path(__file__).resolve().parents[1] / "scripts/run_migrations.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class MigrationFilesTests(unittest.TestCase):
    def test_missing_payload_fails_before_connecting_to_database(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runner, "MIGRATIONS", Path(folder)), patch.object(runner, "connection") as connect, patch("sys.argv", ["run_migrations.py"]):
            with self.assertRaisesRegex(RuntimeError, "migration_files_missing"):
                runner.main()
            connect.assert_not_called()

    def test_operational_storage_migration_provisions_expected_tables(self):
        migration = runner.MIGRATIONS / "0012_operational_module_storage.sql"
        sql = migration.read_text(encoding="utf-8")
        for table in (
            "tasks", "role_permissions", "campaigns", "visit_route_assignments",
            "base_portfolio_assignments", "base_proposals", "monthly_visit_plans",
            "physicians", "social_channels", "market_questions", "integration_drafts",
            "treasury_strategy_revisions", "morning_briefs", "ai_suggestions",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)

    def test_release_contains_ordered_migration_payload(self):
        files = runner.migration_files()
        self.assertIn("0001_baseline.sql", [p.name for p in files])
        self.assertIn("0006_storefront_platform_storage.sql", [p.name for p in files])
        self.assertIn("0007_chat_crm_storage.sql", [p.name for p in files])
        self.assertIn("0008_visit_treasury_columns.sql", [p.name for p in files])
        self.assertIn("0009_assistant_operations_storage.sql", [p.name for p in files])
        self.assertIn("0010_treasury_excel_storage.sql", [p.name for p in files])
        self.assertIn("0011_site_auth_rate_limits.sql", [p.name for p in files])
        self.assertIn("0012_operational_module_storage.sql", [p.name for p in files])
        self.assertEqual(files, sorted(files))
