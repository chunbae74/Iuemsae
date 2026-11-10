import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
import sys
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from host_secrets import SecretStore, PRIVATE_FILES


spec = importlib.util.spec_from_file_location('server_start', Path(__file__).resolve().parents[1] / 'start.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ServerStartTest(unittest.TestCase):
    def test_checks_model_and_selects_gpu_only_when_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / 'stt/models/ieumsae_stt.pt'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'model-fixture')
            tls = root / 'secrets/tls'
            tls.mkdir(parents=True)
            (tls / 'server.pem').write_bytes(b'fixture')
            store = SecretStore(root / 'secrets')
            store.save({name: b'fixture' for name in PRIVATE_FILES})
            (root / 'secrets/jwt_p256.pub.pem').write_bytes(b'fixture')
            configuration = {
                'services': {'stt': {'environment': {'STT_MODEL_SHA256': hashlib.sha256(model.read_bytes()).hexdigest()}}},
            }

            def result(command, **kwargs):
                output = json.dumps(configuration).encode() if 'config' in command else b'version'
                return subprocess.CompletedProcess(command, 0, output, b'')

            with patch.object(launcher, 'ROOT', root), patch.object(launcher.subprocess, 'run', side_effect=result):
                cpu = launcher.prepare('docker')
                gpu = launcher.prepare('docker', gpu=True)
                self.assertNotIn(str(root / 'docker-compose.gpu.yml'), cpu)
                self.assertIn(str(root / 'docker-compose.gpu.yml'), gpu)
                model.write_bytes(b'changed-model')
                with self.assertRaisesRegex(ValueError, 'MODEL_INTEGRITY_FAILED'):
                    launcher.prepare('docker')
                values = store.load()
                values.pop('smtp_password.txt')
                store.save(values)
                with self.assertRaisesRegex(ValueError, 'SECRET_FILES_REQUIRED'):
                    launcher.prepare('docker')

    def test_compose_error_is_not_exposed(self):
        response = subprocess.CompletedProcess([], 1, b'', b'private-configuration-value')
        with patch.object(launcher.subprocess, 'run', return_value=response):
            with self.assertRaisesRegex(ValueError, '^COMPOSE_CONFIGURATION_REQUIRED$'):
                launcher.prepare('docker')

    def test_memory_keeper_precedes_stdin_projection_and_failed_projection_stops_launch(self):
        for projection_status in (0, 1):
            commands = []
            def execute(command, **kwargs):
                commands.append((command, kwargs))
                status = projection_status if 'run' in command else 0
                return subprocess.CompletedProcess(command, status, b'', b'private-error')
            with patch.object(sys, 'argv', ['start']), patch.object(launcher.shutil, 'which', return_value='docker'), patch.object(launcher, 'prepare', return_value=['docker', 'compose']), patch.object(launcher, 'SecretStore') as store, patch.object(launcher.subprocess, 'run', side_effect=execute), redirect_stdout(io.StringIO()) as output:
                store.return_value.runtime_payload.return_value = b'private-payload'
                self.assertEqual(launcher.main(), projection_status)
                self.assertIn('build', commands[0][0])
                self.assertIn('secret-memory', commands[1][0])
                self.assertIn('secret-loader', commands[2][0])
                self.assertEqual(commands[2][1]['input'], b'private-payload')
                self.assertEqual(len(commands), 4 if projection_status == 0 else 3)
                self.assertNotIn('private-', output.getvalue())
                for command, kwargs in commands:
                    self.assertNotIn('private-payload', ' '.join(command))
                    self.assertNotIn('env', kwargs)


if __name__ == '__main__':
    unittest.main()
