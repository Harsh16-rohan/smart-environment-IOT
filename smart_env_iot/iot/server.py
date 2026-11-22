"""REST API + dashboard server (Python standard library only)."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))


def make_handler(gateway, storage, rules, rooms, actuator_states):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200, ctype="application/json"):
            body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "..", "dashboard.html"), "rb") as f:
                    return self._send(f.read(), ctype="text/html")
            if u.path == "/api/state":
                snap = gateway.snapshot()
                snap["actuators"] = {r: dict(s) for r, s in actuator_states.items()}
                snap["manual"] = [f"{r}/{a}" for (r, a) in rules.manual]
                snap["stats"] = storage.stats()
                return self._send(snap)
            if u.path == "/api/history":
                room = q.get("room", [rooms[0]])[0]
                kind = q.get("kind", ["temperature"])[0]
                return self._send(storage.history(room, kind))
            if u.path == "/api/alerts":
                return self._send(storage.recent_alerts())
            self._send({"error": "not found"}, 404)

        def do_POST(self):
            # POST /api/actuator  {"room":"room1","actuator":"fan","mode":"on|off|auto"}
            if urlparse(self.path).path != "/api/actuator":
                return self._send({"error": "not found"}, 404)
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n))
                assert d["room"] in rooms and d["actuator"] in ("fan", "vent")
                mode = {"on": True, "off": False, "auto": None}[d["mode"]]
            except Exception:
                return self._send({"error": "bad request"}, 400)
            rules.set_manual(d["room"], d["actuator"], mode)
            self._send({"ok": True})

    return Handler


def run_server(gateway, storage, rules, rooms, actuator_states, port=8000):
    srv = ThreadingHTTPServer(("127.0.0.1", port),
                              make_handler(gateway, storage, rules, rooms, actuator_states))
    print(f"Dashboard: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    srv.serve_forever()
