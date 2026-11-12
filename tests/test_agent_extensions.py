import unittest
from contextlib import nullcontext
from uuid import uuid4
from unittest.mock import patch,MagicMock
from fastapi import HTTPException
from agent_extensions import SPECS,models,catalog,execute
from agent_playbooks import AUTO_OPERATIONS,PLAYBOOKS
from business_programmes import PROGRAMMES
class SpecialistRegistryTests(unittest.TestCase):
 def test_every_preset_has_real_domain_and_model(self):
  self.assertEqual(set(PROGRAMMES),set(PLAYBOOKS));self.assertEqual(set(SPECS),set(models()))
 def test_sensitive_operations_never_auto_approved(self):
  for name in ('training_publish','outbound_approve','contract_obligation_task'):
   self.assertEqual(SPECS[name]['kind'],'protected');self.assertNotIn(name,AUTO_OPERATIONS)
 def test_staff_catalog_hides_manager_tools(self):
  with patch('operations.role_has_module_permission',return_value=True):names={x['operation'] for x in catalog({'id':2,'role':'visitor'})}
  self.assertEqual(names,{'tracking_analytics','training_my_courses'})
 def test_creation_keys_not_in_model_catalog(self):
  with patch('operations.role_has_module_permission',return_value=True):items=catalog({'id':1,'role':'ceo'})
  for entry in items:self.assertNotIn('submission_key',entry['input_schema'].get('properties',{}))
 def test_forged_ceo_object_reloads_database_role(self):
  c=MagicMock();c.execute.return_value.mappings.return_value.first.return_value={'id':1,'role':'visitor'}
  with patch('agent_extensions.engine') as e:
   e.connect.return_value=nullcontext(c)
   with self.assertRaises(HTTPException) as caught:execute('target_scenarios',{}, {'id':1,'role':'ceo'})
  self.assertEqual(caught.exception.status_code,403)
 def test_staff_cannot_execute_manager_tool(self):
  with self.assertRaises(HTTPException) as caught:execute('outbound_approve',{}, {'id':2,'role':'visitor'})
  self.assertEqual(caught.exception.status_code,403)
 def test_unknown_tool_has_no_dynamic_dispatch(self):
  with self.assertRaises(HTTPException):execute('eval',{'code':'anything'},{'id':1,'role':'ceo'})
 def test_learners_need_no_permission_to_read_own_courses(self):
  with patch('training_workflows.listing',return_value={'items':[]}) as listing:result=execute('training_my_courses',{}, {'id':2,'role':'finance'})
  listing.assert_called_once_with({'id':2,'role':'finance'});self.assertEqual(result,{'items':[]})
