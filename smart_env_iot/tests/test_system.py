import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from iot.broker import Broker, topic_matches  # noqa: E402
from main import build  # noqa: E402


class TestBroker(unittest.TestCase):
    def test_wildcards(self):
        self.assertTrue(topic_matches("sensors/#", "sensors/room1/temperature"))
        self.assertTrue(topic_matches("sensors/+/temperature", "sensors/room1/temperature"))
        self.assertFalse(topic_matches("sensors/+/temperature", "sensors/room1/humidity"))

    def test_pubsub(self):
        b = Broker()
        q = b.subscribe("a/#")
        b.publish("a/b", {"x": 1})
        self.assertEqual(q.get(timeout=1)[1]["x"], 1)


class TestSystem(unittest.TestCase):
    def test_end_to_end(self):
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        _, storage, gateway, rules, states = build(db, interval=0.05)
        time.sleep(1.5)
        self.assertGreater(storage.stats()["readings"], 20)       # data stored
        self.assertIn("room1", gateway.snapshot()["rooms"])       # state tracked
        rules.set_manual("room1", "fan", True)                    # manual override
        time.sleep(0.3)
        self.assertTrue(states["room1"]["fan"])


if __name__ == "__main__":
    unittest.main()
