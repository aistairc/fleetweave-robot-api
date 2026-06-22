import os

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1884))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "robotadmin")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "robotadmin")
MQTT_TOPIC = "robot/+/status"

# リロケーション対応ロボット設定
RELOCATION_SUPPORTED_ROBOTS = os.getenv("RELOCATION_SUPPORTED_ROBOTS", "robotA,robotB").split(",")
RELOCATION_SUPPORTED_ROBOTS = [robot.strip() for robot in RELOCATION_SUPPORTED_ROBOTS if robot.strip()]

# Zenoh設定
ZENOH_HOST = os.getenv("ZENOH_HOST", "localhost")
ZENOH_PORT = int(os.getenv("ZENOH_PORT", 7447))
ZENOH_CONFIG = {
    "connect/endpoints": [f"tcp/{ZENOH_HOST}:{ZENOH_PORT}"]
}
# エリア別マップ名設定
AREA_MAP_NAMES = {
    "buildingB": {
        "area": "area_a",
        "map_name": "buildingB"
    },
    "road": {
        "area": "area_intermediate",
        "map_name": "road"
    },
    "buildingA": {
        "area": "area_c",
        "map_name": "buildingA"
    },
    "maintenance": {
        "area": "maintenance",
        "map_name": "buildingA"
    }
}
# エリア別IPアクセス制限設定
AREA_IP_RESTRICTIONS = {
    "area_a": {
        "allowed_ips": [
            "192.168.1.100",  # FMS-A
            "192.168.1.101",  # FMS-Aバックアップ
            "127.0.0.1",      # ローカルテスト用
            "::1"             # IPv6 localhost
        ],
        "description": "FMS-Aアクセス許可エリア"
    },
    "area_intermediate": {
        "allowed_ips": [
            "192.168.2.100",  # FMS-B
            "192.168.2.101",  # FMS-Bバックアップ
            "127.0.0.1",      # ローカルテスト用
            "::1"
        ],
        "description": "FMS-Bアクセス許可エリア"
    },
    "area_c": {
        "allowed_ips": [
            "192.168.3.100",  # FMS-C
            "192.168.3.101",  # FMS-Cバックアップ
            "127.0.0.1",      # ローカルテスト用
            "::1"
        ],
        "description": "FMS-Cアクセス許可エリア"
    },
    "maintenance": {
        "allowed_ips": [
            "192.168.1.100",  # FMS-A
            "192.168.2.100",  # FMS-B
            "192.168.3.100",  # FMS-C
            "192.168.0.10",   # メンテナンス端末
            "127.0.0.1",
            "::1"
        ],
        "description": "メンテナンスモード・全FMSアクセス許可"
    }
}

# マップ名からエリアへのマッピング
MAP_TO_AREA_MAPPING = {
    "map_b": "area_a",
    "map_road": "area_intermediate",
    "map_a": "area_c",
    "map_default": "area_a",  # デフォルト
    "warehouse_a": "area_a",
    "warehouse_b": "area_intermediate",
    "warehouse_c": "area_c",
    "maintenance_area": "maintenance"
}

# ロボット位置からエリアを判定するための座標範囲設定
POSITION_TO_AREA_MAPPING = {
    "area_a": {
        "x_range": (-10.0, 50.0),
        "y_range": (-10.0, 50.0)
    },
    "area_intermediate": {
        "x_range": (45.0, 100.0),
        "y_range": (-10.0, 50.0)
    },
    "area_c": {
        "x_range": (95.0, 150.0),
        "y_range": (-10.0, 50.0)
    }
}
