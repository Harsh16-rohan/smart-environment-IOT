# Smart Environment Monitoring & Control System (IoT)

A semester project that applies **system design** principles to an IoT use case: monitor
temperature, humidity, air quality and motion in several rooms, automatically control a
fan and ventilation, raise alerts, store history and show everything on a live web dashboard.

Sensors are **simulated in software**, so it runs on any PC with no hardware.
Pure Python standard library, so there is nothing to `pip install`.

---

## 1. How to run in VS Code

1. Install **Python 3.9+** and VS Code with the **Python** extension.
2. `File > Open Folder...` and choose this folder (`smart_env_iot`).
3. Open the terminal (`` Ctrl+` ``) and run:
   ```
   python main.py
   ```
   (on Windows you can also use `py main.py`)
4. Open **http://127.0.0.1:8000** in your browser.
5. Stop with `Ctrl+C`.

Or press **F5** and choose *Run IoT System* (config in `.vscode/launch.json`).

Run the tests: `python -m unittest discover -s tests -v` (or F5 > *Run Tests*).

Options: `python main.py --port 8080 --interval 0.5`

---

## 2. Problem statement & requirements

**Functional**
- FR1: Collect readings from many sensors (temperature, humidity, air quality, motion).
- FR2: Reject faulty readings (out-of-range spikes).
- FR3: Automatically switch a fan (high temp) and ventilation (poor air) with hysteresis.
- FR4: Raise alerts (with cooldown so they don't spam).
- FR5: Store history; show live values, charts, alerts and actuator state.
- FR6: Let the user override actuators manually (On / Off / Auto).

**Non-functional**
| Quality | How the design addresses it |
|---|---|
| Scalability | Pub/sub decouples devices from consumers; topic scheme `sensors/<room>/<kind>` lets you add rooms/sensors with no code change. |
| Reliability | Bounded queues, invalid-data filtering, offline-device detection, SQLite persistence. |
| Low latency | In-memory messaging; control loop reacts within one sensor interval. |
| Extensibility | Each layer is a separate module behind a small interface (broker, storage). |
| Maintainability | One responsibility per module; unit + integration tests. |

---

## 3. Architecture (layered / event-driven)

```
 PERCEPTION LAYER            NETWORK/MESSAGING          EDGE / PROCESSING              APPLICATION
 ┌────────────────┐         ┌──────────────┐         ┌──────────────────┐        ┌──────────────────┐
 │ Sensors (x8)   │ publish │              │subscribe│ Gateway          │        │ REST API         │
 │ temp/hum/air/  │────────▶│   Message    │────────▶│ validate+smooth  │───────▶│ (http.server)    │
 │ motion         │ sensors/│   Broker     │sensors/#│ + store          │ SQLite │ /api/state ...   │
 └────────────────┘ r/kind  │  (pub/sub,   │         └────────┬─────────┘        └────────┬─────────┘
                            │   topics,    │       processed/ │                           │
 ┌────────────────┐ subscribe│   wildcards) │         ┌────────▼─────────┐        ┌────────▼─────────┐
 │ Actuators      │◀────────│              │◀────────│ Rule Engine      │◀───────│ Web Dashboard    │
 │ fan, vent      │actuators/│              │ command │ thresholds +     │ manual │ (HTML/JS, polls  │
 └────────────────┘ r/a/set └──────────────┘         │ hysteresis+alerts│override│  every 2 s)      │
                                                     └──────────────────┘        └──────────────────┘
                                   Storage: SQLite (readings, alerts, actuator_events)
```

### Components
| Module | Role |
|---|---|
| `iot/sensors.py` | `Sensor` threads publish readings; `Actuator` threads apply commands. Actuators feed back into sensors (fan on lowers temperature), so the control loop is realistic. |
| `iot/broker.py` | Topic-based pub/sub with MQTT-style `+` and `#` wildcards, bounded queues for back-pressure. |
| `iot/gateway.py` | Validation, moving-average smoothing, persistence, latest-state cache, offline detection. |
| `iot/rules.py` | Rule engine: thresholds with hysteresis, alert cooldown, manual override. |
| `iot/storage.py` | SQLite access layer (thread-safe). |
| `iot/server.py` + `dashboard.html` | REST API and live dashboard. |
| `main.py` | Composition root: wires everything together. |

### Data flow (example: room gets too hot)
1. `Sensor` publishes `sensors/room1/temperature {value: 33.1}`.
2. `Gateway` validates (within -20..80), smooths over last 5 values, writes to SQLite,
   republishes `processed/room1/temperature`.
3. `RuleEngine` sees the value is above 32, publishes `actuators/room1/fan/set {on:true}`
   and stores an alert.
4. `Actuator` turns the fan on and publishes `.../status`; the event is logged.
5. Temperature falls; when it drops below 29 (hysteresis) the fan turns off.
6. The dashboard shows all of this on its next poll.

### Topic design
| Topic | Direction | Payload |
|---|---|---|
| `sensors/<room>/<kind>` | device → system | `{device, value, ts}` |
| `processed/<room>/<kind>` | gateway → rules | `{value, ts}` |
| `actuators/<room>/<name>/set` | rules → device | `{on, reason}` |
| `actuators/<room>/<name>/status` | device → system | `{on, ts, reason}` |

### Database schema
```
readings(id, room, kind, device, value, ts)      INDEX(room, kind, ts)
alerts(id, room, rule, message, ts)
actuator_events(id, room, actuator, state, reason, ts)
```

### REST API
| Method & path | Purpose |
|---|---|
| `GET /` | Dashboard page |
| `GET /api/state` | Latest values, actuator states, offline devices, stats |
| `GET /api/history?room=room1&kind=temperature` | Last 60 readings |
| `GET /api/alerts` | Last 20 alerts |
| `POST /api/actuator` `{room, actuator, mode: on/off/auto}` | Manual override |

---

## 4. Key design decisions & trade-offs

| Decision | Why | Trade-off / alternative |
|---|---|---|
| Publish/subscribe instead of direct calls | Loose coupling, easy to add consumers | Needs a broker; messages can be lost (we use bounded queues; production would use MQTT QoS 1). |
| Edge gateway validates data | Bad data never reaches storage or rules | Adds a processing hop. |
| Hysteresis (ON at 32, OFF at 29) | Prevents the fan flickering around the threshold | Slightly slower to switch off. |
| SQLite | Zero setup, fine for a single node | Doesn't scale to many writers; use TimescaleDB/InfluxDB in production. |
| Polling dashboard | Simple, works anywhere | WebSockets/SSE would give lower latency. |
| Python stdlib only | Runs anywhere, no install | Flask/FastAPI would be cleaner for a bigger API. |

## 5. Scaling & security (discussion section for your report)

**Scaling path:** replace `broker.py` with **Mosquitto/MQTT** (same publish/subscribe API) →
run several gateway instances (one per building) → move storage to a time-series DB →
put the API behind a load balancer → cache latest state in Redis.

**Security:** TLS for MQTT/HTTP, per-device credentials/certificates, authentication on
`/api/actuator`, input validation (already done on POST), rate limiting, signed firmware updates.

**Reliability:** offline-device detection (no data for 10 s), bounded queues, watchdog/restart
of threads, retained "last known state" messages.

## 6. Testing
- `tests/test_system.py`: topic wildcard matching, pub/sub delivery, and an end-to-end test
  (data stored, state tracked, manual override reaches the actuator).
- Fault injection: sensors randomly emit 10x spikes; the dashboard's "rejected" counter shows
  the gateway filtering them.

## 7. Future work
Real hardware (ESP32 + DHT22 + MQ-135 publishing to Mosquitto), user accounts, mobile
notifications, anomaly detection / ML forecasting, OTA updates.

## 8. Demo script (for your presentation)
1. Start the system, open the dashboard.
2. Show live values and charts; point out the "rejected (faulty)" counter.
3. Wait for a fan/vent to switch on automatically; show the alert.
4. Click **Off** to override, then **Auto** to return control.
5. Walk through the architecture diagram and the trade-offs table.

## Project structure
```
smart_env_iot/
├── main.py              entry point
├── dashboard.html       web UI
├── iot/                 broker, sensors, gateway, rules, storage, server
├── tests/test_system.py
└── .vscode/launch.json  F5 run/debug configs
```
