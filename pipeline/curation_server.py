from __future__ import annotations

import hmac
import json
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from pipeline.curation import CurationError, CurationStore

MAX_REQUEST_BYTES = 64 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


class CurationApplication:
    def __init__(self, store: CurationStore, token: str | None = None) -> None:
        self.store = store
        self.token = token or secrets.token_urlsafe(32)

    def candidates(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self.store.list_candidates(
            query=_first(query, "q", ""),
            confidence=_first(query, "confidence", "all"),
            status=_first(query, "status", "pending"),
            offset=_integer(query, "offset", 0),
            limit=_integer(query, "limit", 50),
        )

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.decide(
            str(payload.get("candidate_id") or ""),
            str(payload.get("action") or ""),
            canonical_entity_id=payload.get("canonical_entity_id"),
            confirmed=payload.get("confirmed") is True,
            note=str(payload.get("note") or ""),
        )


def serve_curation(
    candidates_path: Path,
    decisions_path: Path,
    *,
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    if not candidates_path.is_file():
        raise SystemExit(
            f"No existe {candidates_path}. Ejecutá primero: uv run accesos identity-candidates"
        )
    store = CurationStore(candidates_path, decisions_path)
    application = CurationApplication(store)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), _handler(application))
    except OSError as error:
        raise SystemExit(f"No se pudo abrir 127.0.0.1:{port}: {error}") from error
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Curación local disponible en {url}")
    print("Las decisiones se guardan en", decisions_path)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCuración local finalizada.")
    finally:
        server.server_close()


def _handler(application: CurationApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "IdentityCuration/1.0"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/config":
                self._json(
                    HTTPStatus.OK,
                    {"token": application.token, "summary": application.store.summary()},
                )
                return
            if parsed.path == "/api/candidates":
                self._json(HTTPStatus.OK, application.candidates(parse_qs(parsed.query)))
                return
            self._static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/decision":
                self._json(HTTPStatus.NOT_FOUND, {"error": "Ruta inexistente."})
                return
            supplied = self.headers.get("X-Curation-Token", "")
            if not hmac.compare_digest(supplied, application.token):
                self._json(HTTPStatus.FORBIDDEN, {"error": "Token local inválido."})
                return
            try:
                payload = self._read_json()
                self._json(HTTPStatus.OK, {"candidate": application.decide(payload)})
            except CurationError as error:
                self._json(
                    error.status,
                    {"error": str(error), "code": error.code, "details": error.details},
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "El cuerpo JSON no es válido."})

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Tamaño inválido")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Se esperaba un objeto")
            return value

        def _static(self, request_path: str) -> None:
            relative = "curation.html" if request_path in {"", "/"} else request_path.lstrip("/")
            path = PurePosixPath(relative)
            if path.is_absolute() or ".." in path.parts:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            resource = files("pipeline.curation_ui").joinpath("static", *path.parts)
            if not resource.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = CONTENT_TYPES.get(Path(relative).suffix, "application/octet-stream")
            payload = resource.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _first(query: dict[str, list[str]], key: str, default: str) -> str:
    return query.get(key, [default])[0]


def _integer(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(_first(query, key, str(default)))
    except ValueError:
        return default
