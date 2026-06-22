# ROS-MQTT のBridgeのやり方

## 何を使うか？
ドイツの大学が使っているオープンソースがあるのでそれを使います。
https://github.com/ika-rwth-aachen/mqtt_client

## インストール前必須事項
- ROS2 
- MQTT Broker

## 使用するライブラリ(READMEで実施済みなら不要)
```
$sudo apt install python3-colcon-common-extensions python3-rosdep python3-pip cmake git
```

## ビルド
新規でROSWorkSpaceを作るところから
```
$cd
$mkdir -p ros-mqtt-bridge/src
$cd ros-mqtt-bridge/src
$git clone https://github.com/ika-rwth-aachen/mqtt_client.git
$cd mqtt_client/mqtt_client
$rosdep install -r --ignore-src --from-paths .
$cd ~/ros-mqtt-bridge/
$colcon build --packages-up-to mqtt_client --cmake-args -DCMAKE_BUILD_TYPE=Release
$source install/setup.bash
```

## 起動用のファイル
robot_params.aws.yaml を ros-mqtt-bridge/src/mqtt_client/mqtt_client/config 　配下に置いてビルド



## 起動コマンド
```
$ros2 launch mqtt_client standalone.launch.xml params_file:=$(ros2 pkg prefix mqtt_client)/share/mqtt_client/config/robot_params.aws.yaml
```