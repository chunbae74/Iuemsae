import asyncio
import io
import logging
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
sys.path.insert(0, str(ROOT / 'stt'))

from ieumsae_shared.runtime import SafeFormatter
from ieumsae_shared.web_security import SecurityBoundary


class BoundaryTest(unittest.TestCase):
    def test_internal_error_does_not_escape_or_disclose(self):
        app = FastAPI()

        @app.get('/failure')
        async def fail():
            raise ValueError('private-password database-host local-path')

        app.add_middleware(SecurityBoundary)
        with TestClient(app) as client:
            with self.assertLogs('ieumsae.security', level='ERROR') as events:
                response = client.get('/failure')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'error': 'internal_error'})
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(events.output, ['ERROR:ieumsae.security:REQUEST_FAILED'])

    def test_logging_drops_arguments_tracebacks_and_untrusted_messages(self):
        marker = 'private-password database-host local-path'
        try:
            raise RuntimeError(marker)
        except RuntimeError:
            record = logging.LogRecord('httpx', logging.ERROR, marker, 1, '%s', (marker,), sys.exc_info())
        self.assertEqual(SafeFormatter().format(record), 'ERROR SERVICE_EVENT')

    def test_oversized_body_is_rejected_before_handler(self):
        app = FastAPI()

        @app.post('/body')
        async def body(request: Request):
            self.fail('handler must not run')

        app.add_middleware(SecurityBoundary, max_body_bytes=16)
        with TestClient(app) as client:
            response = client.post('/body', content=b'x' * 17)
        self.assertEqual(response.status_code, 413)

    def test_slow_body_is_rejected(self):
        async def run():
            async def app(scope, receive, send):
                self.fail('handler must not run')

            async def receive():
                await asyncio.sleep(1)

            messages = []

            async def send(message):
                messages.append(message)

            await SecurityBoundary(app, body_timeout=0.01)({'type': 'http'}, receive, send)
            self.assertEqual(messages[0]['status'], 408)

        asyncio.run(run())

    def test_startup_failure_has_no_configuration_or_traceback(self):
        import os
        import subprocess
        environment = os.environ.copy()
        environment.pop("AUTH_DATABASE_URL", None)
        environment["PYTHONPATH"] = os.pathsep.join(str(ROOT / part) for part in ("shared", "auth"))
        result = subprocess.run([sys.executable, "-m", "ieumsae_shared.runtime", "auth"],
                                env=environment, cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), "ERROR STARTUP_FAILED")
        self.assertEqual(result.stdout, "")

    def test_archive_limits_reject_nested_and_expanding_inputs(self):
        import importlib.util
        import tempfile
        import zipfile
        spec = importlib.util.spec_from_file_location("export_model", ROOT / "stt/tools/export_model.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("kosr/checkpoint/best_wer.pth", b"x" * 100000)
        with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(data) as archive:
            with self.assertRaises(ValueError):
                module._find_in_zip(archive, Path(directory))
            with self.assertRaises(ValueError):
                module._find_in_zip(archive, Path(directory), depth=3)

    def test_invalid_pcm_rejected_before_inference(self):
        from ieumsae_stt.asr.recognizer import Recognizer
        recognizer = Recognizer.__new__(Recognizer)
        for audio in (b'x', b'x' * (16000 * 2 * 30 + 2), None):
            with self.assertRaises(ValueError):
                recognizer.transcribe_pcm16(audio)

    def test_sessions_are_isolated_and_capacity_is_bounded(self):
        from fastapi import HTTPException
        from ieumsae_stt.sessions import SessionStore
        store = SessionStore(90, 1)
        session = store.create('user-a', 'device-a', 'translate')
        self.assertIsNone(store.get(session.session_id, 'user-b', 'device-a'))
        self.assertIsNone(store.get(session.session_id, 'user-a', 'device-b'))
        with self.assertRaises(HTTPException):
            store.create('user-a', 'device-a', 'translate')
        self.assertIs(store.get(session.session_id, 'user-a', 'device-a'), session)
        store.wipe_all()


if __name__ == '__main__':
    unittest.main()
