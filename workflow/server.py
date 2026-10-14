"""Loopback-only HTTP interface. Browser never submits shell commands."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .store import Store, Conflict

ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/style.css': ('style.css', 'text/css')}
WEB_ACTIONS = {'node', 'comment', 'followup', 'read'}


def make_server(store, port):
    class Handler(BaseHTTPRequestHandler):
        def host_ok(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def send(self, code, body, mime='application/json'):
            if mime == 'application/json':
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.host_ok():
                return self.send(403, {'error': 'unexpected Host'})
            path = urlparse(self.path).path
            if path == '/api/state':
                return self.send(200, store.read())
            if path in ASSETS:
                name, mime = ASSETS[path]
                return self.send(200, (Path(__file__).parent / 'static' / name).read_bytes(), mime)
            self.send(404, {'error': 'not found'})

        def do_POST(self):
            if not self.host_ok():
                return self.send(403, {'error': 'unexpected Host'})
            origin = self.headers.get('Origin')
            if origin != 'http://' + self.headers['Host']:
                return self.send(403, {'error': 'same-origin browser request required; use CLI for automation'})
            if self.path != '/api/action':
                return self.send(404, {'error': 'not found'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'application/json required'})
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 < size <= 262144:
                    return self.send(413, {'error': 'request body too large or missing'})
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict) or request.get('action') not in WEB_ACTIONS:
                    raise ValueError('action not available from browser')
                if type(request.get('revision')) is not int:
                    raise ValueError('current revision required')
                self.send(200, store.change(request['action'], request.get('data'), revision=request['revision']))
            except Conflict as exc:
                self.send(409, {'error': str(exc)})
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, {'error': str(exc)})

        def log_message(self, *_args):
            pass
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(directory, port):
    store = Store(directory)
    store.read()
    server = make_server(store, port)
    print(f'Workflow: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
