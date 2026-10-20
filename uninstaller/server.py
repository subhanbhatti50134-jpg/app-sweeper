"""Local HTTP server for the premium web UI (stdlib only)."""

import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from uninstaller import __version__
from uninstaller.backends import get_available_backends, get_backend
from uninstaller.core.cleaner import Cleaner
from uninstaller.core.scanner import LeftoverScanner
from uninstaller.core.uninstaller import Uninstaller
from uninstaller.utils.helpers import human_size

WEBUI_DIR = Path(__file__).resolve().parent / "webui"

# Cache installed-package lists (rpm/dnf queries are slow on big systems)
_PKG_CACHE: Dict[str, Any] = {"ts": 0.0, "data": {}}
_PKG_CACHE_TTL = 120  # seconds


def _packages_cached() -> Dict[str, list]:
    """Return {backend_name: [InstalledPackage, ...]}, refreshing when stale."""
    now = time.time()
    if now - _PKG_CACHE["ts"] > _PKG_CACHE_TTL or not _PKG_CACHE["data"]:
        data: Dict[str, list] = {}
        for b in get_available_backends():
            try:
                data[b.name] = b.list_packages(include_orphans=False)
            except Exception:
                data[b.name] = []
        _PKG_CACHE["data"] = data
        _PKG_CACHE["ts"] = now
    return _PKG_CACHE["data"]


def _invalidate_pkg_cache() -> None:
    _PKG_CACHE["ts"] = 0.0


class ApiError(Exception):
    pass


# ======================================================================
# API handlers (all return JSON-serialisable dicts)
# ======================================================================
def api_status(_params: Dict, _body: Dict) -> Dict:
    managers = [{"name": b.name, "display_name": b.display_name}
                for b in get_available_backends()]
    return {"version": __version__, "managers": managers}


def api_packages(params: Dict, _body: Dict) -> Dict:
    q = (params.get("q") or [""])[0].lower()
    mgr = (params.get("manager") or [""])[0]
    pkgs = []
    for mgr_name, items in _packages_cached().items():
        if mgr and mgr_name != mgr:
            continue
        for p in items:
            if q and q not in p.name.lower() and \
                    q not in (p.description or "").lower():
                continue
            pkgs.append({
                "name": p.name, "version": p.version, "size": p.size,
                "size_h": p.display_size() if p.size else "",
                "manager": p.manager,
                "desc": (p.description or "")[:120],
            })
    pkgs.sort(key=lambda p: p["name"].lower())
    return {"packages": pkgs, "count": len(pkgs)}


def api_leftovers(params: Dict, _body: Dict) -> Dict:
    name = (params.get("name") or [""])[0]
    if not name:
        raise ApiError("missing 'name' parameter")
    items = LeftoverScanner().scan_for_app(name)
    total = sum(i.size for i in items)
    return {
        "items": [{"path": i.path, "size": i.size, "size_h": i.display_size(),
                   "kind": i.kind} for i in items],
        "total": total, "total_h": human_size(total), "count": len(items),
    }


def api_uninstall(_params: Dict, body: Dict) -> Dict:
    name = body.get("name")
    manager = body.get("manager")
    clean = bool(body.get("clean", True))
    if not name or not manager:
        raise ApiError("missing 'name' or 'manager'")
    # Scan leftovers first (before uninstall)
    leftovers = LeftoverScanner().scan_for_app(name)
    un = Uninstaller(backend_name=manager, force=True, clean_leftovers=clean)
    result = un.uninstall(name, leftovers=leftovers)
    if result.success:
        _invalidate_pkg_cache()
    return {
        "success": result.success, "message": result.message,
        "freed": result.leftovers_bytes,
        "freed_h": human_size(result.leftovers_bytes),
        "cleaned": len(result.leftovers_removed),
    }


def api_orphans(_params: Dict, _body: Dict) -> Dict:
    results = LeftoverScanner().scan_all_leftovers()
    apps = []
    total = 0
    for name, items in sorted(results.items(),
                              key=lambda kv: sum(i.size for i in kv[1]),
                              reverse=True):
        size = sum(i.size for i in items)
        total += size
        apps.append({
            "name": name, "size": size, "size_h": human_size(size),
            "items": [{"path": i.path, "size_h": i.display_size(),
                       "kind": i.kind} for i in items],
        })
    return {"apps": apps, "total": total, "total_h": human_size(total)}


def api_clean_orphans(_params: Dict, body: Dict) -> Dict:
    names = body.get("names") or []
    if not names:
        raise ApiError("missing 'names'")
    scanner = LeftoverScanner()
    items = []
    for n in names:
        items.extend(scanner.scan_for_app(n))
    c = Cleaner(dry_run=False, force=True)
    removed, freed, errors = c.remove_items(items, ask=False)
    return {"removed": removed, "freed": freed, "freed_h": human_size(freed),
            "errors": errors[:10]}


def api_clean_sizes(_params: Dict, _body: Dict) -> Dict:
    home = Path.home()
    import time
    now = time.time()

    def dir_size(p: Path) -> int:
        if not p.exists():
            return 0
        total = 0
        try:
            if p.is_file():
                return p.stat().st_size
            for f in p.rglob("*"):
                try:
                    if f.is_file() and not f.is_symlink():
                        total += f.stat().st_size
                except OSError:
                    pass
        except OSError:
            pass
        return total

    cache = dir_size(home / ".cache")
    trash = dir_size(home / ".local/share/Trash" / "files")
    temp = 0
    for d in (Path("/tmp"), home / ".cache"):
        try:
            for e in d.iterdir():
                try:
                    if now - e.stat().st_mtime > 3600:
                        temp += dir_size(e)
                except OSError:
                    pass
        except OSError:
            pass
    return {
        "cache": {"bytes": cache, "h": human_size(cache)},
        "trash": {"bytes": trash, "h": human_size(trash)},
        "temp": {"bytes": temp, "h": human_size(temp)},
    }


def api_clean(_params: Dict, body: Dict) -> Dict:
    kind = body.get("kind")
    c = Cleaner(dry_run=False, force=True)
    if kind == "cache":
        removed, freed, errors = c.clean_cache(ask=False)
    elif kind == "trash":
        removed, freed, errors = c.empty_trash(ask=False)
    elif kind == "temp":
        removed, freed, errors = c.clean_temp(ask=False)
    elif kind == "syscache":
        from uninstaller.cli import _clean_system_caches
        _clean_system_caches(False)
        removed, freed, errors = 0, 0, []
    else:
        raise ApiError(f"unknown kind: {kind}")
    return {"removed": removed, "freed": freed, "freed_h": human_size(freed),
            "errors": errors[:10]}


ROUTES: Dict[str, Callable] = {
    "/api/status": api_status,
    "/api/packages": api_packages,
    "/api/leftovers": api_leftovers,
    "/api/orphans": api_orphans,
    "/api/clean-sizes": api_clean_sizes,
}
POST_ROUTES: Dict[str, Callable] = {
    "/api/uninstall": api_uninstall,
    "/api/clean-orphans": api_clean_orphans,
    "/api/clean": api_clean,
}


# ======================================================================
# HTTP handler
# ======================================================================
class Handler(BaseHTTPRequestHandler):
    server_version = "LinUninstall/" + __version__

    def log_message(self, fmt: str, *args: Any) -> None:  # silence logs
        pass

    def _send_json(self, data: Dict, status: int = 200) -> None:
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ROUTES:
            params = parse_qs(parsed.query)
            try:
                self._send_json(ROUTES[path](params, {}))
            except ApiError as e:
                self._send_error_json(str(e))
            except Exception as e:  # noqa: BLE001
                self._send_error_json(f"{type(e).__name__}: {e}", 500)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in POST_ROUTES:
            self._send_error_json("not found", 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw or b"{}")
            self._send_json(POST_ROUTES[path]({}, body))
        except ApiError as e:
            self._send_error_json(str(e))
        except json.JSONDecodeError:
            self._send_error_json("invalid JSON body")
        except Exception as e:  # noqa: BLE001
            self._send_error_json(f"{type(e).__name__}: {e}", 500)

    def _serve_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        # Resolve safely inside webui dir
        target = (WEBUI_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEBUI_DIR.resolve())) or \
                not target.is_file():
            self._send_error_json("not found", 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


# ======================================================================
# Server lifecycle
# ======================================================================
class WebServer:
    """Background web server bound to 127.0.0.1 on a random port."""

    def __init__(self) -> None:
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> str:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
