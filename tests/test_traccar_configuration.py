import tempfile,unittest
from pathlib import Path
from scripts.configure_traccar import configure
from traccar_bridge import Forward
from pydantic import ValidationError
class ConfigurationTests(unittest.TestCase):
 def test_private_config_and_idempotent_key_without_persistent_location_store(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'.env').write_text('POSTGRES_PASSWORD=synthetic-only\nKIARAD_AUTOMATIONS_DISABLED=1\n');result=configure(root,'https://gps.company.example');first=(root/'secrets/traccar-forward.xml').read_text();configure(root,'https://gps.company.example');self.assertEqual(first,(root/'secrets/traccar-forward.xml').read_text());self.assertIn('database.memory',first);self.assertIn('web.enable',first);self.assertNotIn('forward_token',str(result).lower());self.assertIn('KIARAD_AUTOMATIONS_DISABLED=1',(root/'.env').read_text());self.assertIn('KIARAD_TRACCAR_ENABLED=1',(root/'.env').read_text());self.assertNotIn('tracker-server.log',first)
 def test_insecure_or_credentialed_client_urls_rejected_before_writes(self):
  for url in ['http://gps.example','https://name:password@gps.example','https://gps.example/?token=abc','https://gps.example/path','https://gps.example:bad','https://gps.example\nKIARAD_AGENT_DISABLED=0']:
   with self.subTest(url=url),tempfile.TemporaryDirectory() as t:
    root=Path(t);(root/'.env').write_text('existing=true\n')
    with self.assertRaises(ValueError):configure(root,url)
    self.assertEqual((root/'.env').read_text(),'existing=true\n');self.assertFalse((root/'secrets').exists())
 def test_missing_company_env_never_created(self):
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(ValueError):configure(Path(t),'https://gps.example')
   self.assertFalse((Path(t)/'.env').exists())
 def test_broken_existing_token_not_silently_rotated(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'.env').write_text('KIARAD_TRACCAR_FORWARD_TOKEN=short\n')
   with self.assertRaises(ValueError):configure(root,'https://gps.example')
   self.assertEqual((root/'.env').read_text(),'KIARAD_TRACCAR_FORWARD_TOKEN=short\n')

class ForwardAuthGateTests(unittest.TestCase):
 def setUp(self):
  from unittest.mock import patch
  self.enterContext(patch.dict(__import__('os').environ,{'KIARAD_TRACCAR_ENABLED':'1','KIARAD_TRACCAR_FORWARD_TOKEN':'synthetic-forward-token-0123456789012345','KIARAD_API_KEY':'synthetic-global-api-key'}))
  from fastapi.testclient import TestClient
  from api import app
  self.client=TestClient(app);self.addCleanup(self.client.close)
 def test_forwarding_key_required_even_with_global_api_key(self):
  r=self.client.post('/tracking/traccar/positions',json={},headers={'X-API-Key':'synthetic-global-api-key'});self.assertEqual(r.status_code,401)
 def test_correct_server_key_reaches_schema_without_user_login(self):
  r=self.client.post('/tracking/traccar/positions',json={},headers={'X-Kiarad-Traccar-Token':'synthetic-forward-token-0123456789012345'});self.assertEqual(r.status_code,422)
 def test_forwarding_credential_does_not_unlock_device_management(self):
  r=self.client.get('/tracking/traccar/devices',headers={'X-Kiarad-Traccar-Token':'synthetic-forward-token-0123456789012345'});self.assertEqual(r.status_code,401)
 def test_correct_key_still_enforces_body_limit(self):
  r=self.client.post('/tracking/traccar/positions',content=b'x'*33000,headers={'Content-Type':'application/json','X-Kiarad-Traccar-Token':'synthetic-forward-token-0123456789012345'});self.assertEqual(r.status_code,413)
 def test_correct_key_requires_json_content_type(self):
  r=self.client.post('/tracking/traccar/positions',content='{}',headers={'Content-Type':'text/plain','X-Kiarad-Traccar-Token':'synthetic-forward-token-0123456789012345'});self.assertEqual(r.status_code,415)
