import paho.mqtt.client as mqtt
import json
import threading
import uuid
from ...common.logging import get_logger
from ...settings import MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD

class MQTTPublisher:
    """MQTT コマンド送信用クラス"""
    
    def __init__(self):
        self.logger = get_logger("mqtt_publisher")
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """MQTT クライアント初期化"""
        try:
            self.logger.info(f"🌐 Connecting to MQTT broker: {MQTT_HOST}:{MQTT_PORT}")
            
            # 認証情報の確認とログ出力
            if MQTT_USERNAME and MQTT_PASSWORD:
                self.logger.info(f"🔐 MQTT authentication enabled for user: {MQTT_USERNAME}")
            elif MQTT_USERNAME:
                self.logger.warning(f"⚠️ MQTT username provided but no password: {MQTT_USERNAME}")
            else:
                self.logger.info("🔓 MQTT authentication disabled (no username/password)")
            
            self.client = mqtt.Client()
            
            # コールバック設定
            self.client.on_connect = self._on_connect
            self.client.on_publish = self._on_publish
            self.client.on_disconnect = self._on_disconnect
            self.client.on_log = self._on_log
            
            # 認証情報設定（環境変数で指定されている場合）
            if MQTT_USERNAME and MQTT_PASSWORD:
                self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            
            # 接続試行
            result = self.client.connect(MQTT_HOST, MQTT_PORT, 60)
            if result != 0:
                self.logger.error(f"💥 MQTT connect() returned error code: {result}")
                return
                
            self.client.loop_start()
            self.logger.info("📡 MQTT Publisher initialized")
            
        except Exception as e:
            self.logger.error(f"💥 Failed to initialize MQTT publisher: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT接続完了コールバック"""
        if rc == 0:
            self.logger.info("✅ MQTT Publisher connected successfully")
        else:
            error_messages = {
                1: "incorrect protocol version",
                2: "invalid client identifier", 
                3: "server unavailable",
                4: "bad username or password",
                5: "not authorised"
            }
            error_msg = error_messages.get(rc, f"unknown error code {rc}")
            self.logger.error(f"💥 MQTT Publisher connection failed: {rc} ({error_msg})")
            
            # 認証エラーの場合は詳細な診断情報を出力
            if rc in [4, 5]:
                self.logger.error(f"🔍 Authentication diagnostic:")
                self.logger.error(f"   - MQTT_HOST: {MQTT_HOST}")
                self.logger.error(f"   - MQTT_PORT: {MQTT_PORT}")
                self.logger.error(f"   - MQTT_USERNAME: {'SET' if MQTT_USERNAME else 'NOT SET'}")
                self.logger.error(f"   - MQTT_PASSWORD: {'SET' if MQTT_PASSWORD else 'NOT SET'}")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT切断コールバック"""
        if rc != 0:
            self.logger.warning(f"⚠️ MQTT Publisher unexpected disconnect: {rc}")
        else:
            self.logger.info("📡 MQTT Publisher disconnected")
    
    def _on_log(self, client, userdata, level, buf):
        """MQTTログコールバック"""
        # パスワード等の機密情報をフィルタリング
        if "password" not in buf.lower() and "auth" not in buf.lower():
            self.logger.debug(f"🔍 MQTT: {buf}")
    
    def _on_publish(self, client, userdata, mid):
        """MQTT publish完了コールバック"""
        self.logger.debug(f"📤 Message published: {mid}")
    
    def publish_robot_command(self, robot_name: str, command_type: str, command_data: dict):
        """ロボットコマンド送信（汎用）
        
        Args:
            robot_name: ロボット名
            command_type: コマンドタイプ (robotmodechange, robotmapchange, 2dgoal, etc.)
            command_data: コマンドデータ
        """
        try:
            # クライアントの接続状態をチェック
            if not self.client or not self.client.is_connected():
                self.logger.warning("⚠️ MQTT client not connected, attempting to reconnect...")
                self._init_client()
                # 少し待ってから再度チェック
                import time
                time.sleep(0.5)
                if not self.client or not self.client.is_connected():
                    self.logger.error("💥 Failed to reconnect to MQTT broker")
                    return False
            
            topic = f"{robot_name}/{command_type}"  # 修正: 先頭の / を削除
            payload = json.dumps(command_data)
            
            result = self.client.publish(topic, payload)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"📤 Command {command_type} sent to {robot_name}: {command_data}")
                return True
            else:
                self.logger.error(f"💥 Failed to publish {command_type} command: {result.rc}")
                return False
                
        except Exception as e:
            self.logger.error(f"💥 Error publishing {command_type} command: {e}")
            return False
    
    def send_robot_mode_change(self, robot_name: str, mode: int):
        """ロボットモード切り替えコマンドを送信
        
        Args:
            robot_name: ロボット名
            mode: モード (0=ローカル, 1=外部連携)
        """
        command = {"mode": mode}
        return self.publish_robot_command(robot_name, "robotmodechange", command)
    
    def send_map_change(self, robot_name: str, map_name: str, command_id: str = None):
        """マップ切り替えコマンドを送信
        
        Args:
            robot_name: ロボット名
            map_name: マップ名
            command_id: コマンドID（使用しないが一貫性のため）
        """
        command = {"map_name": map_name}
        return self.publish_robot_command(robot_name, "robotMapChange", command)
    def send_extra_tool(self, robot_name: str, tool_name: str, command_id: str = None):
        """追加ツールコマンドを送信
        
        Args:
            robot_name: ロボット名
            tool_name: ツール名
            command_id: コマンドID（使用しないが一貫性のため）
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": command_id if command_id else str(uuid.uuid4()),
                "type": 10  # 追加ツールコマンド
            },
        "tool": tool_name
        }
        return self.publish_robot_command(robot_name, "extra_tool", command)
    def send_2d_goal(self, robot_name: str, x: float, y: float, z: float = 0.0, t: float = 0.0, command_id: str = None):
        """2D移動コマンドを送信
        
        Args:
            robot_name: ロボット名
            x: X座標
            y: Y座標
            z: Z座標（デフォルト0.0）
            t: 角度（デフォルト0.0）
            command_id: コマンドID（なければUUIDを生成）
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": command_id if command_id else str(uuid.uuid4()),
                "type": 0  # 2D移動
            },
            "move_order": [{
                "serial_number": 0,
                "x": x,
                "y": y,
                "z": z,
                "t": t
            }]
        }
        return self.publish_robot_command(robot_name, "2dgoal", command)
    
    def send_2d_goal_plan(self, robot_name: str, poses: list, command_id: str = None):
        """大局移動コマンドを送信
        
        Args:
            robot_name: ロボット名
            poses: 目標位置のリスト [{"x": x, "y": y, "z": z, "t": t}, ...]
            command_id: コマンドID（なければUUIDを生成）
        """
        move_orders = []
        for i, pose in enumerate(poses):
            move_orders.append({
                "serial_number": i,
                "x": pose.get("x", 0.0),
                "y": pose.get("y", 0.0),
                "z": pose.get("z", 0.0),
                "t": pose.get("t", 0.0)
            })
        
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": command_id if command_id else str(uuid.uuid4()),
                "type": 1  # 大局移動
            },
            "move_order": move_orders
        }
        return self.publish_robot_command(robot_name, "2dgoalplan", command)
    
    def send_2d_goal_cancel(self, robot_name: str, command_id: str = None):
        """移動キャンセル（停止）コマンドを送信
        
        Args:
            robot_name: ロボット名
            command_id: コマンドID（なければUUIDを生成）
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": command_id if command_id else str(uuid.uuid4()),
                "type": 9  # 移動キャンセル
            }
        }
        return self.publish_robot_command(robot_name, "2dgoalcancel", command)
    
    def send_initial_pose(self, robot_name: str, x: float = 0.0, y: float = 0.0, z: float = 0.0, t: float = 0.0, command_id: str = None):
        """位置補正コマンドを送信
        
        Args:
            robot_name: ロボット名
            x: X座標位置（デフォルト0.0）
            y: Y座標位置（デフォルト0.0）
            z: Z座標位置（デフォルト0.0）
            t: 回転角度（デフォルト0.0）
            command_id: コマンドID（なければUUIDを生成）
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": command_id if command_id else str(uuid.uuid4()),
                "type": 2  # 位置補正
            },
            "initial_order": {
                "x": x,
                "y": y,
                "z": z,
                "t": t
            }
        }
        return self.publish_robot_command(robot_name, "initialpose", command)
    
    # 便利メソッド
    def send_external_control_mode(self, robot_name: str):
        """外部連携モードに切り替え"""
        return self.send_robot_mode_change(robot_name, 1)
    
    def send_local_control_mode(self, robot_name: str):
        """ローカルモードに切り替え"""
        return self.send_robot_mode_change(robot_name, 0)
    
    def send_move_to_position(self, robot_name: str, x: float, y: float, z: float = 0.0, t: float = 0.0):
        """指定位置への移動（便利メソッド）"""
        return self.send_2d_goal(robot_name, x, y, z, t)
    
    def send_multi_waypoint_path(self, robot_name: str, waypoints: list):
        """複数地点を通る経路を送信"""
        return self.send_2d_goal_plan(robot_name, waypoints)
    
    def send_position_correction(self, robot_name: str, x: float, y: float, z: float = 0.0, t: float = 0.0):
        """位置補正コマンドを送信（便利メソッド）"""
        return self.send_initial_pose(robot_name, x, y, z, t)
    
    def disconnect(self):
        """MQTT切断"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.logger.info("👋 MQTT Publisher disconnected")

# グローバルインスタンス
mqtt_publisher = MQTTPublisher()
