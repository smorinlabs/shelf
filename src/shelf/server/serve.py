"""Hardened local HTTP server for a generated Shelf library."""

import json
import re
import socket
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def find_free_port(preferred: int) -> int:
    """Return the preferred loopback port when free, otherwise an ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
        except OSError:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as fallback:
                fallback.bind(("127.0.0.1", 0))
                return fallback.getsockname()[1]
    return preferred


class LibraryRequestHandler(SimpleHTTPRequestHandler):
    """Serve one library without allowing resolved paths to leave its root."""

    library_root = Path()
    _translated_target: Path | None = None

    def _resolve_url_path(self, url: str) -> Path | None:
        request_path = urllib.parse.urlsplit(url).path
        decoded_path = urllib.parse.unquote(request_path)
        relative_path = decoded_path.lstrip("/")

        try:
            target = (self.library_root / relative_path).resolve()
            target.relative_to(self.library_root)
        except (OSError, RuntimeError, ValueError):
            return None
        return target

    def translate_path(self, path: str) -> str:
        """Translate a URL to its already-validated path below the library root."""
        target = self._translated_target or self._resolve_url_path(path)
        if target is None:
            return str(self.library_root / ".shelf-forbidden-path")
        return str(target)

    def send_head(self):
        """Reject traversal before the standard handler opens or lists a path."""
        target = self._resolve_url_path(self.path)
        if target is None:
            self.send_error(403, "Path resolves outside the library root")
            return None

        self._translated_target = target
        try:
            return super().send_head()
        finally:
            self._translated_target = None

    def do_GET(self) -> None:
        """Serve the live index with response-only PAGE.root injection."""
        if urllib.parse.urlsplit(self.path).path != "/":
            super().do_GET()
            return

        index_path = self._resolve_url_path("/index.html")
        if index_path is None:
            self.send_error(403, "Path resolves outside the library root")
            return

        try:
            body = index_path.read_bytes()
        except OSError:
            self.send_error(404, "File not found")
            return

        escaped_root = json.dumps(str(self.library_root), ensure_ascii=True)
        escaped_root = (
            escaped_root.replace("&", r"\u0026").replace("<", r"\u003c").replace(">", r"\u003e")
        )
        escaped_root_bytes = escaped_root.encode()
        body, _ = re.subn(
            rb'"root"\s*:\s*""',
            lambda _: b'"root": ' + escaped_root_bytes,
            body,
            count=1,
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(root: Path, port: int) -> ThreadingHTTPServer:
    """Build a loopback-only threaded HTTP server rooted at the library."""
    resolved_root = root.resolve()

    class RootedLibraryRequestHandler(LibraryRequestHandler):
        pass

    RootedLibraryRequestHandler.library_root = resolved_root
    return ThreadingHTTPServer(("127.0.0.1", port), RootedLibraryRequestHandler)


def serve(root: Path, port: int) -> tuple[ThreadingHTTPServer, int]:
    """Start a daemon server thread and return the server and bound port."""
    selected_port = find_free_port(port)
    server = make_server(root, selected_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]
