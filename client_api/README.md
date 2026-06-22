# Robot Client API

Robot Client API is the on-robot ROS2 workspace for FleetWeave — a Robot/Area-separated Fleet Management System (FMS) architecture.

This module implements the Robot Client API described in the following paper:

> Yoko Sasaki, Duyhinh Nguyen, Hiroki Ikeuchi, Takashi Miki,
> "A Robot/Area-Separated Fleet Management Architecture for Mobile Robots Operating in Urban Environments,"
> Proc. ROBOMECH 2026.

## Overview

The Robot Client API runs on the robot and bridges ROS2 topics to MQTT, enabling the Robot Cloud API to send navigation commands and receive status updates over the network.

```
Robot Cloud API  (cloud)
      │  MQTT
Robot Client API  (on robot, this module)
      │  ROS2 topics
Robot navigation stack
```

## Requirements

- Ubuntu 22.04
- ROS2 Humble
- MQTT broker (e.g., Mosquitto) or AWS IoT Core
- CycloneDDS

## Installation

### ROS2

Follow the official instructions: https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html

```bash
sudo rosdep init
rosdep update
```

### Additional apt packages

```bash
sudo apt install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-pip \
    git \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-geographic-msgs \
    ros-humble-tf-transformations \
    mosquitto mosquitto-clients
```

### Python packages

```bash
pip install paho-mqtt  # version 2.0.0 or later
```

### CycloneDDS

Copy the config file to your home directory and edit it:

```bash
cp cyclonedds.xml ~/
```

- Line 6: Set the network interface name (wired or wireless)
- Line 22: Replace `{USER}` with your username

Add to `.bashrc`:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/<user>/cyclonedds.xml
```

Set the ROS domain ID in the terminal before running (do not add to `.bashrc`):

```bash
export ROS_DOMAIN_ID=<your DDS domain ID>
```

## Build

From the workspace root:

```bash
colcon build --symlink-install
source install/setup.bash
```

## Running

### Using systemd (recommended for production)

Copy scripts to system locations:

```bash
sudo cp bash/robot_client.sh /usr/local/bin/
sudo cp bash/mqttbridge.sh /usr/local/bin/
sudo cp service/robot_client_api.service /etc/systemd/system/
sudo cp service/ros_mqtt_bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable robot_client_api
sudo systemctl start robot_client_api
```

Before doing so, edit `bash/robot_client.sh` and `bash/mqttbridge.sh` to replace `<user>` and `<workspace>` with your actual paths.

### Manual

```bash
# Terminal 1: Robot Client API nodes
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=<your DDS domain ID>
source install/setup.bash
ros2 launch py_launch robot_client_api_launch.py

# Terminal 2: MQTT bridge (for AWS IoT Core)
ros2 launch mqtt_client standalone.launch.xml \
    params_file:=$(ros2 pkg prefix mqtt_client)/share/mqtt_client/config/robot_params.aws.yaml
```

## AWS IoT Core Configuration

Edit `robot_params.aws.yaml`:

1. Set `host` to your AWS IoT endpoint (`aws iot describe-endpoint --endpoint-type iot:Data-ATS`)
2. Set certificate paths (`ca_certificate`, `certificate`, `key`) to your AWS IoT credentials
3. The MQTT topic prefix `robotA` identifies this robot — change it to match the robot name configured in the Robot Cloud API

For local MQTT instead of AWS IoT, see `ros-mqtt_bridge.md`.

## Repository Structure

```
client_api/
├── bash/
│   ├── robot_client.sh         # Startup script for Client API nodes
│   └── mqttbridge.sh           # Startup script for MQTT bridge
├── cyclonedds.xml              # CycloneDDS network configuration
├── ros-mqtt_bridge.md          # Instructions for local MQTT bridge setup
├── service/
│   ├── robot_client_api.service    # systemd service for Client API
│   └── ros_mqtt_bridge.service     # systemd service for MQTT bridge
├── robot_params.aws.yaml       # MQTT bridge config (AWS IoT Core)
└── src/
    ├── custom_msgs/            # Custom ROS2 message/action/service definitions
    ├── py_launch/              # ROS2 launch file
    ├── robot_cmd/              # ROS2 nodes: navigation command subscribers
    ├── robot_status/           # ROS2 nodes: robot status publisher
    └── test_system/            # System integration tests
```

## Related Repositories

- [fleetweave-job-manager](https://github.com/aistairc/fleetweave-job-manager) — Job Management System
- [fleetweave-area-fms](https://github.com/aistairc/fleetweave-area-fms) — FMS(Area) based on Open-RMF
- [fleetweave-robot-api](https://github.com/aistairc/fleetweave-robot-api) — this repository (Robot Cloud API + Client API)
