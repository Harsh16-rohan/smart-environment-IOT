"""SQLite persistence layer (thread-safe via a single lock + one connection)."""
import sqlite3
import threading
import time


class Storage:
    def __init__(self, path="iot_data.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS readings(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT, kind TEXT, device TEXT, value REAL, ts REAL);
                CREATE INDEX IF NOT EXISTS idx_readings ON readings(room, kind, ts);
                CREATE TABLE IF NOT EXISTS alerts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT, rule TEXT, message TEXT, ts REAL);
                CREATE TABLE IF NOT EXISTS actuator_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT, actuator TEXT, state INTEGER, reason TEXT, ts REAL);
                """
            )

    def add_reading(self, room, kind, device, value, ts):
        with self.lock:
            self.db.execute("INSERT INTO readings(room,kind,device,value,ts) VALUES(?,?,?,?,?)",
                            (room, kind, device, value, ts))
            self.db.commit()

    def add_alert(self, room, rule, message):
        with self.lock:
            self.db.execute("INSERT INTO alerts(room,rule,message,ts) VALUES(?,?,?,?)",
                            (room, rule, message, time.time()))
            self.db.commit()

    def add_actuator_event(self, room, actuator, state, reason, ts):
        with self.lock:
            self.db.execute("INSERT INTO actuator_events(room,actuator,state,reason,ts) VALUES(?,?,?,?,?)",
                            (room, actuator, int(state), reason, ts))
            self.db.commit()

    def history(self, room, kind, limit=60):
        with self.lock:
            rows = self.db.execute(
                "SELECT ts, value FROM readings WHERE room=? AND kind=? ORDER BY ts DESC LIMIT ?",
                (room, kind, limit)).fetchall()
        return [{"ts": r[0], "value": r[1]} for r in reversed(rows)]

    def recent_alerts(self, limit=20):
        with self.lock:
            rows = self.db.execute(
                "SELECT room, rule, message, ts FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"room": r[0], "rule": r[1], "message": r[2], "ts": r[3]} for r in rows]

    def stats(self):
        with self.lock:
            return {
                "readings": self.db.execute("SELECT COUNT(*) FROM readings").fetchone()[0],
                "alerts": self.db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
            }
