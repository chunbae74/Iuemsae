import asyncio
import json
import re
import time

import httpx
from cryptography import x509

from ieumsae_shared.b64 import b64d
from .attestation import AttestationError


class RevocationChecker:
    def __init__(self):
        self.entries = frozenset()
        self.expires = 0
        self.lock = asyncio.Lock()

    async def check(self, chain):
        async with self.lock:
            if time.monotonic() >= self.expires:
                try:
                    async with asyncio.timeout(15):
                        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                            async with client.stream('GET', 'https://android.googleapis.com/attestation/status') as response:
                                response.raise_for_status()
                                body = bytearray()
                                async for chunk in response.aiter_bytes():
                                    if len(body) + len(chunk) > 2 * 1024 * 1024:
                                        raise ValueError()
                                    body.extend(chunk)
                                entries = json.loads(body)['entries']
                                if not isinstance(entries, dict) or any(not re.fullmatch('[0-9a-f]+', key) for key in entries):
                                    raise ValueError()
                                maximum_age = re.search(r'max-age=(\d+)', response.headers.get('cache-control', ''))
                                ttl = min(int(maximum_age[1]), 3600) if maximum_age else 60
                                self.entries = frozenset(entries)
                                self.expires = time.monotonic() + ttl
                except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
                    raise AttestationError('revocation_unavailable') from None
        for encoded in chain:
            certificate = x509.load_der_x509_certificate(b64d(encoded, max_len=8192))
            if format(certificate.serial_number, 'x') in self.entries:
                raise AttestationError('certificate_revoked')


checker = RevocationChecker()
