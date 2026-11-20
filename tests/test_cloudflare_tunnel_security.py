"""Static safety regressions for the Windows Cloudflare tunnel installer."""
from pathlib import Path
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "cloudflare"
    / "kiarad_cloudflare_named_tunnel_v2.ps1"
).read_text(encoding="utf-8-sig")


class CloudflareTunnelSecurityTests(unittest.TestCase):
    def test_binary_must_be_authenticode_signed_by_cloudflare(self):
        self.assertIn("Get-AuthenticodeSignature", SCRIPT)
        self.assertIn("SignerCertificate.Subject", SCRIPT)
        self.assertIn("Status -ne 'Valid'", SCRIPT)
        self.assertNotIn("releases/latest/download", SCRIPT)

    def test_service_files_and_credentials_have_restricted_acl(self):
        self.assertIn("icacls.exe", SCRIPT)
        self.assertIn("S-1-5-18", SCRIPT)
        self.assertIn("S-1-5-32-544", SCRIPT)
        self.assertIn("Protect-Path $SvcDir -Directory", SCRIPT)
        self.assertIn("Protect-Path $LogDir -Directory", SCRIPT)
        self.assertIn("Protect-Path $credDestination", SCRIPT)
        self.assertIn("Protect-Path $configPath", SCRIPT)

    def test_existing_windows_service_is_reconfigured_not_deleted(self):
        self.assertIn("sc.exe config KiaradCloudflared", SCRIPT)
        self.assertNotIn("sc.exe delete", SCRIPT.lower())
        self.assertNotIn("Remove-Service", SCRIPT)

    def test_existing_tunnel_credentials_failure_is_non_destructive(self):
        self.assertIn("Credentials missing for existing tunnel", SCRIPT)
        self.assertIn("do not delete/recreate it", SCRIPT)
        self.assertNotIn("tunnel delete", SCRIPT.lower())

    def test_config_validation_precedes_service_changes_and_quick_tunnel_is_preserved(self):
        self.assertLess(SCRIPT.index("ingress validate"), SCRIPT.index("Windows service"))
        self.assertIn("Quick Tunnel was not stopped", SCRIPT)


if __name__ == "__main__":
    unittest.main()
