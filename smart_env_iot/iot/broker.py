"""Lightweight in-process publish/subscribe message broker (MQTT-style topics).

Topics look like 'sensors/room1/temperature'. Subscribers may use wildcards:
  '+'  matches exactly one level   (sensors/+/temperature)
  '#'  matches all remaining levels (sensors/#)

In a real deployment this module is replaced by an MQTT broker (e.g. Mosquitto);
the publish()/subscribe() interface is deliberately the same.
"""
import queue
import threading


def topic_matches(pattern: str, topic: str) -> bool:
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t):
            return False
        if part != "+" and part != t[i]:
            return False
    return len(p) == len(t)


class Broker:
    def __init__(self):
        self._subs = []  # (pattern, queue)
        self._lock = threading.Lock()

    def subscribe(self, pattern: str) -> "queue.Queue":
        q = queue.Queue(maxsize=1000)  # bounded queue = back-pressure
        with self._lock:
            self._subs.append((pattern, q))
        return q

    def publish(self, topic: str, payload: dict) -> None:
        with self._lock:
            targets = [q for pat, q in self._subs if topic_matches(pat, topic)]
        for q in targets:
            try:
                q.put_nowait((topic, payload))
            except queue.Full:
                pass  # drop message if consumer is too slow
