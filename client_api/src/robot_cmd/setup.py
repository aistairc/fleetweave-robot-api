from setuptools import find_packages, setup

package_name = 'robot_cmd'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='maintainer@example.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'clear_route = robot_cmd.clear_route:main',
            'move_2d = robot_cmd.move_2d:main',
            'plan_2d = robot_cmd.plan_2d:main',
            'init_pose = robot_cmd.init_pose:main',
            'change_map = robot_cmd.change_map:main',
        ],
    },
)
