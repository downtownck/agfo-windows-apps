import hashlib
import importlib.util
import subprocess
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import agfo_network as net
import agfo_tray as tray
import agfo_installer as installer


class NetworkTests(unittest.TestCase):
    def test_read_profiler_share_roots_with_turkish_paths(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'AGFO-BackupSync' / 'profiles'
            path.mkdir(parents=True)
            (path / 'one.json').write_text(json.dumps({
                'source': r'\\SYNOLOGY\Denetim\İçerik',
                'target': r'\\UGREEN\Yedekler\Ekim',
            }, ensure_ascii=False), encoding='utf-8')
            with patch.dict(os.environ, {'LOCALAPPDATA': root}):
                self.assertEqual(net._profile_unc_paths(),
                                 [r'\\SYNOLOGY\Denetim', r'\\UGREEN\Yedekler'])

    def test_discovery_is_read_only_unless_scan_selected(self):
        with patch.object(net, 'known_items', return_value=([{
            'kind': 'X', 'path': r'\\NAS\Files', 'name': 'Files',
            'origin': 'mapped', 'state': 'Bagli', 'selectable': True
        }], [])):
            with patch.object(net, '_scan_smb_hosts', side_effect=AssertionError('must not scan')):
                report = net.discover('known')
        self.assertEqual(report['mode'], 'known')
        self.assertEqual(report['items'][0]['path'], r'\\NAS\Files')

    def test_no_duplicate_shares(self):
        out = []
        net._add(out, 'SMB', r'\\NAS\SHARE', 'one', 'x')
        net._add(out, 'SMB', r'\\nas\share', 'two', 'x')
        self.assertEqual(len(out), 1)

    def test_scan_filters_not_private_networks(self):
        with patch.object(net, '_private_networks', return_value=[]):
            with patch.object(net, 'known_items', return_value=([], [])):
                with patch.object(net.sys, 'platform', 'win32'):
                    result = net.discover('scan')
        self.assertEqual(result['items'], [])
        self.assertTrue(result['warnings'])

    def test_active_smb_sessions_without_mapped_drive(self):
        with patch.object(net.sys, 'platform', 'win32'):
            with patch.object(net, '_win_mapped_drives', return_value=[]):
                with patch.object(net, '_win_persistent_drives', return_value=[]):
                    with patch.object(net, '_win_active_smb_connections',
                                      return_value=[('UGREEN', 'Backup'), ('UGREEN', 'ADMIN$')]):
                        with patch.object(net, '_profile_unc_paths', return_value=[]):
                            rows, notes = net.known_items()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['path'], chr(92) * 2 + 'UGREEN' + chr(92) + 'Backup')
        self.assertTrue(rows[0]['selectable'])

    def test_write_report_atomic_utf8(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root) / 'rapor.json'
            net.write_result({'items': [{'name': 'İçerik'}]}, str(dest))
            self.assertEqual(json.loads(dest.read_text(encoding='utf-8'))['items'][0]['name'], 'İçerik')
            self.assertFalse(Path(str(dest) + '.tmp').exists())

    def test_probe_readable_directory(self):
        with tempfile.TemporaryDirectory() as root:
            result = tray.probe_path(root)
            self.assertTrue(result['ok'])
            self.assertIn('okunabilir', result['message'].lower())


class InstallerTests(unittest.TestCase):
    def test_valid_manifest(self):
        filenames = ['AGFO-BackupSync.exe', 'AGFO-BackupSync-GUI.ps1',
                     'AGFO-BackupSync-Core.ps1', 'AGFO-BackupSync-Worker.ps1',
                     'AGFO-Guvenli-Baslat.ps1', 'Create-AgfoShortcut.ps1']
        with tempfile.TemporaryDirectory() as root:
            for name in filenames:
                (Path(root) / name).write_bytes(b'fixture')
            hashes = {name: hashlib.sha256(b'fixture').hexdigest() for name in filenames}
            (Path(root) / 'manifest.json').write_text(json.dumps({'version': installer.VERSION,
                                                                  'files': hashes}), encoding='utf-8')
            self.assertEqual(installer.payload_files(Path(root)), hashes)
            (Path(root) / filenames[0]).write_bytes(b'tampered')
            with self.assertRaises(RuntimeError):
                installer.payload_files(Path(root))

    def test_manifest_prevents_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'manifest.json').write_text(json.dumps({
                'version': installer.VERSION, 'files': {'../attack': 'a' * 64}}), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                installer.payload_files(Path(root))




class DriveLetterTests(unittest.TestCase):
    def test_mapping_unc_uses_net_use_and_persistent(self):
        import agfo_drives as d
        plan = d.mapping_plan(r'\\UGREEN\Belgeler\Ekim', 'Z:', True, [])
        self.assertEqual(plan['kind'], 'SMB')
        self.assertEqual(plan['command'], [d._windows_exe('net.exe'), 'use', 'Z:',
                                           r'\\UGREEN\Belgeler\Ekim', '/persistent:yes'])
        self.assertNotIn('password', ' '.join(plan['command']).lower())

    def test_local_subst_is_session_only(self):
        import agfo_drives as d
        plan = d.mapping_plan(r'D:\Belgeler\Arsiv', 'Y', False, [])
        self.assertEqual(plan['command'], [d._windows_exe('subst.exe'), 'Y:', r'D:\Belgeler\Arsiv'])
        with self.assertRaises(ValueError):
            d.mapping_plan(r'D:\Belgeler\Arsiv', 'Y:', True, [])

    def test_mapped_network_subfolder_canonicalized(self):
        import agfo_drives as d
        known = [{'letter': 'S:', 'kind': 'SMB', 'target': r'\\Synology\Reports'}]
        plan = d.mapping_plan(r'S:\2026\Ekim', 'Z:', True, known)
        self.assertEqual(plan['target'], r'\\Synology\Reports\2026\Ekim')
        self.assertEqual(plan['kind'], 'SMB')

    def test_invalid_paths_or_drive_letters_rejected(self):
        import agfo_drives as d
        for bad in ('A:', 'C:', 'ZZ', 'Z:/tmp', ';'):
            with self.assertRaises(ValueError):
                d.letter(bad)
        for path in (r'\\NAS', r'\\?\C:\Windows', r'\\.\C:', r'file.txt',
                     '\\NAS\\share\narg'):
            with self.assertRaises(ValueError):
                d.mapping_plan(path, 'Z', True, [])

    def test_used_drive_cannot_be_overwritten(self):
        import agfo_drives as d
        with patch.object(d.sys, 'platform', 'win32'):
            with patch.object(d, 'available_letters', return_value=['Y:']):
                with patch.object(d, '_run', side_effect=AssertionError('no command')):
                    with self.assertRaises(ValueError):
                        d.map_drive(r'\\NAS\Backup', 'Z:', True)

    def test_unmap_cannot_delete_physical_disk(self):
        import agfo_drives as d
        with patch.object(d.sys, 'platform', 'win32'):
            with patch.object(d, 'mappings', return_value=[]):
                with patch.object(d, '_run', side_effect=AssertionError('no command')):
                    with self.assertRaises(ValueError):
                        d.unmap_drive('D:')

    def test_unmap_chooses_correct_windows_command(self):
        import agfo_drives as d
        for row, command in [
            ({'letter': 'Z:', 'kind': 'SMB', 'target': r'\\NAS\Share'},
             [d._windows_exe('net.exe'), 'use', 'Z:', '/delete', '/yes']),
            ({'letter': 'Y:', 'kind': 'SUBST', 'target': r'D:\Local'},
             [d._windows_exe('subst.exe'), 'Y:', '/d']),
        ]:
            with patch.object(d.sys, 'platform', 'win32'):
                with patch.object(d, 'mappings', return_value=[row]):
                    with patch.object(d, '_run') as action:
                        result = d.unmap_drive(row['letter'])
                        self.assertTrue(result['ok'])
                        action.assert_called_once_with(command)

    def test_subst_does_not_allow_alias_to_itself(self):
        import agfo_drives as d
        with self.assertRaises(ValueError):
            d.mapping_plan('Z:\\Docs', 'Z:', False, [])

    def test_free_letters_protects_physical_and_persistent(self):
        import agfo_drives as d
        with patch.object(d, 'mappings', return_value=[{'letter': 'Z:'}]):
            with patch.object(d, '_windows_drive_mask', return_value=1 << (ord('Y') - 65)):
                allowed = d.available_letters()
        self.assertNotIn('Z:', allowed)
        self.assertNotIn('Y:', allowed)
        self.assertIn('X:', allowed)


class BuildEnvironmentTests(unittest.TestCase):
    @staticmethod
    def helper():
        file = Path(__file__).resolve().parents[1] / 'packaging' / 'prepare_build_env.py'
        spec = importlib.util.spec_from_file_location('agfo_prepare_build_env', file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_build_uses_local_cache_and_python_helper(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / 'packaging' / 'build_windows.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("$buildCache = Join-Path $env:LOCALAPPDATA 'AGFO-BackupSync\\build-cache'", script)
        self.assertIn("$venv = Join-Path $buildCache 'venv'", script)
        self.assertIn("$dist = Join-Path $buildCache 'dist'", script)
        self.assertIn("$publishDist = Join-Path $root 'dist'", script)
        self.assertIn("Copy-Item -LiteralPath $setupExe", script)
        self.assertIn("packaging\\prepare_build_env.py", script)
        self.assertNotIn('function Test-BuildVenv', script)
        self.assertNotIn("import sys, pip; print(sys.base_prefix)", script)
        self.assertIn("Assert-Exit 'Python sanal ortam hazirligi'", script)
        self.assertIn("$venvPython = Join-Path $venv 'Scripts\\python.exe'", script)

    def test_setup_manifest_matches_installer_version(self):
        script = (Path(__file__).resolve().parents[1] / 'packaging' / 'build_windows.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("$manifest = [ordered]@{ version = '" + installer.VERSION + "';", script)

    def test_existing_venv_without_pip_is_repaired_not_deleted(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'venv'
            creation = subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(root)],
                                      capture_output=True, text=True)
            self.assertEqual(creation.returncode, 0, creation.stderr)
            actual = helper.venv_python(root)
            ok, msg = helper.verify_venv(root, sys.base_prefix, sys.version_info[:2])
            self.assertTrue(ok, msg)  # Absence of pip is not an invalid venv.
            has_pip, _ = helper.pip_available(actual)
            self.assertFalse(has_pip)
            messages = []
            result = helper.prepare_build_environment(root, printer=messages.append)
            self.assertEqual(result, actual)
            has_pip, detail = helper.pip_available(actual)
            self.assertTrue(has_pip, detail)
            self.assertTrue(any('ensurepip' in m for m in messages), messages)
            self.assertFalse(any('yeniden olusturuyorum' in m for m in messages), messages)

    def test_stale_cross_computer_venv_is_rebuilt(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'venv'
            root.mkdir()
            (root / 'pyvenv.cfg').write_text('home = C:\\BrokenPython312\\\n', encoding='utf-8')
            messages = []
            actual = helper.prepare_build_environment(root, printer=messages.append)
            self.assertTrue(actual.is_file())
            ok, msg = helper.verify_venv(root, sys.base_prefix, sys.version_info[:2])
            self.assertTrue(ok, msg)
            self.assertTrue(any('yeniden olusturuyorum' in m for m in messages), messages)

    def test_cli_rejects_unexpected_venv_path(self):
        helper = self.helper()
        with tempfile.TemporaryDirectory() as tmp:
            danger = Path(tmp) / 'do-not-touch'
            danger.mkdir()
            (danger / 'important.txt').write_text('retain', encoding='utf-8')
            with patch.dict(os.environ, {'LOCALAPPDATA': tmp}):
                with patch.object(sys, 'argv', ['prepare_build_env.py', '--venv', str(danger)]):
                    self.assertEqual(helper.main(), 2)
            self.assertEqual((danger / 'important.txt').read_text(), 'retain')


if __name__ == '__main__':
    unittest.main()


class SelfUpdateTests(unittest.TestCase):
    """v2.3.0 - GitHub'dan tek tik guncelleme (ag gerektirmez)."""

    def setUp(self):
        import agfo_selfupdate as su
        import agfo_github_update as ghu
        self.su, self.ghu = su, ghu
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.tmp.name})
        self.env.start()
        self.data = b'MZ' + b'setup' * 1000
        self.rels = [{'tag_name': 'backupsync-v2.3.1', 'name': 'BackupSync 2.3.1', 'draft': False, 'prerelease': False, 'body': 'n',
                      'html_url': 'https://github.com/downtownck/agfo-windows-apps/releases/tag/backupsync-v2.3.1',
                      'assets': [{'name': 'AGFO-BackupSync-Setup.exe', 'size': len(self.data),
                                  'digest': 'sha256:' + hashlib.sha256(self.data).hexdigest(),
                                  'browser_download_url': 'https://github.com/downtownck/agfo-windows-apps/releases/download/backupsync-v2.3.1/AGFO-BackupSync-Setup.exe'}]},
                     {'tag_name': 'supertools-v9.0.0', 'draft': False, 'prerelease': False, 'assets': []}]

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _resp(self, data):
        import io

        class R(io.BytesIO):
            headers = {'Content-Length': str(len(data))}
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return R(data)

    def test_versions_consistent_everywhere(self):
        root = Path(__file__).resolve().parents[1]
        v = installer.VERSION
        self.assertEqual(net.VERSION, v)
        import agfo_drives
        self.assertEqual(agfo_drives.VERSION, v)
        for rel, needle in [('packaging/build_windows.ps1', "version = '%s'" % v), ('payload/AGFO-BackupSync-Core.ps1', "AgfoVersion = '%s'" % v),
                            ('payload/AGFO-BackupSync-GUI.ps1', 'AGFO BackupSync v%s' % v), ('payload/Create-AgfoShortcut.ps1', 'AGFO BackupSync v%s' % v),
                            ('Derle-ve-Kur.cmd', 'v%s' % v)]:
            self.assertIn(needle, (root / rel).read_text(encoding='utf-8-sig'), rel)

    def test_check_finds_update_and_asset(self):
        res = self.su.check(force=True, releases=self.rels)
        self.assertEqual(res['status'], 'update')
        self.assertEqual(res['version'], '2.3.1')
        self.assertEqual(res['asset']['name'], 'AGFO-BackupSync-Setup.exe')
        self.assertTrue(str(self.su.state_path()).startswith(self.tmp.name))

    def test_download_verifies_sha_and_cleans(self):
        res = self.su.check(force=True, releases=self.rels)
        with patch.object(self.ghu, '_open', lambda url, **k: self._resp(self.data)):
            path = self.su.download_setup(res)
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(path.name, 'AGFO-BackupSync-Setup-2.3.1.exe')
        with patch.object(self.ghu, '_open', lambda url, **k: self._resp(self.data[:-3] + b'xyz')):
            path.unlink()
            with self.assertRaises(self.ghu.GHUpdateError):
                self.su.download_setup(res)
        self.assertFalse(path.exists())
        self.assertFalse(list(path.parent.glob('*.part')))

    def test_launch_setup_uses_runas_update(self):
        calls = []
        self.su.launch_setup(Path(self.tmp.name) / 'S.exe', shell_execute=lambda *a: calls.append(a) or 42)
        self.assertEqual(calls[0][1:4], ('runas', str(Path(self.tmp.name) / 'S.exe'), '--update'))
        with self.assertRaises(OSError):
            self.su.launch_setup(Path('x.exe'), shell_execute=lambda *a: 5)   # UAC reddi / hata

    def test_installed_mode_only_for_installed_frozen_exe(self):
        exe = str(installer.INSTALL_DIR / installer.APP_EXE)
        with patch.object(Path, 'resolve', lambda self: self):
            self.assertTrue(self.su.installed_mode(exe, frozen=True))
            self.assertFalse(self.su.installed_mode(exe, frozen=False))
            self.assertFalse(self.su.installed_mode(r'D:\Downloads\AGFO-BackupSync.exe', frozen=True))

    def test_run_update_waits_for_lock_then_relaunches(self):
        calls, slept, relaunched = [], [], []

        def fake_install(desktop, autostart, on_step):
            calls.append((desktop, autostart))
            if len(calls) < 3:
                raise PermissionError('AGFO-BackupSync.exe kilitli. Bildirim alanindaki AGFO uygulamasini kapatip tekrar kurun.')
        result = installer.run_update(install_fn=fake_install, detect_fn=lambda: (False, True), relaunch_fn=lambda: relaunched.append(1),
                                      sleep=slept.append, delay=0.5)
        self.assertEqual(result, (False, True))
        self.assertEqual(calls, [(False, True)] * 3)      # mevcut tercihler korunur
        self.assertEqual(slept, [0.5, 0.5])
        self.assertEqual(relaunched, [1])

    def test_run_update_does_not_retry_admin_error_and_does_not_relaunch(self):
        relaunched = []

        def no_admin(*a):
            raise PermissionError('C:\\agfo-backutil kurulumu icin Windows yonetici izni gerekir.')
        with self.assertRaises(PermissionError):
            installer.run_update(install_fn=no_admin, detect_fn=lambda: (True, True), relaunch_fn=lambda: relaunched.append(1), sleep=lambda s: None)
        self.assertEqual(relaunched, [])

    def test_run_update_gives_up_after_retries(self):
        def locked(*a):
            raise PermissionError('dosya kilitli')
        with self.assertRaises(PermissionError):
            installer.run_update(install_fn=locked, detect_fn=lambda: (True, False), relaunch_fn=lambda: None, retries=3, sleep=lambda s: None)

    def test_tray_menu_has_update_items(self):
        src = (Path(__file__).resolve().parents[1] / 'src' / 'agfo_tray.py').read_text(encoding='utf-8')
        self.assertIn("'Guncellemeleri denetle'", src)
        self.assertIn('visible=lambda item: bool(upd[\'result\'])', src)
        self.assertIn('icon.stop()          # exe kilidini birak', src)

    def test_build_includes_update_modules(self):
        script = (Path(__file__).resolve().parents[1] / 'packaging' / 'build_windows.ps1').read_text(encoding='utf-8-sig')
        for mod in ('agfo_selfupdate', 'agfo_github_update', 'agfo_installer'):
            self.assertIn('--hidden-import ' + mod, script)
