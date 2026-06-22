import json
import uuid
import zenoh
from typing import Dict, Any, Optional
from ...common.logging import get_logger
from .sesstion import get_zenoh_session

logger = get_logger("gateway.zenoh.publisher")

class ZenohPublisher:
    """Zenoh用ロボットコマンドパブリッシャー"""
    
    def __init__(self, session: Optional[zenoh.Session] = None):
        """パブリッシャーを初期化
        
        Args:
            session: Zenohセッション（Noneの場合はグローバルセッションを使用）
        """
        self.session = session
    
    def get_session(self) -> zenoh.Session:
        """Zenohセッションを取得"""
        if self.session:
            return self.session
        return get_zenoh_session().get_session()
    
    def publish_robot_command(self, robot_name: str, topic_suffix: str, command: Dict[str, Any]):
        """ロボットにコマンドを送信
        
        Args:
            robot_name: ロボット名
            topic_suffix: トピックのサフィックス（例: "2dgoal", "robotmodechange"）
            command: 送信するコマンド辞書
        """
        try:
            session = self.get_session()
            key_expr = f"/{robot_name}/{topic_suffix}"
            
            # コマンドをJSONとしてシリアライズ
            payload = json.dumps(command, ensure_ascii=False)
            
            logger.info(f"📤 Publishing command to robot: {robot_name}")
            logger.debug(f"📋 Command payload: {payload}")
            
            # Zenohで送信
            session.put(key_expr, payload)
            
            logger.info(f"✅ Successfully published command to {robot_name} on {key_expr}")
            
        except Exception as e:
            logger.error(f"❌ Failed to publish command to {robot_name}: {e}")
            raise
    
    def send_robot_mode_change(self, robot_name: str, mode: int):
        """ロボットモード切り替えコマンドを送信
        
        Args:
            robot_name: ロボット名
            mode: 動作モード（0=外部連携、1=ローカル）
        """
        command = {
            "mode": mode
        }
        
        self.publish_robot_command(robot_name, "robotmodechange", command)
    
    def send_map_change(self, robot_name: str, map_name: str):
        """マップ切り替えコマンドを送信
        
        Args:
            robot_name: ロボット名
            map_name: 切り替えるマップ名（上位から指定される）
        """
        command = {
            "map_name": map_name
        }
        
        self.publish_robot_command(robot_name, "robotMapChange", command)
    
    def send_2d_goal(self, robot_name: str, x: float, y: float, z: float = 0.0, t: float = 0.0):
        """2D移動コマンドを送信
        
        Args:
            robot_name: ロボット名
            x: X座標
            y: Y座標
            z: Z座標（デフォルト0.0）
            t: 角度（デフォルト0.0）
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": str(uuid.uuid4()),
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
        
        self.publish_robot_command(robot_name, "2dgoal", command)
    
    def send_2d_goal_plan(self, robot_name: str, poses: list):
        """大局移動コマンドを送信
        
        Args:
            robot_name: ロボット名
            poses: 目標位置のリスト [{"x": x, "y": y, "z": z, "t": t}, ...]
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
                "UUID": str(uuid.uuid4()),
                "type": 1  # 大局移動
            },
            "move_order": move_orders
        }
        
        self.publish_robot_command(robot_name, "2dgoalplan", command)
    
    def send_2d_goal_cancel(self, robot_name: str):
        """移動キャンセル（停止）コマンドを送信
        
        Args:
            robot_name: ロボット名
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": str(uuid.uuid4()),
                "type": 9  # 移動キャンセル
            }
        }
        
        self.publish_robot_command(robot_name, "2dgoalcancel", command)
    
    def send_initial_pose(self, robot_name: str, x: float = 0.0, y: float = 0.0, z: float = 0.0, t: float = 0.0):
        """位置補正コマンドを送信
        
        Args:
            robot_name: ロボット名
            x: X座標位置（デフォルト0.0）
            y: Y座標位置（デフォルト0.0）
            z: Z座標位置（デフォルト0.0）
            t: 回転角度（デフォルト0.0）
        """
        command = {
            "ID": {
                "robot_name": robot_name,
                "UUID": str(uuid.uuid4()),
                "type": 2  # 位置補正
            },
            "initial_order": {
                "x": x,
                "y": y,
                "z": z,
                "t": t
            }
        }
        
        self.publish_robot_command(robot_name, "initialpose", command)
    
    def send_position_correction(self, robot_name: str, x: float, y: float, z: float = 0.0, t: float = 0.0):
        """位置補正コマンドを送信（便利メソッド）
        
        Args:
            robot_name: ロボット名
            x: X座標位置
            y: Y座標位置
            z: Z座標位置（デフォルト0.0）
            t: 回転角度（デフォルト0.0）
        """
        self.send_initial_pose(robot_name, x, y, z, t)
    
    def _get_timestamp(self) -> str:
        """現在のタイムスタンプを取得
        
        Returns:
            ISO形式のタイムスタンプ文字列
        """
        from datetime import datetime
        return datetime.now().isoformat()
    
    def send_status_request(self, robot_name: str):
        """ステータス要求を送信（カスタムコマンドとして）
        
        Args:
            robot_name: ロボット名
        """
        command = {
            "timestamp": self._get_timestamp()
        }
        
        self.publish_robot_command(robot_name, "statusrequest", command)
    
    # 便利メソッド：複数の操作を組み合わせ
    def send_move_to_position(self, robot_name: str, x: float, y: float, z: float = 0.0, t: float = 0.0):
        """指定位置への移動（便利メソッド）
        
        Args:
            robot_name: ロボット名
            x: X座標
            y: Y座標
            z: Z座標（デフォルト0.0）
            t: 角度（デフォルト0.0）
        """
        self.send_2d_goal(robot_name, x, y, z, t)
    
    def send_external_control_mode(self, robot_name: str):
        """外部連携モードに切り替え（便利メソッド）
        
        Args:
            robot_name: ロボット名
        """
        self.send_robot_mode_change(robot_name, 0)
    
    def send_local_control_mode(self, robot_name: str):
        """ローカルモードに切り替え（便利メソッド）
        
        Args:
            robot_name: ロボット名
        """
        self.send_robot_mode_change(robot_name, 1)
    
    def send_stop(self, robot_name: str):
        """停止（便利メソッド）
        
        Args:
            robot_name: ロボット名
        """
        self.send_2d_goal_cancel(robot_name, "stop_request")
    
    def send_emergency_stop(self, robot_name: str):
        """緊急停止（便利メソッド）
        
        Args:
            robot_name: ロボット名
        """
        self.send_2d_goal_cancel(robot_name, "emergency_stop")
    
    def send_reset_pose(self, robot_name: str, x: float = 0.0, y: float = 0.0, theta: float = 0.0):
        """位置リセット（便利メソッド）
        
        Args:
            robot_name: ロボット名
            x: X座標（デフォルト0.0）
            y: Y座標（デフォルト0.0）
            theta: 角度（デフォルト0.0）
        """
        pose = {"x": x, "y": y, "theta": theta}
        self.send_initial_pose(robot_name, pose)

# グローバルパブリッシャーインスタンス
_global_publisher: Optional[ZenohPublisher] = None

def get_zenoh_publisher() -> ZenohPublisher:
    """グローバルZenohパブリッシャーを取得
    
    Returns:
        グローバルZenohパブリッシャーインスタンス
    """
    global _global_publisher
    if _global_publisher is None:
        _global_publisher = ZenohPublisher()
    return _global_publisher