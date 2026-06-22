from .mqtt.client import create_client
from .mqtt.subscribe import on_message
from .mqtt.publisher import mqtt_publisher
from ..settings import MQTT_TOPIC, RELOCATION_SUPPORTED_ROBOTS, AREA_MAP_NAMES
from ..common.logging import setup_logger, get_logger
from ..infra.redis.client import redis_streams_manager
import threading
import signal
import sys
import asyncio
import os

# Zenoh関連のインポート（オプショナル）
try:
    from .zenoh.main import ZenohGateway
    ZENOH_AVAILABLE = True
except ImportError:
    ZENOH_AVAILABLE = False

def main():
    # ログ設定
    logger = setup_logger("gateway")
    
    logger.info("🚀 Gateway starting...")
    
    # 環境変数で起動モードを制御
    enable_mqtt = os.getenv("ENABLE_MQTT", "true").lower() == "true"
    enable_zenoh = os.getenv("ENABLE_ZENOH", "false").lower() == "true"
    
    if not enable_mqtt and not enable_zenoh:
        logger.error("❌ Both MQTT and Zenoh are disabled. Enable at least one.")
        sys.exit(1)
    
    # MQTT起動
    mqtt_client = None
    if enable_mqtt:
        logger.info("📡 Creating MQTT client...")
        mqtt_client = create_client(on_message)
    
        # 監視対象のロボット名リスト
        robot_names = ["robotA"]  # TODO: 設定ファイルから読み取り
        
        # 各ロボットのステータスとレスポンストピックを購読
        for robot_name in robot_names:
            # ロボットステータス購読
            status_topic = f"{robot_name}/robotStatus"
            mqtt_client.subscribe(status_topic)
            logger.info(f"📋 MQTT: Subscribing to status topic: {status_topic}")
            
            # 各種レスポンストピック購読
            response_topics = [
                f"{robot_name}/robotMapChange/response",
                f"{robot_name}/2dgoal/response", 
                f"{robot_name}/2dgoalplan/response",
                f"{robot_name}/2dgoalcancel/response",
                f"{robot_name}/initialpose/response"
            ]
            
            for topic in response_topics:
                mqtt_client.subscribe(topic)
                logger.info(f"📋 MQTT: Subscribing to response topic: {topic}")
        
        logger.info("✅ MQTT Gateway ready")
    
    # Zenoh起動
    zenoh_gateway = None
    zenoh_thread = None
    if enable_zenoh and ZENOH_AVAILABLE:
        logger.info("🌐 Starting Zenoh Gateway...")
        zenoh_gateway = ZenohGateway()
        zenoh_thread = threading.Thread(target=run_zenoh_in_thread, args=(zenoh_gateway,), daemon=True)
        zenoh_thread.start()
        logger.info("✅ Zenoh Gateway started in background thread")
    elif enable_zenoh and not ZENOH_AVAILABLE:
        logger.warning("⚠️ Zenoh is enabled but zenoh module is not available")
    
    logger.info("✅ Gateway ready - listening for messages...")
    logger.info("📺 Press Ctrl+C to stop")
    
    # Redis Streamsコマンド処理スレッドを開始
    redis_thread = threading.Thread(target=start_redis_subscriber, daemon=True)
    redis_thread.start()
    
    # Ctrl+Cシグナルハンドラを設定
    signal.signal(signal.SIGINT, lambda s, f: shutdown_gateway(mqtt_client, zenoh_gateway))
    
    try:
        if mqtt_client:
            mqtt_client.loop_forever()
        else:
            # MQTTが無効の場合は無限ループ
            while True:
                import time
                time.sleep(1)
    except KeyboardInterrupt:
        shutdown_gateway(mqtt_client, zenoh_gateway)

def run_zenoh_in_thread(zenoh_gateway):
    """Zenoh Gateway を別スレッドで実行"""
    logger = get_logger("gateway")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(zenoh_gateway.run_forever())
    except Exception as e:
        logger.error(f"💥 Zenoh Gateway thread error: {e}")

def start_redis_subscriber():
    """コマンド用Redis Streams処理開始"""
    logger = get_logger("gateway")
    logger.info("📥 Starting Redis Streams consumer...")
    
    # 監視対象のロボット名リスト（MQTTと統一）
    robot_names = ["robotA"]  # TODO: 設定ファイルから読み取り
    
    def command_handler(robot_name: str, command_data: dict) -> bool:
        """コマンド処理ハンドラ"""
        try:
            logger.info(f"📦 Received command for {robot_name}: {command_data}")
            
            command_type = command_data.get("command")
            
            if command_type == "navigation_start":
                # ナビゲーション開始コマンド - tasksを解析して適切なコマンドに変換
                tasks = command_data.get("tasks", [])
                navigation_tasks = [task for task in tasks if task.get("name") in ["NavigationTask", "navigation_2d"]]
                command_id = command_data.get("command_id")
                
                if len(navigation_tasks) == 1:
                    # 単一ポイント移動 -> 2d_goal
                    task = navigation_tasks[0]
                    nav_param = task.get("navParam", {})
                    success = mqtt_publisher.send_2d_goal(
                        robot_name,
                        nav_param.get("x", 0.0),
                        nav_param.get("y", 0.0),
                        nav_param.get("z", 0.0),
                        nav_param.get("theta", 0.0),  # theta を t にマッピング
                        command_id
                    )
                    logger.info(f"✅ Sent 2d_goal command to {robot_name}: x={nav_param.get('x')}, y={nav_param.get('y')}, theta={nav_param.get('theta')}")
                    return success
                elif len(navigation_tasks) > 1:
                    # 複数ポイント移動 -> 2d_goal_plan
                    poses = []
                    for task in navigation_tasks:
                        nav_param = task.get("navParam", {})
                        poses.append({
                            "x": nav_param.get("x", 0.0),
                            "y": nav_param.get("y", 0.0),
                            "z": nav_param.get("z", 0.0),
                            "t": nav_param.get("theta", 0.0)
                        })
                    logger.info(f"✅ Sent 2d_goal_plan command to {robot_name}: {len(poses)} waypoints")
                    return mqtt_publisher.send_2d_goal_plan(robot_name, poses, command_id)
                else:
                    logger.warning(f"⚠️ No navigation tasks found in navigation_start command")
                    return False
            
            elif command_type == "2d_goal":
                # 2D移動コマンド（単一ポイント）
                command_id = command_data.get("command_id")
                success = mqtt_publisher.send_2d_goal(
                    robot_name,
                    command_data.get("x", 0.0),
                    command_data.get("y", 0.0),
                    command_data.get("z", 0.0),
                    command_data.get("t", 0.0),
                    command_id
                )
                return success
                
            elif command_type == "2d_goal_plan":
                # 大局移動コマンド（複数ポイント）
                poses = command_data.get("poses", [])
                command_id = command_data.get("command_id")
                return mqtt_publisher.send_2d_goal_plan(robot_name, poses, command_id)
                
            elif command_type == "2d_goal_cancel":
                # 移動キャンセル（停止）コマンド
                command_id = command_data.get("command_id")
                return mqtt_publisher.send_2d_goal_cancel(robot_name, command_id)
                
            elif command_type == "initial_pose":
                # 位置補正コマンド
                command_id = command_data.get("command_id")
                return mqtt_publisher.send_initial_pose(
                    robot_name,
                    command_data.get("x", 0.0),
                    command_data.get("y", 0.0),
                    command_data.get("z", 0.0),
                    command_data.get("t", 0.0),
                    command_id
                )
                
            elif command_type == "robot_map_change":
                # マップ変更コマンド
                return True  # 一時的に無効化
                # map_name = command_data.get("map_name", "")
                # target_area = command_data.get("target_area", "maintenance")
                # relocate = command_data.get("relocate")
                # command_id = command_data.get("command_id")
                
                # # エリア情報をログに含める
                # area_info = ""
                # if target_area in ["area_a", "area_intermediate", "area_c", "maintenance"]:
                #     area_names = {
                #         "area_a": "FMS-A",
                #         "area_intermediate": "FMS-B", 
                #         "area_c": "FMS-C",
                #         "maintenance": "メンテナンス"
                #     }
                #     area_info = f" (エリア: {area_names.get(target_area, target_area)})"
                
                # logger.info(f"🗺️ Processing map change: map_name={map_name}{area_info}, relocate={relocate}, robot={robot_name}")
                
                # # マップ変更を送信
                # map_success = mqtt_publisher.send_map_change(robot_name, map_name, command_id)
                
                # # relocateデータがある場合かつ対応ロボットの場合のみ位置補正も送信
                # pose_success = True  # デフォルトは成功
                # if relocate and isinstance(relocate, dict) and relocate.get("x") is not None:
                #     if robot_name in RELOCATION_SUPPORTED_ROBOTS:
                #         pose_success = mqtt_publisher.send_initial_pose(
                #             robot_name,
                #             relocate.get("x", 0.0),
                #             relocate.get("y", 0.0),
                #             0.0,  # zはデフォルト
                #             relocate.get("theta", 0.0),
                #             command_id  # 同じcommand_idを使用
                #         )
                #         logger.info(f"✨ Sent initial_pose with map change for {robot_name}: x={relocate.get('x')}, y={relocate.get('y')}, theta={relocate.get('theta')}")
                #     else:
                #         logger.info(f"⚠️ Robot {robot_name} does not support relocation (supported: {RELOCATION_SUPPORTED_ROBOTS}). Skipping initial_pose.")
                # else:
                #     logger.info(f"ℹ️ No relocate data provided for map change command.")
                
                # return map_success and pose_success
            elif command_type == "extra_tool":
                # 追加ツールコマンド
                tool_name = command_data.get("tool", "")
                command_id = command_data.get("command_id")
                return mqtt_publisher.send_extra_tool(robot_name, tool_name, command_id)
            else:
                logger.warning(f"⚠️ Unknown command type: {command_type}")
                return False
                
        except Exception as e:
            logger.error(f"💥 Error handling command: {e}")
            return False
    
    # Redis Streams消費開始
    redis_streams_manager.consume_commands(robot_names, command_handler)

def shutdown_gateway(mqtt_client, zenoh_gateway=None):
    """ゲートウェイ終了処理"""
    logger = get_logger("gateway")
    logger.info("🛑 Gateway stopping...")
    
    # MQTT切断
    if mqtt_client:
        mqtt_client.disconnect()
        logger.info("📡 MQTT disconnected")
    
    # MQTT Publisher切断
    mqtt_publisher.disconnect()
    
    # Zenoh停止
    if zenoh_gateway:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(zenoh_gateway.stop())
            logger.info("🌐 Zenoh Gateway stopped")
        except Exception as e:
            logger.error(f"💥 Error stopping Zenoh Gateway: {e}")
    
    # Redis Streams停止
    redis_streams_manager.stop()
    
    logger.info("👋 Gateway stopped")
    sys.exit(0)

if __name__ == "__main__":
    main()
