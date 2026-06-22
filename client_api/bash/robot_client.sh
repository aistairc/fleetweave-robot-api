#!/bin/bash

while true
do
    ping_result=$(ping -w 5 8.8.8.8 | grep '100% packet loss')
    date_result=$(date)
    if [[ -n $ping_result ]]; then
            echo "NG"
        else
            echo "OK"
            break
    fi
done

source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_HOME=/home/<user>/my_ros_home
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/<user>/cyclonedds.xml
export ROS_DOMAIN_ID=21
source /home/<user>/<workspace>/install/setup.bash
ros2 launch py_launch robot_client_api_launch.py
