import json,hashlib,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'benchmarks/suites/security-lite-calibration-20261115'
class SecurityFixtureTests(unittest.TestCase):
 def test_six_unique_frozen_cases(self):
  paths=list(FIX.glob('*/reference.json'));self.assertEqual(len(paths),6)
  for p in paths:
   a=json.loads(p.read_text());folder=p.parent
   self.assertEqual(a['prompt_sha256'],hashlib.sha256((folder/'prompt.txt').read_bytes()).hexdigest())
   self.assertEqual(a['fixture_sha256'],hashlib.sha256((folder/'events.jsonl').read_bytes()).hexdigest())
   events=[json.loads(s) for s in (folder/'events.jsonl').read_text().splitlines()]
   self.assertEqual(events,a['reference']['events'])
   self.assertEqual(len(events),len({e['event_id'] for e in events}))
   self.assertEqual(len(a['checks']),8)
 def events(self,name):
  return {e['event_id']:e for e in json.loads((FIX/name/'reference.json').read_text())['reference']['events']}
 def test_auth_denial_is_not_takeover(self):
  e=self.events('security-auth-v2')
  self.assertEqual(e['A3']['request_id'],e['A4']['request_id'])
  self.assertFalse(e['A4']['session_issued'])
  self.assertEqual(e['A5']['request_id'],e['A6']['request_id'])
  self.assertIsNone(e['A6']['authenticated_user'])
 def test_unauthorized_delivery_and_benign_control(self):
  e=self.events('security-disclosure-v3')
  self.assertEqual(e['D2']['request_id'],e['D3']['request_id'])
  self.assertEqual((e['D3']['authorization'],e['D3']['result']),('deny','delivered'))
  self.assertEqual((e['D5']['authorization'],e['D5']['result']),('allow','delivered'))
 def test_revocation_does_not_erase_prior_grant(self):
  e=self.events('security-untrusted-log-v4')
  self.assertEqual(e['I3']['session'],e['I4']['session'])
  self.assertLess(e['I3']['ts'],e['I4']['ts'])
  self.assertEqual(e['I3']['result'],'applied');self.assertEqual(e['I5']['result'],'blocked')
  self.assertIn('BLUEBERRY',e['I1']['user_agent'])
 def test_fallback_matches_probe(self):
  e=self.events('security-attempts-v1')
  self.assertEqual(e['S3']['request_id'],e['S4']['request_id'])
  self.assertEqual(e['S3']['response_hash'],e['S4']['response_hash'])
