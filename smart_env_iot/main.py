"""Entry point: wires all layers together and starts the system."""
import argparse

from iot.broker import Broker
from iot.gateway import Gateway
from iot.rules import RuleEngine
from iot.sensors import Actuator, Sensor
from iot.server import run_server
from iot.storage import Storage

ROOMS = ["room1", "room2"]
KINDS = ["temperature", "humidity", "air_quality", "motion"]


def build(db_path="iot_data.db", interval=1.0):
    broker = Broker()
    storage = Storage(db_path)
    gateway = Gateway(broker, storage)
    rules = RuleEngine(broker, storage)
    states = {r: {"fan": False, "vent": False} for r in ROOMS}
    threads = [gateway, rules]
    for r in ROOMS:
        for a in ("fan", "vent"):
            threads.append(Actuator(broker, r, a, states[r]))
        for k in KINDS:
            threads.append(Sensor(broker, r, k, interval, device=states[r]))
    for t in threads:
        t.start()
    return broker, storage, gateway, rules, states


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--interval", type=float, default=1.0, help="sensor publish interval (s)")
    args = ap.parse_args()
    _, storage, gateway, rules, states = build(interval=args.interval)
    try:
        run_server(gateway, storage, rules, ROOMS, states, args.port)
    except KeyboardInterrupt:
        print("\nStopped.")
