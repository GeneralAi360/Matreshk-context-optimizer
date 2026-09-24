"""Regression coverage against provider-shaped data, not a detector-only mock."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/context-optimizer/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
import context_optimizer as co
import runtime_audit
import matreshka_bridge as mb
import standalone as st
from context_telemetry.detectors import detect_session_waste


def rollout(home, project, sid, content=True, timestamp='2026-09-24T08:00:00Z'):
    p = home / 'sessions/2026/09/24' / ('rollout-' + sid + '.jsonl')
    p.parent.mkdir(parents=True, exist_ok=True)
    events = [{'type':'session_meta', 'timestamp':timestamp, 'payload':{'id':sid,'cwd':str(project),'model':'test'}}]
    if content:
        events += [
            {'type':'response_item','timestamp':timestamp,'payload':{'type':'function_call','name':'read_file','arguments':json.dumps({'path':str(project / 'app.py')})}},
            {'type':'response_item','timestamp':timestamp,'payload':{'type':'function_call','name':'read_file','arguments':json.dumps({'path':str(project / 'app.py')})}},
            {'type':'response_item','timestamp':timestamp,'payload':{'type':'function_call_output','output':'x' * 70000}},
            {'type':'event_msg','timestamp':timestamp,'payload':{'type':'token_count','info':{'last_token_usage':{'input_tokens':3000,'output_tokens':100,'total_tokens':3100}, 'total_token_usage':{'input_tokens':3000,'output_tokens':100,'total_tokens':3100}}}},
        ]
    p.write_text('\n'.join(json.dumps(x) for x in events)+'\n',encoding='utf-8')
    return p


class Environment:

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.project = self.base/'project';self.project.mkdir()
        self.home = self.base/'provider';self.home.mkdir()
        (self.project/'AGENTS.md').write_text('Правила проекта\n',encoding='utf-8')
    def tearDown(self):
        self.temp.cleanup()
    def run_audit(self, command='adopt'):
        return co.run_command(command, self.project, provider='codex',include_global=False,telemetry_root=str(self.home),trigger_mode='MANUAL',trigger_reason='Проверка',trigger_automatic=False)


class Pipeline(Environment, unittest.TestCase):
    def test_provider_parser_to_report(self):
        rollout(self.home,self.project,'ours')
        result = self.run_audit()
        categories = {f['category'] for f in result['audit']['findings']}
        self.assertIn('NATIVE_TOOL_RESULT_DOMINANCE',categories)
        self.assertIn('NATIVE_REPEATED_FILE_READS',categories)
        self.assertEqual(result['runtime']['sessions'][0]['session_id'],'ours')
        self.assertTrue(any(f['category']=='NATIVE_TOOL_RESULT_DOMINANCE' for f in result['bridge']['topFindings']))
        # The last request total is NOT exact live window occupancy.
        self.assertEqual(result['bridge']['runtimeMeasurement']['semantics'],'OBSERVED_SUBSET')
        self.assertEqual(result['bridge']['runtimeMeasurement']['status'],'PARTIAL')
        f=next(f for f in result['audit']['findings'] if f['category']=='NATIVE_TOOL_RESULT_DOMINANCE')
        self.assertEqual(f['measurement']['unit'],'bytes')
        self.assertIsNone(f['expected_effect']['estimated_saving'])
        self.assertTrue(f['evidence'])
    def test_project_filter_before_budget_and_findings(self):
        ours=rollout(self.home,self.project,'ours')
        os.utime(ours,(1,1))
        for n in range(30):
            rollout(self.home,self.base/'another',f'other-{n}')
        result=self.run_audit()
        self.assertEqual([x['session_id'] for x in result['runtime']['sessions']],['ours'])
        self.assertTrue(all('ours' in f['evidence'][0]['locator'] for f in result['audit']['findings'] if f['scope']=='SESSION'))
    def test_latest_unknown_not_replaced_by_old(self):
        rollout(self.home,self.project,'old',timestamp='2026-09-23T08:00:00Z')
        rollout(self.home,self.project,'new',content=False)
        result=self.run_audit()
        self.assertIsNone(result['bridge']['runtimeMeasurement']['value'])
    def test_effective_snapshot_not_double_counted(self):
        x={'context':{'breakdown_bytes_effective':{},'breakdown_bytes_full':{'tool_result_bytes':70000}},'events':{}}
        self.assertFalse(detect_session_waste(x))
        x['context'].pop('breakdown_bytes_effective')
        f=detect_session_waste(x)[0]
        self.assertEqual(f['detail']['tracked_context_bytes'],70000)
        self.assertEqual(f['detail']['breakdown_source'],'breakdown_bytes_full')
    def test_boolean_is_not_token_measurement(self):
        rt={'engine':'Matreshka Context Telemetry','provider':'codex','sessions':[{'context':{'reported_context_tokens':True,'reported_context_measurement_type':'PROVIDER_MEASURED','reported_context_semantics':'CURRENT_CONTEXT'}}]}
        self.assertIsNone(mb.runtime_from_native(rt)['value'])
    def test_telemetry_failure_does_not_destroy_static_audit(self):
        with patch('context_optimizer.collect_runtime',side_effect=OSError('private path')):
            result=self.run_audit()
        self.assertIsNone(result['bridge']['runtimeMeasurement']['value'])
        self.assertTrue(result['warnings'])
        self.assertNotIn('private path',str(result['warnings']))


class Standalone(Environment, unittest.TestCase):
    def test_read_only_default(self):
        result=self.run_audit()
        st.render(result)
        self.assertFalse((self.project/st.STATE_DIR).exists())
    def test_save_full_report_and_new_chat(self):
        rollout(self.home,self.project,'ours')
        result=self.run_audit()
        locations=st.save_result(self.project,result)
        stored=st.read_latest(self.project)
        self.assertEqual(stored['audit']['summary']['finding_count'],2)
        self.assertNotIn('runtime',stored)
        self.assertTrue((self.project/locations['report']).is_file())
        self.assertTrue((self.project/locations['html']).is_file())
        self.assertIsNotNone(st.read_latest(self.project,'baseline'))
        self.assertIn('STATE.md',st.render(stored))
    def test_lock_conflict_does_not_overwrite(self):
        root=self.project/st.STATE_DIR;root.mkdir();(root/'state.lock').write_text('other')
        with self.assertRaises(ValueError):
            st.save_result(self.project,self.run_audit())
        self.assertEqual((root/'state.lock').read_text(encoding='utf-8'),'other')
    def test_memory_preserves_other_bytes_and_needs_approval(self):
        st.save_result(self.project,self.run_audit())
        original=b'Original user rules\r\nNO DELETE\r\n'
        target=self.project/'AGENTS.md';target.write_bytes(original)
        plan=st.remember(self.project,'codex',None)
        self.assertEqual(target.read_bytes(),original)
        with self.assertRaises(ValueError):st.remember(self.project,'codex','bad')
        st.remember(self.project,'codex',plan['approval'])
        after=target.read_bytes();self.assertTrue(after.startswith(original))
        plan2=st.remember(self.project,'codex',None)
        self.assertFalse(plan2['changed'])
        self.assertEqual(after.count(st.BEGIN),1)
    def test_memory_rejects_stale_approval(self):
        st.save_result(self.project,self.run_audit())
        plan=st.remember(self.project,'codex',None)
        (self.project/'AGENTS.md').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):st.remember(self.project,'codex',plan['approval'])
        self.assertEqual((self.project/'AGENTS.md').read_text(encoding='utf-8'),'changed')
    def test_state_symlink_refused(self):
        outside=self.base/'outside';outside.mkdir()
        try:(self.project/st.STATE_DIR).symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Symlink unavailable')
        with self.assertRaises(ValueError):st.save_result(self.project,self.run_audit())
        self.assertEqual(list(outside.iterdir()),[])
    def test_corrupt_pointer_fails_closed(self):
        d=self.project/st.STATE_DIR;d.mkdir();(d/'latest.json').write_text('{bad')
        with self.assertRaises(ValueError):st.read_latest(self.project)
    def test_finish_no_false_savings(self):
        result=self.run_audit('start');st.save_result(self.project,result)
        (self.project/'AGENTS.md').write_text('short',encoding='utf-8')
        result=self.run_audit('finish');st.save_result(self.project,result)
        stored=st.read_latest(self.project)
        self.assertEqual(stored['comparison']['verdict'],'UNVERIFIED')
        self.assertLess(stored['comparison']['static_bytes_delta'],0)
    def test_source_identity_not_reused_across_projects(self):
        st.save_result(self.project,self.run_audit())
        pointer=st.load(self.project,st.STATE_DIR+'/latest.json');aid=pointer['audit_id']
        path=self.project/st.STATE_DIR/'audits'/aid/'audit.json'
        doc=json.loads(path.read_text(encoding='utf-8'));doc['project_identity']='wrong';path.write_text(json.dumps(doc),encoding='utf-8')
        with self.assertRaises(ValueError):st.read_latest(self.project)
    def test_secret_redaction_and_html_escape(self):
        result=self.run_audit();result['message_ru']='password=secret-value <script>alert(1)</script>'
        locations=st.save_result(self.project,result)
        text=(self.project/locations['html']).read_text(encoding='utf-8')
        self.assertNotIn('secret-value',text)
        self.assertNotIn('<script>',text)
    def test_finished_baseline_rotates_only_on_new_start(self):
        st.save_result(self.project,self.run_audit('start'))
        first=st.load(self.project,st.STATE_DIR+'/baseline.json')['audit_id']
        st.save_result(self.project,self.run_audit('resume'))
        self.assertEqual(st.load(self.project,st.STATE_DIR+'/baseline.json')['audit_id'],first)
        st.save_result(self.project,self.run_audit('finish'))
        self.assertTrue(st.load(self.project,st.STATE_DIR+'/baseline.json')['closed'])
        st.save_result(self.project,self.run_audit('start'))
        self.assertNotEqual(st.load(self.project,st.STATE_DIR+'/baseline.json')['audit_id'],first)
    def test_compact_cli_does_not_dump_full_audit(self):
        proc=subprocess.run([sys.executable,'-B',str(SCRIPTS/'context_optimizer.py'),'--project',str(self.project),'--provider','none','status'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(proc.returncode,0,proc.stderr)
        doc=json.loads(proc.stdout)
        self.assertNotIn('audit',doc)
        self.assertNotIn('runtime',doc)
        self.assertIn('bridge',doc)
    def test_cli_standalone_without_matreshka(self):
        proc=subprocess.run([sys.executable,'-B',str(SCRIPTS/'standalone.py'),'--project',str(self.project),'--provider','none','--save','adopt'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('Сохранено:',proc.stdout)
        self.assertIsNotNone(st.read_latest(self.project))


if __name__=='__main__':
    unittest.main()
