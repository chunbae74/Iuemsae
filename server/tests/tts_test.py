import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stt'))


class TtsSecurityTest(unittest.TestCase):
    def test_audio_response_validation_and_limits(self):
        with patch.dict(os.environ, {
            'STT_AUTH_STATUS_URL': 'https://auth.example.invalid/auth/session/status',
            'STT_MODEL_SHA256': '0' * 64,
            'STT_SIGNING_KEY_ID': 'test',
            'STT_SIGNING_KEY_NOT_AFTER': '1',
            'STT_ELEVENLABS_MODEL_ID': 'test',
            'STT_ELEVENLABS_VOICE_ID': 'testvoice',
        }):
            from ieumsae_stt import tts

        async def run():
            for status, mime, data, accepted in (
                (200, 'audio/mpeg', b'audio', True),
                (200, 'text/html', b'private-provider-error', False),
                (200, 'audio/mpeg', b'', False),
                (200, 'audio/mpeg', b'x' * (5 * 1024 * 1024 + 1), False),
                (500, 'application/json', b'private-provider-error', False),
            ):
                synth = tts.Synthesizer()
                await synth.close()
                synth._client = httpx.AsyncClient(
                    base_url='https://api.elevenlabs.io',
                    transport=httpx.MockTransport(lambda request: httpx.Response(status, headers={'content-type': mime}, content=data)),
                )
                try:
                    with patch.object(tts, 'provider', return_value='elevenlabs'), patch.object(tts, '_api_key', return_value='test'):
                        if accepted:
                            self.assertEqual(await synth.synthesize('test', 'happy'), (data, 'audio/mpeg'))
                        else:
                            with self.assertRaises(tts.TtsFailed):
                                await synth.synthesize('test', 'happy')
                finally:
                    await synth.close()

        asyncio.run(run())


    def test_authorization_fails_closed_and_checks_identity(self):
        with patch.dict(os.environ, {
            'STT_AUTH_STATUS_URL': 'https://auth.example.invalid/auth/session/status',
            'STT_MODEL_SHA256': '0' * 64, 'STT_SIGNING_KEY_ID': 'test',
            'STT_SIGNING_KEY_NOT_AFTER': '1', 'STT_ELEVENLABS_MODEL_ID': 'test',
            'STT_ELEVENLABS_VOICE_ID': 'testvoice',
        }):
            from ieumsae_stt.authorization import AuthorizationClient
        from fastapi import HTTPException

        async def run():
            for status, payload, expected in (
                (200, {'active': True, 'userId': 'a', 'deviceId': 'b', 'ttsConsent': False}, False),
                (200, {'active': True, 'userId': 'a', 'deviceId': 'b', 'ttsConsent': True}, True),
                (200, {'active': True, 'userId': 'other', 'deviceId': 'b'}, 401),
                (401, {}, 401), (503, {}, 503),
            ):
                client = AuthorizationClient()
                await client.close()
                client.client = httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, json=payload)))
                try:
                    if isinstance(expected, bool):
                        self.assertIs(await client.check('token', 'a', 'b'), expected)
                    else:
                        with self.assertRaises(HTTPException) as caught:
                            await client.check('token', 'a', 'b')
                        self.assertEqual(caught.exception.status_code, expected)
                finally:
                    await client.close()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
