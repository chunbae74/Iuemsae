import asyncio
import ssl

import httpx
from fastapi import HTTPException

from .config import settings


class AuthorizationClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            verify=ssl.create_default_context(cafile=settings.auth_ca_file),
            timeout=5,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )

    async def close(self):
        await self.client.aclose()

    async def check(self, token, user_id, device_id):
        try:
            async with asyncio.timeout(10):
                async with self.client.stream(
                    'GET', str(settings.auth_status_url),
                    headers={'Authorization': 'Bearer ' + token},
                ) as response:
                    if response.status_code in (401, 403):
                        raise HTTPException(401, 'invalid_token')
                    if response.status_code != 200:
                        raise HTTPException(503, 'authorization_unavailable')
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > 4096:
                            raise HTTPException(503, 'authorization_unavailable')
                        body.extend(chunk)
                    import json
                    data = json.loads(body)
                    if not isinstance(data, dict) or data.get('active') is not True:
                        raise HTTPException(401, 'invalid_token')
                    if data.get('userId') != user_id or data.get('deviceId') != device_id:
                        raise HTTPException(401, 'invalid_token')
                    return data.get('ttsConsent') is True
        except (httpx.HTTPError, ValueError, TimeoutError):
            raise HTTPException(503, 'authorization_unavailable') from None
