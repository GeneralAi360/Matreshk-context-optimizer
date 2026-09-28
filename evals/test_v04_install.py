"""Installer and installed runtime tests: real filesystem, no apps or network required."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('ctx_install', ROOT / 'install.py')
ins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ins)


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.project = self.base / 'Проект с пробелами'; self.project.mkdir()
        self.home = self.base / 'home'; self.home.mkdir()
        self.source = self.base / 'source'
        shutil.copytree(ROOT / 'skills/context-optimizer', self.source, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        self.root, self.target = ins.destination('cursor','project',self.project,self.home)
    def tearDown(self):
        self.tmp.cleanup()
    def install(self):
        preview, _ = ins.plan('install',self.source,self.target)
        return ins.apply(self.root,self.target,self.source,'install',preview['approval'])
    def run_quick(self, mode, *options, cwd=None):
        return subprocess.run([sys.executable,'-B',str(self.target/'scripts/quick.py'),'--harness','cursor','--project',str(self.project),*options,mode],cwd=cwd,encoding='utf-8',capture_output=True)
    def test_all_host_locations(self):
        expected = {'codex':'.agents/skills/context-optimizer','claude':'.claude/skills/context-optimizer','cursor':'.cursor/skills/context-optimizer','antigravity':'.agents/skills/context-optimizer','antigravity-cli':'.agents/skills/context-optimizer'}
        for host in ins.PROFILES:
            with self.subTest(host=host):
                root, dst = ins.destination(host,'project',self.project,self.home)
                self.assertEqual(dst,root/expected[host])
                root, dst = ins.destination(host,'user',self.project,self.home)
                self.assertEqual(root,self.home)
                self.assertEqual(dst,root/ins.PROFILES[host][1])
    def test_preview_no_write(self):
        self.assertEqual(ins.plan('install',self.source,self.target)[0]['status'],'PREVIEW')
        self.assertEqual(list(self.project.iterdir()),[])
    def test_wrong_approval_no_write(self):
        with self.assertRaises(ins.InstallError):ins.apply(self.root,self.target,self.source,'install','bad')
        self.assertEqual(list(self.project.iterdir()),[])
    def test_payload_change_invalidates_approval(self):
        preview,_=ins.plan('install',self.source,self.target)
        (self.source/'notes.txt').write_text('new',encoding='utf-8')
        with self.assertRaises(ins.InstallError):ins.apply(self.root,self.target,self.source,'install',preview['approval'])
    def test_install_and_doctor(self):
        self.install()
        self.assertEqual(ins.doctor(self.root,self.target,'cursor')['status'],'INSTALLED')
        self.assertTrue((self.target/'scripts/standalone.py').exists())
        self.assertFalse((self.project/'AGENTS.md').exists())
    def test_second_install_unchanged(self):
        self.install(); before=ins.snapshot(self.target)[0]
        preview,_=ins.plan('install',self.source,self.target)
        self.assertEqual(preview['status'],'UNCHANGED')
        self.assertEqual(ins.snapshot(self.target)[0],before)
    def test_shared_codex_antigravity_target(self):
        root,dst=ins.destination('codex','project',self.project,self.home)
        p,_=ins.plan('install',self.source,dst);ins.apply(root,dst,self.source,'install',p['approval'])
        _,other=ins.destination('antigravity','project',self.project,self.home)
        self.assertEqual(dst,other)
        self.assertEqual(ins.plan('install',self.source,other)[0]['status'],'UNCHANGED')
    def test_unmanaged_target_refused(self):
        self.target.mkdir(parents=True);(self.target/'mine.txt').write_text('mine',encoding='utf-8')
        with self.assertRaises(ins.InstallError):ins.plan('install',self.source,self.target)
        self.assertEqual((self.target/'mine.txt').read_text(encoding='utf-8'),'mine')
    def test_modified_owned_file_refused(self):
        self.install();(self.target/'SKILL.md').write_text('edited by user',encoding='utf-8')
        for mode in ('update','uninstall'):
            with self.assertRaises(ins.InstallError):ins.plan(mode,self.source,self.target)
    def test_added_file_and_empty_dir_refused(self):
        self.install();p=self.target/'personal.txt';p.write_text('private',encoding='utf-8')
        with self.assertRaises(ins.InstallError):ins.plan('update',self.source,self.target)
        p.unlink();(self.target/'personal').mkdir()
        with self.assertRaises(ins.InstallError):ins.plan('uninstall',self.source,self.target)
    def test_removed_owned_file_refused(self):
        self.install();(self.target/'SKILL.md').unlink()
        with self.assertRaises(ins.InstallError):ins.plan('update',self.source,self.target)
    def test_corrupt_manifest_refused(self):
        self.install();(self.target/ins.MANIFEST).write_text('{bad',encoding='utf-8')
        with self.assertRaises(ins.InstallError):ins.plan('update',self.source,self.target)
    def test_update_archives_old_and_keeps_other_skill(self):
        self.install();old=ins.snapshot(self.target)[0]
        other=self.target.parent/'other';other.mkdir();(other/'SKILL.md').write_text('other',encoding='utf-8')
        (self.source/'notes.txt').write_text('new version',encoding='utf-8')
        preview,_=ins.plan('update',self.source,self.target)
        result=ins.apply(self.root,self.target,self.source,'update',preview['approval'])
        self.assertEqual(ins.snapshot(Path(result['backup']))[0],old)
        self.assertEqual((other/'SKILL.md').read_text(encoding='utf-8'),'other')
        self.assertEqual((self.target/'notes.txt').read_text(encoding='utf-8'),'new version')
    def test_uninstall_preserves_audits_and_rules(self):
        self.install();audit=self.project/'.context-optimizer';audit.mkdir();(audit/'STATE.md').write_text('state',encoding='utf-8')
        rule=self.project/'AGENTS.md';rule.write_text('rules',encoding='utf-8')
        p,_=ins.plan('uninstall',self.source,self.target)
        r=ins.apply(self.root,self.target,self.source,'uninstall',p['approval'])
        self.assertFalse(self.target.exists());self.assertTrue((Path(r['backup'])/'SKILL.md').exists())
        self.assertEqual(rule.read_text(encoding='utf-8'),'rules')
        self.assertEqual((audit/'STATE.md').read_text(encoding='utf-8'),'state')
    def test_missing_uninstall_noop(self):
        self.assertEqual(ins.plan('uninstall',self.base/'missing',self.target)[0]['status'],'UNCHANGED')
    def test_lock_refuses_parallel_write(self):
        p,_=ins.plan('install',self.source,self.target)
        (self.root/ins.STATE).mkdir();(self.root/ins.STATE/'install.lock').write_text('busy',encoding='utf-8')
        with self.assertRaises(ins.InstallError):ins.apply(self.root,self.target,self.source,'install',p['approval'])
        self.assertFalse(self.target.exists())
    def test_pending_transaction_refused(self):
        self.install();d=self.root/ins.STATE/'transactions';(d/'incomplete.json').write_text('{"status":"PREPARING"}',encoding='utf-8')
        self.assertEqual(ins.doctor(self.root,self.target,'cursor')['status'],'NEEDS_REVIEW')
        p,_=ins.plan('uninstall',self.source,self.target)
        with self.assertRaises(ins.InstallError):ins.apply(self.root,self.target,self.source,'uninstall',p['approval'])
    def test_update_activation_failure_restores_original(self):
        self.install();old=ins.snapshot(self.target)[0]
        (self.source/'notes.txt').write_text('new',encoding='utf-8');p,_=ins.plan('update',self.source,self.target)
        real=ins.os.replace
        def fail_stage(source,dest):
            if Path(source).parent.name=='staging':raise OSError('injected failure')
            return real(source,dest)
        with patch.object(ins.os,'replace',side_effect=fail_stage):
            with self.assertRaises(ins.InstallError):ins.apply(self.root,self.target,self.source,'update',p['approval'])
        self.assertEqual(ins.snapshot(self.target)[0],old)
    def test_symlink_parent_refused(self):
        outside=self.base/'outside';outside.mkdir()
        try:(self.project/'.cursor').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Symlink privilege unavailable')
        with self.assertRaises(ins.InstallError):ins.plan('install',self.source,self.target)
        self.assertFalse(list(outside.iterdir()))
    def test_source_symlink_refused(self):
        try:(self.source/'linked').symlink_to(ROOT/'LICENSE')
        except OSError:self.skipTest('Symlink privilege unavailable')
        with self.assertRaises(ins.InstallError):ins.package(self.source)
    def test_source_hardlink_refused(self):
        p=self.source/'hard';original=self.base/'file';original.write_text('x',encoding='utf-8')
        try:os.link(original,p)
        except OSError:self.skipTest('Hardlinks unavailable')
        with self.assertRaises(ins.InstallError):ins.package(self.source)
    def test_oversized_source_refused(self):
        with patch.object(ins,'LIMIT',10):
            with self.assertRaises(ins.InstallError):ins.package(self.source)
    def test_package_missing_runtime_refused(self):
        (self.source/'scripts/quick.py').unlink()
        with self.assertRaises(ins.InstallError):ins.package(self.source)
    def test_installed_quick_runs_outside_skill_cwd(self):
        self.install();r=self.run_quick('adopt',cwd=self.home)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Сохранено:',r.stdout)
        self.assertTrue((self.project/'.context-optimizer/STATE.md').is_file())
        self.assertEqual(ins.doctor(self.root,self.target,'cursor')['status'],'INSTALLED')
    def test_installed_modes_help_doctor_status_are_read_only(self):
        self.install()
        for mode in ('help','doctor','status'):
            r=self.run_quick(mode);self.assertEqual(r.returncode,0,r.stderr)
            self.assertFalse((self.project/'.context-optimizer').exists())
        self.assertIn('Cursor',self.run_quick('doctor').stdout)
    def test_read_only_audit(self):
        self.install();r=self.run_quick('adopt','--read-only')
        self.assertEqual(r.returncode,0,r.stderr);self.assertFalse((self.project/'.context-optimizer').exists())
    def test_invalid_mode_does_not_execute(self):
        self.install();r=self.run_quick('adopt; echo BAD')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.project/'.context-optimizer').exists())
    def test_approval_restricted_to_memory(self):
        self.install();r=self.run_quick('adopt','--approve','TOKEN')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.project/'.context-optimizer').exists())
    def test_installed_status_remember_finish(self):
        self.install();self.assertEqual(self.run_quick('start').returncode,0)
        r=self.run_quick('remember');self.assertEqual(r.returncode,0,r.stderr)
        p=json.loads(r.stdout);self.assertFalse((self.project/'AGENTS.md').exists())
        r=self.run_quick('remember','--approve',p['approval']);self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue((self.project/'AGENTS.md').exists())
        self.assertEqual(self.run_quick('finish').returncode,0)
        r=self.run_quick('status');self.assertIn('не подтверждена',r.stdout.lower())
    def test_cli_preview_and_apply_utf8(self):
        args=[sys.executable,'-B',str(ROOT/'install.py'),'install','--host','cursor','--project',str(self.project),'--source',str(self.source)]
        r=subprocess.run(args,encoding='utf-8',capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr);p=json.loads(r.stdout)
        r=subprocess.run([*args,'--approve',p['approval']],encoding='utf-8',capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'APPLIED')


if __name__=='__main__':unittest.main()
