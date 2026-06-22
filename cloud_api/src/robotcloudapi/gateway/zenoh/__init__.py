"""
Zenoh Gateway モジュール

このモジュールはZenohプロトコルを使用してロボットとの通信を行うためのゲートウェイ機能を提供します。

主要コンポーネント:
- session: Zenohセッション管理
- subscribe: ロボットステータスのサブスクリプション
- publisher: ロボットコマンドのパブリッシュ
- main: ゲートウェイのメイン実行機能

使用例:
    # Zenohゲートウェイを起動
    from robotcloudapi.gateway.zenoh.main import run_zenoh_gateway
    await run_zenoh_gateway()
    
    # 個別の機能を使用
    from robotcloudapi.gateway.zenoh import get_zenoh_publisher, start_zenoh_robot_monitoring
    
    # パブリッシャーを取得してコマンド送信
    publisher = get_zenoh_publisher()
    publisher.send_navigation_command("robot1", "auto", "map1", [])
    
    # ロボット監視を開始
    start_zenoh_robot_monitoring()
"""

from .sesstion import (
    ZenohSession,
    get_zenoh_session,
    initialize_zenoh_session,
    cleanup_zenoh_session
)

from .subscribe import (
    ZenohSubscriber,
    get_zenoh_subscriber,
    start_zenoh_robot_monitoring,
    start_zenoh_response_monitoring,
    stop_zenoh_robot_monitoring
)

from .publisher import (
    ZenohPublisher,
    get_zenoh_publisher
)

from .main import (
    ZenohGateway,
    run_zenoh_gateway
)

__all__ = [
    # Session
    "ZenohSession",
    "get_zenoh_session", 
    "initialize_zenoh_session",
    "cleanup_zenoh_session",
    
    # Subscriber
    "ZenohSubscriber",
    "get_zenoh_subscriber",
    "start_zenoh_robot_monitoring",
    "start_zenoh_response_monitoring",
    "stop_zenoh_robot_monitoring",
    
    # Publisher
    "ZenohPublisher", 
    "get_zenoh_publisher",
    
    # Gateway
    "ZenohGateway",
    "run_zenoh_gateway"
]