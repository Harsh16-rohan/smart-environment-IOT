"""Simulated IoT devices: sensors (publishers) and actuators (subscribers)."""
import math
import random
import threading
import time


class Sensor(threading.Thread):
    """Publishes a reading every `interval` seconds to sensors/<room>/<kind>."""

    RANGES = {  # (base, amplitude, noise)
        "temperature": (28.0, 6.0, 0.4),   # deg C
        "humidity": (55.0, 15.0, 1.0),     # %
        "air_quality": (120.0, 80.0, 6.0), # ppm (gas level)
        "motion": (0.0, 1.0, 0.0),         # 0/1
    }

    def __init__(self, broker, room, kind, interval=1.0, device=None):
        super().__init__(daemon=True)
        self.broker, self.room, self.kind = broker, room, kind
        self.interval = interval
        self.device_id = f"{room}-{kind}"
        self.device = device  # shared state so actuators can influence readings
        self._t = random.random() * 100
        self._halt = threading.Event()

    def read(self):
        base, amp, noise = self.RANGES[self.kind]
        self._t += 0.05
        if self.kind == "motion":
            return 1 if random.random() < 0.15 else 0
        v = base + amp * math.sin(self._t) + random.gauss(0, noise)
        if self.device:  # cooling/ventilation actually lowers the value
            if self.kind == "temperature" and self.device.get("fan"):
                v -= 4
            if self.kind == "air_quality" and self.device.get("vent"):
                v -= 60
        if random.random() < 0.01:  # occasional faulty spike to test validation
            v *= 10
        return round(v, 2)

    def run(self):
        while not self._halt.is_set():
            self.broker.publish(
                f"sensors/{self.room}/{self.kind}",
                {"device": self.device_id, "value": self.read(), "ts": time.time()},
            )
            time.sleep(self.interval)

    def stop(self):
        self._halt.set()


class Actuator(threading.Thread):
    """Listens on actuators/<room>/<name>/set and changes its state."""

    def __init__(self, broker, room, name, state):
        super().__init__(daemon=True)
        self.room, self.name, self.state = room, name, state
        self.broker = broker
        self.q = broker.subscribe(f"actuators/{room}/{name}/set")

    def run(self):
        while True:
            _, payload = self.q.get()
            self.state[self.name] = bool(payload["on"])
            self.broker.publish(
                f"actuators/{self.room}/{self.name}/status",
                {"on": self.state[self.name], "ts": time.time(), "reason": payload.get("reason", "")},
            )
