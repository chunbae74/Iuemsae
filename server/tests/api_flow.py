import json
import os
import secrets
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pyhpke import KEMKey


ROOT = Path(__file__).resolve().parents[1]


def verify_api_flow(test):
    sys.path.insert(0, str(ROOT / 'stt'))
    with patch.dict(os.environ, {
        'STT_AUTH_STATUS_URL': 'https://auth.example.invalid/auth/session/status',
        'STT_MODEL_SHA256': '0' * 64,
        'STT_SIGNING_KEY_ID': 'test',
        'STT_SIGNING_KEY_NOT_AFTER': str(int(time.time() * 1000) + 60000),
        'STT_ELEVENLABS_MODEL_ID': 'test',
        'STT_ELEVENLABS_VOICE_ID': 'testvoice',
    }):
        from ieumsae_stt import main as stt, tts
    from ieumsae_stt.asr.recognizer import Recognizer
    from ieumsae_stt.authorization import AuthorizationClient
    from ieumsae_stt.sessions import SessionStore
    from ieumsae_stt.crypto import (
        HPKE_SUITE, hpke_info, TTS_HPKE_INFO_PREFIX,
        aes_encrypt, aes_decrypt, chunk_aad, result_aad, tts_audio_aad, ServerSigner,
    )
    from ieumsae_shared.b64 import b64d, b64e
    from ieumsae_shared.device_sig import canonical
    from ieumsae_shared.tokens import AccessTokenVerifier
    from ieumsae_auth.main import app as auth_app
    from ieumsae_auth.db import SessionLocal
    from ieumsae_auth.models import User, Device
    from ieumsae_auth.security import hash_password
    from ieumsae_auth import sessions, profile
    import torch
    torch.set_num_threads(2)

    async def run():
        device_key = ec.generate_private_key(ec.SECP256R1())
        public = b64e(device_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        async with SessionLocal() as db:
            user = User(login_id='u' + secrets.token_hex(5), email=secrets.token_hex(5) + '@example.com',
                        password_hash=hash_password(secrets.token_hex(24)), password_changed_at=sessions.now())
            db.add(user)
            await db.flush()
            device = Device(user_id=user.id, public_key=public, security_level='TEE', sdk_int=35)
            db.add(device)
            await db.flush()
            await profile.record_consent(db, user.id, tts_overseas=True)
            await db.flush()
            tokens = await sessions.start(db, user.id, device)
            await db.commit()
            device_id = str(device.id)
        key = serialization.load_pem_private_key((Path(test.temp.name) / 'jwt.pem').read_bytes(), None)
        current = stt.State()
        current.verifier = AccessTokenVerifier(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        current.signer = ServerSigner(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
                                      'test', int(time.time() * 1000) + 60000)
        current.sessions = SessionStore(90, 3)
        current.recognizer = Recognizer((ROOT / 'stt/models/ieumsae_stt.pt').read_bytes(), 'cpu')
        current.authorization = AuthorizationClient()
        await current.authorization.close()
        current.authorization.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=auth_app))
        audio_fixture = b'ID3' + secrets.token_bytes(64)
        current.synth = AsyncMock()
        current.synth.synthesize.return_value = (audio_fixture, 'audio/mpeg')
        token = tokens['accessToken']

        def seal(session, data, info):
            public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64d(session['hpkePublicKey']))
            enc, context = HPKE_SUITE.create_sender_context(KEMKey.from_pyca_cryptography_key(public_key), info=info)
            return {'enc': b64e(enc), 'ciphertext': b64e(context.seal(data))}

        try:
            with patch.object(stt, 'state', current), patch.object(tts, 'provider', return_value='elevenlabs'):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stt.app), base_url='https://test.invalid') as client:
                    async def signed(method, path, body=None):
                        raw = json.dumps(body, separators=(',', ':')).encode() if body is not None else b''
                        stamp = str(int(time.time() * 1000))
                        nonce = secrets.token_urlsafe(24)
                        signature = device_key.sign(canonical(method, path, stamp, nonce, raw), ec.ECDSA(hashes.SHA256()))
                        return await client.request(method, path, content=raw, headers={
                            'Authorization': 'Bearer ' + token, 'X-Device-Id': device_id,
                            'X-Timestamp': stamp, 'X-Nonce': nonce, 'X-Signature': b64e(signature),
                            'Content-Type': 'application/json',
                        })

                    test.assertEqual((await client.get('/system/keys')).status_code, 200)
                    response = await signed('POST', '/stt/session', {'mode': 'translate'})
                    test.assertEqual(response.status_code, 200, response.text)
                    session = response.json()
                    sid = session['sessionId']
                    session_key = secrets.token_bytes(32)
                    response = await signed('POST', f'/stt/session/{sid}/key', seal(session, session_key, hpke_info(sid)))
                    test.assertEqual(response.status_code, 204, response.text)
                    import numpy as np
                    pcm = np.zeros(16000, dtype='<i2')
                    pcm[8000:] = (3000 * np.sin(np.arange(8000) * 0.1)).astype('<i2')
                    timestamp = int(time.time() * 1000)
                    iv, ciphertext = aes_encrypt(session_key, pcm.tobytes(), chunk_aad(sid, 0, timestamp))
                    response = await signed('POST', f'/stt/session/{sid}/chunk', {'seq': 0, 'timestamp': timestamp, 'iv': b64e(iv), 'ciphertext': b64e(ciphertext)})
                    test.assertEqual(response.status_code, 200, response.text)
                    response = await signed('POST', f'/stt/session/{sid}/finalize', {'lastSeq': 0})
                    test.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    plain = json.loads(aes_decrypt(session_key, b64d(result['iv']), b64d(result['ciphertext']), result_aad(sid)))
                    test.assertIsInstance(plain['text'], str)
                    test.assertIsNone(current.sessions.get(sid, str(user.id), device_id))

                    response = await signed('POST', '/tts/session')
                    test.assertEqual(response.status_code, 200, response.text)
                    session = response.json()
                    sid = session['sessionId']
                    payload = json.dumps({'key': b64e(session_key), 'text': 'test', 'emotion': 'happy'}).encode()
                    request = seal(session, payload, TTS_HPKE_INFO_PREFIX + sid.encode())
                    response = await signed('POST', f'/tts/session/{sid}/speak', request)
                    test.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    test.assertEqual(aes_decrypt(session_key, b64d(result['iv']), b64d(result['ciphertext']), tts_audio_aad(sid)), audio_fixture)
                    test.assertEqual((await signed('POST', f'/tts/session/{sid}/speak', request)).status_code, 404)

                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=auth_app), base_url='https://auth.example.invalid') as auth:
                        headers = {'Authorization': 'Bearer ' + token}
                        response = await auth.put('/user/communication', headers=headers, json={'comprehensionLevel': 2, 'showToListener': True, 'consent': True})
                        test.assertEqual(response.status_code, 204)
                        response = await auth.get('/user/profile', headers=headers)
                        test.assertEqual(response.json()['communication']['comprehensionLevel'], 2)
                        test.assertEqual((await auth.delete('/user/communication', headers=headers)).status_code, 204)
                        test.assertEqual((await auth.put('/user/consents/tts', headers=headers, json={'agree': False})).status_code, 204)
                        test.assertEqual((await signed('POST', '/tts/session')).status_code, 403)
                        test.assertEqual((await auth.post('/auth/logout', json={'refreshToken': tokens['refreshToken']})).status_code, 204)
                        test.assertEqual((await signed('POST', '/stt/session', {'mode': 'translate'})).status_code, 401)
        finally:
            await current.authorization.close()
            current.sessions.wipe_all()

    test.client.portal.call(run)
