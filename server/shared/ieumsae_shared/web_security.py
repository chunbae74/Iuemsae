import asyncio
import logging

from starlette.responses import JSONResponse


class SecurityBoundary:
    def __init__(self, app, max_body_bytes=65536, body_timeout=10):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.body_timeout = body_timeout

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        started = False

        async def safe_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                headers = list(message.get('headers', []))
                headers = [(key, value) for key, value in headers if key.lower() not in (b'cache-control', b'x-content-type-options')]
                headers.extend([(b'cache-control', b'no-store'),
                                (b'x-content-type-options', b'nosniff')])
                message = {**message, 'headers': headers}
            await send(message)

        async def error(status, code):
            await JSONResponse({'error': code}, status_code=status)(scope, receive, safe_send)

        try:
            body = bytearray()
            async with asyncio.timeout(self.body_timeout):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    if len(body) + len(chunk) > self.max_body_bytes:
                        await error(413, 'request_too_large')
                        return
                    body.extend(chunk)
                    if not message.get('more_body', False):
                        break

            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            await self.app(scope, buffered_receive, safe_send)
        except TimeoutError:
            if not started:
                await error(408, 'request_timeout')
        except Exception:
            logging.getLogger('ieumsae.security').error('REQUEST_FAILED')
            if not started:
                await error(500, 'internal_error')
