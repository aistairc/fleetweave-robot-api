import json
from ...infra.redis.client import redis_client
from ...domain.models.robot import RobotStatus
from ..merge.status_merger import merge
from ...common.logging import get_logger
import math

logger = get_logger("gateway.mqtt")

def on_message(client, userdata, msg):
    try:
        logger.info(f"📦 Received message on topic: {msg.topic}")
        payload = json.loads(msg.payload.decode())
        logger.debug(f"📋 Payload: {payload}")

        # トピックからロボット名とメッセージタイプを抽出
        topic_parts = msg.topic.split('/')
        logger.debug(f"🔍 Topic parts: {topic_parts}")
        
        # 新仕様: {robot_name}/robotStatus や {robot_name}/command/response
        if len(topic_parts) >= 2:
            robot_name = topic_parts[0] if topic_parts[0] else topic_parts[1]
            logger.info(f"🤖 Extracted robot name: '{robot_name}' from topic: {msg.topic}")
            
            if len(topic_parts) == 2 and topic_parts[1] == "robotStatus":
                # ロボットステータスメッセージ
                _handle_robot_status(robot_name, payload)
            elif len(topic_parts) == 3 and topic_parts[2] == "response":
                # コマンドレスポンスメッセージ
                command_type = topic_parts[1]
                _handle_robot_response(robot_name, command_type, payload)
            else:
                logger.warning(f"⚠️ Unknown topic format: {msg.topic}")
        else:
            logger.error(f"❌ Invalid topic format: {msg.topic}")
            return
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse JSON from topic {msg.topic}: {e}")
    except Exception as e:
        logger.error(f"💥 Error processing message from topic {msg.topic}: {e}")

def _handle_robot_status(robot_name: str, payload: dict):
    """ロボッッシステータス処理"""
    try:
        logger.info(f"🤖 Processing status for robot: {robot_name}")
        key = f"robot:status:{robot_name}"

        old = redis_client.hgetall(key)

        # データフォーマットを判定して変換
        if _is_legacy_format(payload):
            # 既存フォーマット（期待していたフォーマット）
            status = _parse_legacy_format(payload, robot_name)
        elif _is_new_format(payload):
            # 新しいフォーマット（連携資料のフォーマット）
            status = _parse_new_format(payload, robot_name)
        else:
            logger.error(f"❌ Unknown payload format for robot: {robot_name}")
            logger.debug(f"🔍 Payload: {payload}")
            return

        merged = merge(old, status)
        redis_client.hset(key, mapping=merged)
        
        logger.info(f"✅ Successfully updated Redis for robot: {robot_name}")
        logger.debug(f"💾 Updated data: {merged}")
    except Exception as e:
        logger.error(f"💥 Error processing robot status: {e}")

def _handle_robot_response(robot_name: str, command_type: str, payload: dict):
    """ロボットコマンドレスポンス処理"""
    try:
        response_code = payload.get("response_code")
        if response_code is not None:
            response_status = _get_response_status(response_code)
            logger.info(f"🤖 Robot {robot_name} {command_type} response: {response_status} (code: {response_code})")
            
            # レスポンスをRedisに保存（必要に応じて）
            response_key = f"robot:response:{robot_name}:{command_type}"
            response_data = {
                "robot_name": robot_name,
                "command_type": command_type,
                "response_code": response_code,
                "response_status": response_status,
                "timestamp": _get_timestamp()
            }
            
            # ID情報がある場合は保存
            if "ID" in payload:
                id_info = payload["ID"]
                response_data["uuid"] = id_info.get("UUID", "")
                response_data["type"] = id_info.get("type", "")
            
            # serial_numberがある場合は保存
            if "serial_number" in payload:
                response_data["serial_number"] = payload["serial_number"]
            
            redis_client.hset(response_key, mapping=response_data)
            logger.debug(f"💾 Response saved to Redis: {response_data}")
            
            # ナビゲーション関連のコマンドの場合、タスクステータスを更新
            if command_type in ["2dgoal", "2dgoalplan", "2dgoalcancel"]:
                _update_navigation_task_status(robot_name, response_code, payload, command_type)
                
        else:
            logger.warning(f"⚠️ Response payload missing response_code: {payload}")
    except Exception as e:
        logger.error(f"💥 Error processing robot response: {e}")

def _get_response_status(response_code: int) -> str:
    """レスポンスコードから状態文字列を取得"""
    status_map = {
        0: "ReceiveOK",          # 受信応答
        1: "Success",            # 実行完了
        2: "Fail",               # 実行失敗
        3: "WayPointArraival",   # 中継地点到着（大局移動のみ）
        4: "AnotherTaskRunning", # 別命令を実行中
        5: "MapNotFound",        # 指定マップ無し
        6: "MapChangeRetry"      # 走行中マップ切り替えエラー
    }
    return status_map.get(response_code, f"unknown({response_code})")

def _get_timestamp() -> str:
    """現在のタイムスタンプを取得"""
    from datetime import datetime
    return datetime.now().isoformat()

def _update_navigation_task_status(robot_name: str, response_code: int, payload: dict, command_type: str = None):
    """ナビゲーションタスクのステータス更新"""
    try:
        # PayloadからUUIDを取得
        command_id = None
        if "ID" in payload and "UUID" in payload["ID"]:
            command_id = payload["ID"]["UUID"]
            logger.info(f"🔍 Processing response for command_id: {command_id}")
        
        # ロボットに関連するアクティブなナビゲーションタスクを検索
        task_keys = redis_client.keys(f"navigation:task:*")
        
        for task_key in task_keys:
            task_data_str = redis_client.hget(task_key, "data")
            current_status = redis_client.hget(task_key, "status")
            
            if task_data_str and current_status:
                task_data = json.loads(task_data_str.decode() if isinstance(task_data_str, bytes) else task_data_str)
                current_status = current_status.decode() if isinstance(current_status, bytes) else current_status
                
                # タスクIDの一致確認（UUIDとcommand_idの両方で確認）
                task_id = task_data.get("task_id")
                should_update = False
                
                if command_id:
                    # UUIDが指定されている場合、正確な一致確認
                    should_update = (task_id == command_id and 
                                   task_data.get("robot_name") == robot_name and 
                                   current_status in ["pending", "running"])
                else:
                    # UUIDがない場合、ロボット名とアクティブ状態で確認
                    should_update = (task_data.get("robot_name") == robot_name and 
                                   current_status in ["pending", "running"])
                
                if should_update:
                    # コマンドタイプとレスポンスコードに応じてステータスを更新
                    if command_type in ["2dgoalcancel", "2d_goal_cancel"]:
                        # キャンセルコマンドの場合
                        if response_code == 1:
                            new_status = "canceled"
                        elif response_code == 2:
                            new_status = "failed"  # キャンセル失敗
                        elif response_code == 7:
                            new_status = "canceled"  # NotFound - 未実行中のキャンセル
                        else:
                            new_status = "failed"
                        logger.info(f"🛑 Navigation cancel command for {robot_name}: response_code={response_code} → {new_status} (task_id: {task_id})")
                    else:
                        # 通常のナビゲーションコマンドの場合
                        new_status = _get_task_status_from_response_code(response_code)
                    
                    if new_status != current_status:
                        redis_client.hset(task_key, "status", new_status)
                        logger.info(f"✅ Updated navigation task status for {robot_name}: {current_status} → {new_status} (command: {command_type}, response_code: {response_code}, task_id: {task_id})")
                        
                        # タスク完了時の追加処理
                        if new_status == "completed":
                            _handle_task_completion(robot_name, task_data)
                        elif new_status == "canceled":
                            _handle_task_cancellation(robot_name, task_data)
                        elif new_status == "failed":
                            _handle_task_failure(robot_name, task_data)
                        
                        break  # 該当タスクが見つかったのでループを抜ける
                            
    except Exception as e:
        logger.error(f"💥 Error updating navigation task status: {e}")

def _get_task_status_from_response_code(response_code: int) -> str:
    """レスポンスコードからタスクステータスを取得"""
    status_map = {
        0: "running",     # ReceiveOK - 受信応答、実行開始
        1: "completed",   # Success - 実行完了
        2: "failed",      # Fail - 実行失敗
        3: "running",     # WayPointArraival - 中継地点到着（継続中）
        4: "failed",      # AnotherTaskRunning - 別命令実行中
        5: "failed",      # MapNotFound - 指定マップなし
        6: "failed",      # MapChangeRetry - マップ切り替えエラー
        10: "running",    # NotFound - ドアオープン中などで未実行
        11: "running",   # Canceled - キャンセル成功
        12: "running"    # CancelFailed - キャンセル失敗
    }
    return status_map.get(response_code, "unknown")

def _handle_task_completion(robot_name: str, task_data: dict):
    """タスク完了時の処理"""
    try:
        # ロボットの現在のステータスを確認
        current_robot_status = redis_client.hget(f"robot:status:{robot_name}", "status")
        
        if current_robot_status:
            # バイト型の場合のみデコード、そうでなければそのまま使用
            status_str = current_robot_status.decode() if isinstance(current_robot_status, bytes) else current_robot_status
            
            # ロボットが作業中（working）の場合のみidleに変更
            # その他のステータス（moving, emergency等）はロボット側の更新を尊重
            if status_str == "working":
                redis_client.hset(f"robot:status:{robot_name}", "status", "idle")
                logger.info(f"🎉 Navigation task completed for {robot_name} - robot status updated to idle")
            else:
                logger.info(f"🎉 Navigation task completed for {robot_name} - robot status remains {status_str}")
        else:
            # ステータスが不明な場合はidleに設定
            redis_client.hset(f"robot:status:{robot_name}", "status", "idle")
            logger.info(f"🎉 Navigation task completed for {robot_name} - robot status set to idle (no previous status)")
            
    except Exception as e:
        logger.error(f"💥 Error handling task completion: {e}")

def _handle_task_cancellation(robot_name: str, task_data: dict):
    """タスクキャンセル時の処理"""
    try:
        # キャンセル時も同様に現在のステータスを確認
        current_robot_status = redis_client.hget(f"robot:status:{robot_name}", "status")
        
        if current_robot_status:
            # バイト型の場合のみデコード、そうでなければそのまま使用
            status_str = current_robot_status.decode() if isinstance(current_robot_status, bytes) else current_robot_status
            
            if status_str == "working":
                redis_client.hset(f"robot:status:{robot_name}", "status", "idle")
                logger.info(f"🛑 Navigation task canceled for {robot_name} - robot status updated to idle")
            else:
                logger.info(f"🛑 Navigation task canceled for {robot_name} - robot status remains {status_str}")
        else:
            redis_client.hset(f"robot:status:{robot_name}", "status", "idle")
            logger.info(f"🛑 Navigation task canceled for {robot_name} - robot status set to idle (no previous status)")
            
    except Exception as e:
        logger.error(f"💥 Error handling task cancellation: {e}")

def _handle_task_failure(robot_name: str, task_data: dict):
    """タスク失敗時の処理"""
    try:
        # 失敗時も同様に現在のステータスを確認
        current_robot_status = redis_client.hget(f"robot:status:{robot_name}", "status")
        
        if current_robot_status:
            # バイト型の場合のみデコード、そうでなければそのまま使用
            status_str = current_robot_status.decode() if isinstance(current_robot_status, bytes) else current_robot_status
            
            if status_str == "working":
                redis_client.hset(f"robot:status:{robot_name}", "status", "idle")
                logger.warning(f"⚠️ Navigation task failed for {robot_name} - robot status updated to idle")
            else:
                logger.warning(f"⚠️ Navigation task failed for {robot_name} - robot status remains {status_str}")
        else:
            redis_client.hset(f"robot:status:{robot_name}", "status", "idle")
            logger.warning(f"⚠️ Navigation task failed for {robot_name} - robot status set to idle (no previous status)")
            
    except Exception as e:
        logger.error(f"💥 Error handling task failure: {e}")

def _is_new_format(payload):
    """新しいフォーマットかどうかを判定"""
    return "robot_status" in payload and "location" in payload and "battery" in payload

def _is_legacy_format(payload):
    """レガシーフォーマットかどうかを判定"""
    # レガシーフォーマットは既存のRobotStatusの構造に従う
    # 新フォーマットとは異なる構造を持つ
    return not _is_new_format(payload) and any(key in payload for key in ["name", "battery_soc", "status", "map_name"])

def _parse_legacy_format(payload, name):
    """レガシーフォーマットをパース"""
    # 既存のフォーマット構造をそのまま使用
    return RobotStatus(
        name=payload.get("name", name),
        battery_soc=payload.get("battery_soc", 0.0),
        map_name=payload.get("map_name", ""),
        pos_x=payload.get("pos_x"),
        pos_y=payload.get("pos_y"), 
        pos_theta=payload.get("pos_theta"),
        status=payload.get("status", "unknown"),
        mode=payload.get("mode", 0),
        task_no=payload.get("task_no", "0"),
    )

def _parse_new_format(payload, name):
    """新しいフォーマットをパース"""
    robot_status = payload.get("robot_status", {})
    location = payload.get("location", {})
    battery = payload.get("battery", {})
    
    # ステータスの変換（数値 → 文字列）
    status_map = {
            0: "moving_complate",     # 移動完了
            1: "moving",              # 移動中
            2: "moving_manual",       # マニュアル走行
            3: "idle",                # 待機中
            10: "emergency",          # 非常停止ボタン押下中
            11: "open_door",          # ドアがオープン中
            12: "initialize"          # ライダー検知での停止中
        }
    status = status_map.get(robot_status.get("status"), "unknown")
    
    # バッテリーレベルの変換（100% → 1.0）
    battery_level = battery.get("level", 0)
    battery_soc = battery_level / 100.0 if battery_level else 0.0
    
    # モードの取得
    mode = robot_status.get("mode", 0)
    
    return RobotStatus(
        name=name,
        battery_soc=battery_soc,
        map_name=robot_status.get("map", ""),
        pos_x=location.get("x"),
        pos_y=location.get("y"),
        pos_z=location.get("z", 0.0),  # z座標を追加
        pos_theta=math.radians(location.get("t", 0.0)),  # theta（角度）
        pos_w=1.0,  # クォータニオンのw成分（デフォルト値）
        status=status,
        mode=mode,  # modeを追加
        task_no="0",  # 新フォーマットにはtaskNoがないのでデフォルト値
    )
