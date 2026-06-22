# Robot Cloud API

Robot Cloud API is the cloud-side API server for FleetWeave — a Robot/Area-separated Fleet Management System (FMS) architecture.

This module implements the Robot Cloud API described in the following paper:

> Yoko Sasaki, Duyhinh Nguyen, Hiroki Ikeuchi, Takashi Miki,
> "A Robot/Area-Separated Fleet Management Architecture for Mobile Robots Operating in Urban Environments,"
> Proc. ROBOMECH 2026.

## Overview

The Robot Cloud API acts as the bridge between FMS instances (Area and Robot) and the physical robot. It exposes a REST API and manages robot state via Redis. Commands are forwarded to the robot over MQTT (or Zenoh) via a gateway process.

```
FMS(Area) / FMS(Robot) / Job Management System
              │  REST API
       Robot Cloud API  (this module)
              │
         Redis Streams
              │
           Gateway
              │  MQTT / Zenoh
       Robot Client API  (on robot)
              │
           Robot
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Redis
- MQTT broker (e.g., Mosquitto) — or Zenoh router

## Setup

```bash
# Install dependencies
uv sync

# Start Redis
sudo systemctl start redis-server

# Initialize Redis Streams for each robot
redis-cli XGROUP CREATE robot:commands:robotA gateway_group 0 MKSTREAM
redis-cli XGROUP CREATE robot:responses:robotA gateway_group 0 MKSTREAM
```

## Running

```bash
# Start the API server
uv run uvicorn robotcloudapi.api.main:app --host 0.0.0.0 --port 8045

# Start the MQTT gateway (separate terminal)
uv run gateway
```

## Configuration

Key environment variables (see `src/robotcloudapi/settings.py`):

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `MQTT_HOST` | `localhost` | MQTT broker host |
| `MQTT_PORT` | `1884` | MQTT broker port |
| `MQTT_USERNAME` | `robotadmin` | MQTT username |
| `MQTT_PASSWORD` | `robotadmin` | MQTT password |
| `RELOCATION_SUPPORTED_ROBOTS` | `robotA,robotB` | Comma-separated robot names that support relocation |

Area map names and IP restrictions are configured directly in `settings.py`.

## API Endpoints

The server exposes a REST API at `http://localhost:8045`. Key endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/robot_status` | GET | Get robot status |
| `/robot_battery` | GET | Get battery level |
| `/robots/available` | GET | List available robots |
| `/job/robot_reserve` | POST | Reserve a robot |
| `/job/robot_release` | POST | Release a robot |
| `/job/navigation_start` | POST | Start navigation |
| `/job/navigation_stop` | POST | Stop navigation |
| `/job/navigation_iscomplate` | GET | Check navigation completion |
| `/robot_map_change` | POST | Change robot map |
| `/job/area_change` | POST | Switch robot area (FMS connection) |

Interactive API documentation is available at `http://localhost:8045/docs`.

## Related Repositories

- [fleetweave-job-manager](https://github.com/aistairc/fleetweave-job-manager) — Job Management System
- [fleetweave-area-fms](https://github.com/aistairc/fleetweave-area-fms) — FMS(Area) based on Open-RMF
- [fleetweave-robot-api](https://github.com/aistairc/fleetweave-robot-api) — this repository (Robot Cloud API + Client API)
