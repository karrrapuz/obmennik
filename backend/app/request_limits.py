"""Bound small API bodies before JSON validation; market ingest has its own limit."""
from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, limit=65536):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}
                or not scope['path'].startswith('/api/')
                or scope['path'] == '/api/internal/market/snapshots'):
            return await self.app(scope, receive, send)

        async def reject(status, detail):
            await JSONResponse({'detail': detail}, status_code=status)(scope, receive, send)

        headers = dict(scope.get('headers', []))
        if headers.get(b'content-encoding', b'identity').lower() != b'identity':
            return await reject(415, 'Compressed request bodies are not accepted')
        declared = headers.get(b'content-length')
        if declared is not None:
            if not declared.isdigit() or len(declared) > 10:
                return await reject(400, 'Invalid content length')
            if int(declared) > self.limit:
                return await reject(413, 'Request exceeds size limit')
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > self.limit:
                return await reject(413, 'Request exceeds size limit')
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        pending = True

        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)
