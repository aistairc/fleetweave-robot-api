from launch_ros.substitutions import FindPackageShare
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution, TextSubstitution
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    loglevel = 'info'

    arg_param_1 = DeclareLaunchArgument(
        'loglevel',
        default_value='info',
        description='Logging level'
    )
    loglevel = LaunchConfiguration('loglevel')

    robot_status = Node(
        package='robot_status',
        executable='robot_status',
        name='robot_status',
        parameters=[{
            'loglevel': loglevel
        }]
    )

    cmd_change_map = Node(
        package='robot_cmd',
        executable='change_map',
        name='change_map',
        parameters=[{
            'loglevel': loglevel
        }]
    )

    cmd_clear_route = Node(
        package='robot_cmd',
        executable='clear_route',
        name='clear_route',
        parameters=[{
            'loglevel': loglevel
        }]
    )

    cmd_init_pose = Node(
        package='robot_cmd',
        executable='init_pose',
        name='init_pose',
        parameters=[{
            'loglevel': loglevel
        }]
    )

    cmd_move_2d = Node(
        package='robot_cmd',
        executable='move_2d',
        name='move_2d',
        parameters=[{
            'loglevel': loglevel
        }]
    )

    cmd_plan_2d = Node(
        package='robot_cmd',
        executable='plan_2d',
        name='plan_2d',
        parameters=[{
            'loglevel': loglevel
        }]
    )


    return LaunchDescription([
        arg_param_1,
        robot_status,
        cmd_change_map,
        cmd_clear_route,
        cmd_init_pose,
        cmd_move_2d,
        cmd_plan_2d,
    ])