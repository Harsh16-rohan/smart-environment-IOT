"""Edge gateway: validates sensor data, smooths it, stores it, tracks latest state,
and republishes clean data on 'processed/...' topics for the rule engine."""
import threading
import time
from collections import defaultdict, deque

VALID = {  # physically plausible ranges -> anything outside is a sensor fault
    "temperature": (-20, 80),
    "humidity": (0, 100),
    "air_quality": (0, 1000),
    "motion": (0, 1),
}


class Gateway(threading.Thread):
    def __init__(self, broker, storage, window=5):
        super().__init__(daemon=True)
        self.broker, self.storage = broker, storage
        self.q = broker.subscribe("sensors/#")
        self.window = window
        self.buffers = defaultdict(lambda: deque(maxlen=window))
        self.latest = {}          # (room, kind) -> {value, ts}
        self.last_seen = {}       # device -> ts  (for offline detection)
        self.rejected = 0
        self.lock = threading.Lock()

    def run(self):
        while True:
            topic, p = self.q.get()
            _, room, kind = topic.split("/")
            lo, hi = VALID.get(kind, (float("-inf"), float("inf")))
            if not (lo <= p["value"] <= hi):
                self.rejected += 1
                continue  # drop invalid reading
            buf = self.buffers[(room, kind)]
            buf.append(p["value"])
            smooth = round(sum(buf) / len(buf), 2) if kind != "motion" else p["value"]
            self.storage.add_reading(room, kind, p["device"], smooth, p["ts"])
            with self.lock:
                self.latest[(room, kind)] = {"value": smooth, "ts": p["ts"]}
                self.last_seen[p["device"]] = time.time()
            self.broker.publish(f"processed/{room}/{kind}", {"value": smooth, "ts": p["ts"]})

    def snapshot(self):
        with self.lock:
            out = defaultdict(dict)
            for (room, kind), v in self.latest.items():
                out[room][kind] = v["value"]
            offline = [d for d, t in self.last_seen.items() if time.time() - t > 10]
            return {"rooms": out, "offline_devices": offline, "rejected": self.rejected}
