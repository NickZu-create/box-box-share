"""Start the local synthetic preview independently of a terminal session."""
import argparse
import functools
import hashlib
import http.client
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'output' / 'design-preview'
ROUTE = '/hans/buddy/2/'
IDENTITY = hashlib.sha256(os.path.normcase(str(DIST.resolve())).encode()).hexdigest()[:24]


def ready(port):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
    try:
        connection.request('GET', ROUTE)
        response = connection.getresponse()
        body = response.read(65536)
        return (response.status == 200 and response.getheader('X-BoxBox-Preview') == IDENTITY
                and b'Box Box Share' in body and b'group-demo' in body)
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8012)
    parser.add_argument('--open', action='store_true', help='Open the preview in your browser')
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    if not (DIST / ROUTE.strip('/') / 'index.html').is_file():
        parser.error('Preview files are missing. Follow COLLABORATION.md to rebuild them.')
    if args.serve:
        class PreviewHandler(SimpleHTTPRequestHandler):
            def end_headers(self):
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-BoxBox-Preview', IDENTITY)
                super().end_headers()

        handler = functools.partial(PreviewHandler, directory=str(DIST))
        with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
            server.serve_forever()
        return
    url = f'http://127.0.0.1:{args.port}{ROUTE}'
    if not ready(args.port):
        if listening(args.port):
            parser.error(f'Port {args.port} is used by another service. Use --port with a free port.')
        runtime = ROOT / 'backups' / 'preview-runtime'
        runtime.mkdir(parents=True, exist_ok=True)
        options = {'start_new_session': True} if os.name != 'nt' else {
            'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        }
        with (runtime / f'preview-{args.port}.log').open('ab') as log:
            child = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), '--serve', '--port', str(args.port)],
                cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                close_fds=True, **options,
            )
        (runtime / f'preview-{args.port}.pid').write_text(str(child.pid), encoding='ascii')
        for _ in range(40):
            if ready(args.port):
                break
            if child.poll() is not None:
                parser.error(f'Preview stopped. Check backups/preview-runtime/preview-{args.port}.log.')
            time.sleep(0.1)
        else:
            parser.error('Preview did not start. Check backups/preview-runtime/.')
    print(f'Preview ready: {url}')
    print('This address works on this computer only. Run this helper again after restarting Windows.')
    if args.open:
        webbrowser.open(url)


if __name__ == '__main__':
    main()
