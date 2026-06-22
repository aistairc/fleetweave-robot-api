from setuptools import find_packages, setup

package_name = 'test_system'

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
            'test_move_2d = test_system.test_move_2d:main',
            'test_plan_2d = test_system.test_plan_2d:main',
            'test_init_status = test_system.test_init_status:main',
            'test_clear_route = test_system.test_clear_route:main',
            'test_change_map = test_system.test_change_map:main',
            'test_init_pose = test_system.test_init_pose:main',
            'test_state_1shot = test_system.test_state_1shot:main',
        ],
    },
)
