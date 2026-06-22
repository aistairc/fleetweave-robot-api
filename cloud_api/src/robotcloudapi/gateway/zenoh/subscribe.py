import json
import zenoh
from typing import Callable, Optional
from ...infra.redis.client import redis_client
from ...domain.models.robot import RobotStatus
from ..merge.status_merger import merge
from ...common.logging import get_logger
from .sesstion import get_zenoh_session

logger = get_logger("gateway.zenoh.subscriber")

class ZenohSubscriber:
    """Zenoh用ロボットステータスサブスクライバー"""
    
    def __init__(self, session: Optional[zenoh.Session] = None):
        """サブスクライバーを初期化
        
        Args:
            session: Zenohセッション（Noneの場合はグローバルセッションを使用）
        """
        self.session = session
        self.subscribers = {}
        
    def get_session(self) -> zenoh.Session:
        """Zenohセッションを取得"""
        if self.session:
            return self.session
        return get_zenoh_session().get_session()
    
    def on_robot_status(self, sample: zenoh.Sample):
        """ロボットステータスメッセージを受信した時のハンドラー
        
        Args:
            sample: Zenohサンプルデータ
        """
        try:
            key_expr = str(sample.key_expr)
            payload_bytes = sample.payload
            
            logger.info(f"📦 Received message on key: {key_expr}")
            
            # ペイロードをJSONとしてデコード
            payload = json.loads(payload_bytes.decode('utf-8'))
            logger.debug(f"📋 Payload: {payload}")

            # キーからロボット名とメッセージタイプを抽出 ({robot_name}/robotStatus または {robot_name}/command/response の形式)
            key_parts = key_expr.split('/')
            if len(key_parts) >= 2:
                robot_name = key_parts[0]
                
                if len(key_parts) == 2 and key_parts[1] == "robotStatus":
                    # ロボットステータスメッセージ
                    self._handle_robot_status(robot_name, payload)
                elif len(key_parts) == 3 and key_parts[2] == "response":
                    # コマンドレスポンスメッセージ
                    command_type = key_parts[1]
                    self._handle_robot_response(robot_name, command_type, payload)
                else:
                    logger.warning(f"⚠️ Unknown key format: {key_expr}")
            else:
                logger.error(f"❌ Invalid key format: {key_expr}")
                return

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse JSON from key {key_expr}: {e}")
        except Exception as e:
            logger.error(f"💥 Error processing message from key {key_expr}: {e}")
    
    def _handle_robot_status(self, robot_name: str, payload: dict):
        """ロボットステータス処理"""
        try:
            logger.info(f"🤖 Processing status for robot: {robot_name}")
            redis_key = f"robot:status:{robot_name}"

            old = redis_client.hgetall(redis_key)

            # 新仕様のフォーマットを処理
            if self._is_new_format(payload):
                status = self._parse_new_format(payload, robot_name)
            else:
                logger.error(f"❌ Unknown payload format for robot: {robot_name}")
                logger.debug(f"🔍 Payload: {payload}")
                return

            merged = merge(old, status)
            redis_client.hset(redis_key, mapping=merged)
            
            logger.info(f"✅ Successfully updated Redis for robot: {robot_name}")
            logger.debug(f"💾 Updated data: {merged}")
            
        except Exception as e:
            logger.error(f"💥 Error processing robot status: {e}")
    
    def _handle_robot_response(self, robot_name: str, command_type: str, payload: dict):
        """ロボットコマンドレスポンス処理"""
        try:
            response_code = payload.get("response_code")
            if response_code is not None:
                response_status = self._get_response_status(response_code)
                logger.info(f"🤖 Robot {robot_name} {command_type} response: {response_status} (code: {response_code})")
                
                # レスポンスをRedisに保存
                response_key = f"robot:response:{robot_name}:{command_type}"
                response_data = {
                    "robot_name": robot_name,
                    "command_type": command_type,
                    "response_code": response_code,
                    "response_status": response_status,
                    "timestamp": self._get_timestamp()
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
            else:
                logger.warning(f"⚠️ Response payload missing response_code: {payload}")
        except Exception as e:
            logger.error(f"💥 Error processing robot response: {e}")

    def _is_new_format(self, payload):
        """新しいフォーマットかどうかを判定"""
        return "robot_status" in payload and "location" in payload and "battery" in payload
    
    def _parse_new_format(self, payload, name):
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
            pos_theta=location.get("t"),  # tがtheta（角度）
            status=status,
            mode=mode,
            task_no="0",  # 新フォーマットにはtaskNoがないのでデフォルト値
        )

    def on_robot_response(self, sample: zenoh.Sample):
        """ロボットレスポンスメッセージを受信した時のハンドラー
        
        Args:
            sample: Zenohサンプルデータ
        """
        try:
            key_expr = str(sample.key_expr)
            payload_bytes = sample.payload
            
            logger.info(f"📨 Received response on key: {key_expr}")
            
            # ペイロードをJSONとしてデコード
            payload = json.loads(payload_bytes.decode('utf-8'))
            logger.debug(f"📋 Response payload: {payload}")

            # キーからロボット名とコマンドタイプを抽出 (/{name}/{command}/response の形式)
            key_parts = key_expr.split('/')
            if len(key_parts) >= 4 and key_parts[3] == 'response':
                robot_name = key_parts[1]
                command_type = key_parts[2]
            else:
                logger.error(f"❌ Invalid response key format: {key_expr}")
                return

            # レスポンスコードの解析
            response_code = payload.get("responsecode")
            if response_code is not None:
                response_status = self._get_response_status(response_code)
                logger.info(f"🤖 Robot {robot_name} {command_type} response: {response_status} (code: {response_code})")
                
                # レスポンスをRedisに保存（オプション）
                redis_key = f"robot:response:{robot_name}:{command_type}"
                response_data = {
                    "responsecode": response_code,
                    "status": response_status,
                    "timestamp": self._get_timestamp(),
                    "command_type": command_type
                }
                redis_client.hset(redis_key, mapping=response_data)
                redis_client.expire(redis_key, 300)  # 5分でexpire
                
            else:
                logger.warning(f"⚠️ No responsecode found in response from {robot_name}")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse JSON response from key {key_expr}: {e}")
        except Exception as e:
            logger.error(f"💥 Error processing response from key {key_expr}: {e}")

    def _get_response_status(self, response_code: int) -> str:
        """レスポンスコードから状態文字列を取得
        
        Args:
            response_code: レスポンスコード
            
        Returns:
            状態文字列
        """
        status_map = {
            0: "received",      # 受信応答
            1: "completed",     # 実行完了
            2: "failed",        # 実行失敗
            3: "waypoint_reached" # 中継地点到達
        }
        return status_map.get(response_code, f"unknown({response_code})")
    
    def _get_timestamp(self) -> str:
        """現在のタイムスタンプを取得
        
        Returns:
            ISO形式のタイムスタンプ文字列
        """
    
    def _get_response_status(self, response_code: int) -> str:
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
    
    def _get_timestamp(self) -> str:
        """現在のタイムスタンプを取得"""
        from datetime import datetime
        return datetime.now().isoformat()
        """新しいフォーマットをパース"""
        robotstatus = payload.get("robotstatus", {})
        location = payload.get("location", {})
        battery = payload.get("battery", {})
        
        # ステータスの変換（数値 → 文字列）
        status_map = {
            0: "idle",
            1: "moving", 
            2: "working",
            3: "error",
            4: "charging"
        }
        status = status_map.get(robotstatus.get("status"), "unknown")
        
        # バッテリーレベルの変換（100% → 1.0）
        battery_level = battery.get("level", 0)
        battery_soc = battery_level / 100.0 if battery_level else 0.0
        
        return RobotStatus(
            name=name,
            battery_soc=battery_soc,
            map_name=robotstatus.get("map", ""),
            pos_x=location.get("x"),
            pos_y=location.get("y"),
            pos_theta=location.get("t"),  # tがtheta（角度）
            status=status,
            task_no="0",  # 新フォーマットにはtaskNoがないのでデフォルト値
        )
    
    def subscribe_robot_status(self, robot_name: str = "*"):
        """ロボットステータスをサブスクライブ
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        try:
            session = self.get_session()
            key_expr = f"/{robot_name}/robotstatus"
            
            logger.info(f"🔔 Subscribing to robot status: {key_expr}")
            
            subscriber = session.declare_subscriber(key_expr, self.on_robot_status)
            self.subscribers[key_expr] = subscriber
            
            logger.info(f"✅ Successfully subscribed to: {key_expr}")
            return subscriber
            
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to {key_expr}: {e}")
            raise
    
    def subscribe_robot_responses(self, robot_name: str = "*", command_type: str = "*"):
        """ロボットレスポンスをサブスクライブ
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
            command_type: コマンドタイプ（"*"で全コマンド、例："robotmodechange"）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        try:
            session = self.get_session()
            key_expr = f"/{robot_name}/{command_type}/response"
            
            logger.info(f"🔔 Subscribing to robot responses: {key_expr}")
            
            subscriber = session.declare_subscriber(key_expr, self.on_robot_response)
            self.subscribers[key_expr] = subscriber
            
            logger.info(f"✅ Successfully subscribed to responses: {key_expr}")
            return subscriber
            
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to responses {key_expr}: {e}")
            raise
    
    def subscribe_mode_change_responses(self, robot_name: str = "*"):
        """モード変更レスポンスを監視（便利メソッド）
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses(robot_name, "robotmodechange")
    
    def subscribe_map_change_responses(self, robot_name: str = "*"):
        """マップ変更レスポンスを監視（便利メソッド）
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses(robot_name, "robotmapchange")
    
    def subscribe_2d_goal_responses(self, robot_name: str = "*"):
        """2D移動レスポンスを監視（便利メソッド）
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses(robot_name, "2dgoal")
    
    def subscribe_2d_goal_plan_responses(self, robot_name: str = "*"):
        """大局経路レスポンスを監視（便利メソッド）
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses(robot_name, "2dgoalplan")
    
    def subscribe_2d_goal_cancel_responses(self, robot_name: str = "*"):
        """移動キャンセルレスポンスを監視（便利メソッド）
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses(robot_name, "2dgoalcancel")
    
    def subscribe_initial_pose_responses(self, robot_name: str = "*"):
        """位置補正レスポンスを監視（便利メソッド）
        
        Args:
            robot_name: ロボット名（"*"で全ロボット）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses(robot_name, "initialpose")
    
    def subscribe_all_responses(self):
        """全ロボットの全レスポンスを監視（便利メソッド）
        
        Returns:
            Zenohサブスクライバーオブジェクト
        """
        return self.subscribe_robot_responses("*", "*")
    
    def subscribe_all_robots(self):
        """全ロボットのステータスをサブスクライブ"""
        return self.subscribe_robot_status("*")
    
    def unsubscribe(self, key_expr: str):
        """指定されたキーのサブスクリプションを停止
        
        Args:
            key_expr: キー式
        """
        if key_expr in self.subscribers:
            try:
                logger.info(f"🔕 Unsubscribing from: {key_expr}")
                self.subscribers[key_expr].undeclare()
                del self.subscribers[key_expr]
                logger.info(f"✅ Successfully unsubscribed from: {key_expr}")
            except Exception as e:
                logger.error(f"❌ Failed to unsubscribe from {key_expr}: {e}")
    
    def unsubscribe_all(self):
        """全てのサブスクリプションを停止"""
        for key_expr in list(self.subscribers.keys()):
            self.unsubscribe(key_expr)

# グローバルサブスクライバーインスタンス
_global_subscriber: Optional[ZenohSubscriber] = None

def get_zenoh_subscriber() -> ZenohSubscriber:
    """グローバルZenohサブスクライバーを取得
    
    Returns:
        グローバルZenohサブスクライバーインスタンス
    """
    global _global_subscriber
    if _global_subscriber is None:
        _global_subscriber = ZenohSubscriber()
    return _global_subscriber

def start_zenoh_robot_monitoring():
    """Zenohロボット監視を開始"""
    subscriber = get_zenoh_subscriber()
    return subscriber.subscribe_all_robots()

def start_zenoh_response_monitoring():
    """Zenohレスポンス監視を開始"""
    subscriber = get_zenoh_subscriber()
    return subscriber.subscribe_all_responses()

def stop_zenoh_robot_monitoring():
    """Zenohロボット監視を停止"""
    subscriber = get_zenoh_subscriber()
    subscriber.unsubscribe_all()