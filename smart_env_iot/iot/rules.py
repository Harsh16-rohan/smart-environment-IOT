"""Rule engine: evaluates processed data, raises alerts and commands actuators.

Uses hysteresis (separate ON / OFF thresholds) so devices don't flicker.
"""
import threading
import time

RULES = [
    # (name, sensor kind, actuator, ON when value >, OFF when value <)
    ("high_temperature", "temperature", "fan", 32.0, 29.0),
    ("poor_air_quality", "air_quality", "vent", 180.0, 140.0),
]
ALERT_COOLDOWN = 15  # seconds between repeated alerts of the same kind


class RuleEngine(threading.Thread):
    def __init__(self, broker, storage):
        super().__init__(daemon=True)
        self.broker, self.storage = broker, storage
        self.q = broker.subscribe("processed/#")
        self.status_q = broker.subscribe("actuators/+/+/status")
        self.actuator_state = {}  # (room, actuator) -> bool
        self.last_alert = {}
        self.manual = {}          # (room, actuator) -> bool override from dashboard
        threading.Thread(target=self._log_status, daemon=True).start()

    def _log_status(self):
        while True:
            topic, p = self.status_q.get()
            _, room, name, _ = topic.split("/")
            self.actuator_state[(room, name)] = p["on"]
            self.storage.add_actuator_event(room, name, p["on"], p.get("reason", ""), p["ts"])

    def command(self, room, actuator, on, reason):
        self.broker.publish(f"actuators/{room}/{actuator}/set", {"on": on, "reason": reason})

    def run(self):
        while True:
            topic, p = self.q.get()
            _, room, kind = topic.split("/")
            v = p["value"]
            for name, k, act, hi, lo in RULES:
                if k != kind or (room, act) in self.manual:
                    continue
                on = self.actuator_state.get((room, act), False)
                if v > hi and not on:
                    self.command(room, act, True, f"{name}: {v} > {hi}")
                    self._alert(room, name, f"{kind} {v} above {hi} -> {act} ON")
                elif v < lo and on:
                    self.command(room, act, False, f"{name}: {v} < {lo}")
            if kind == "motion" and v == 1:
                self._alert(room, "motion", "Motion detected")

    def _alert(self, room, rule, msg):
        key = (room, rule)
        if time.time() - self.last_alert.get(key, 0) >= ALERT_COOLDOWN:
            self.last_alert[key] = time.time()
            self.storage.add_alert(room, rule, msg)

    def set_manual(self, room, actuator, on):
        """Dashboard override: manual=None returns control to automation."""
        if on is None:
            self.manual.pop((room, actuator), None)
        else:
            self.manual[(room, actuator)] = on
            self.command(room, actuator, on, "manual override")
