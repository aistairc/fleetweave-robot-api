# fleetweave-robot-api

Robot API component of FleetWeave — a Robot/Area-separated Fleet Management System (FMS) architecture for managing small mobile robots operating across urban environments.

This module implements the Robot Cloud API and Robot Client API described in the following paper:

> Yoko Sasaki, Duyhinh Nguyen, Hiroki Ikeuchi, Takashi Miki,
> "A Robot/Area-Separated Fleet Management Architecture for Mobile Robots Operating in Urban Environments,"
> Proc. ROBOMECH 2026.

## Overview

```
         Job Management System
                  │
     FMS(Area)    │    FMS(Robot)
           │      │      │
           └──────┴──────┘
                  │  REST API
         Robot Cloud API  ◄── cloud_api/
                  │
            Redis Streams
                  │
              Gateway
                  │  MQTT / Zenoh
         Robot Client API  ◄── client_api/
                  │  ROS2 topics
              Robot
```

The **Robot Cloud API** (`cloud_api/`) runs in the cloud and manages robot reservation, navigation commands, and status via Redis and MQTT.

The **Robot Client API** (`client_api/`) runs on-robot as a ROS2 workspace. It bridges the robot's ROS2 navigation topics to MQTT so the cloud can communicate with the robot over the network.

## Repository Structure

```
fleetweave-robot-api/
├── cloud_api/          # FastAPI server (Python, uv)
│   ├── pyproject.toml
│   └── src/
│       └── robotcloudapi/
│           ├── api/            # REST API endpoints
│           ├── gateway/        # MQTT / Zenoh gateway
│           ├── infra/          # Redis client
│           ├── domain/         # Domain models
│           └── settings.py     # Configuration
└── client_api/         # ROS2 workspace
    ├── bash/           # Startup scripts
    ├── service/        # systemd service files
    ├── solid_params.aws.yaml   # MQTT bridge config
    └── src/
        ├── custom_msgs/        # ROS2 message definitions
        ├── py_launch/          # Launch file
        ├── robot_cmd/          # Navigation command nodes
        └── robot_status/       # Status publisher node
```

## Quick Start

See each component's README for setup and usage:

- [cloud_api/README.md](cloud_api/README.md) — Robot Cloud API
- [client_api/README.md](client_api/README.md) — Robot Client API

## Related Repositories

- [fleetweave-job-manager](https://github.com/aistairc/fleetweave-job-manager) — Job Management System
- [fleetweave-area-fms](https://github.com/aistairc/fleetweave-area-fms) — FMS(Area) based on Open-RMF
