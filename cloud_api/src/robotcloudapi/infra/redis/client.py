import redis
import threading
import json
import time
import uuid
from ...settings import REDIS_HOST, REDIS_PORT
from ...common.logging import get_logger

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
)

class RedisStreamsManager:
    """Redis Streams管理クラス"""
    
    def __init__(self):
        self.redis_client = redis_client
        self.logger = get_logger("redis_streams")
        self._is_running = False
        self.consumer_group = "gateway_group"
        self.consumer_name = "gateway_001"
        
    def add_command(self, robot_name: str, command_data: dict) -> str:
        """ロボットコマンドをストリームに追加"""
        try:
            stream_key = f"robot:commands:{robot_name}"
            
            # コマンドIDがない場合は生成
            if "command_id" not in command_data:
                command_data["command_id"] = str(uuid.uuid4())
            
            # ストリームエントリ作成
            stream_entry = {
                "command_id": command_data["command_id"],
                "command_type": command_data.get("command", "unknown"),
                "payload": json.dumps(command_data),
                "status": "pending",
                "created_at": str(int(time.time())),
                "robot_name": robot_name
            }
            
            # ストリームにメッセージ追加
            message_id = self.redis_client.xadd(stream_key, stream_entry)
            
            self.logger.info(f"📤 Added command to stream {stream_key}: {command_data['command_id']}")
            return message_id
            
        except Exception as e:
            self.logger.error(f"💥 Failed to add command to stream: {e}")
            return None
    
    def init_consumer_groups(self, robot_names: list):
        """コンシューマーグループ初期化"""
        for robot_name in robot_names:
            try:
                stream_key = f"robot:commands:{robot_name}"
                self.redis_client.xgroup_create(
                    stream_key, 
                    self.consumer_group, 
                    "0", 
                    mkstream=True
                )
                self.logger.info(f"📋 Created consumer group for {stream_key}")
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    self.logger.debug(f"📋 Consumer group already exists for {stream_key}")
                else:
                    self.logger.error(f"💥 Error creating consumer group: {e}")
    
    def consume_commands(self, robot_names: list, callback_handler):
        """コマンドストリームを消費"""
        try:
            # コンシューマーグループ初期化
            self.init_consumer_groups(robot_names)
            
            # ストリームキーリスト作成
            streams = {f"robot:commands:{robot_name}": ">" for robot_name in robot_names}
            
            self.logger.info(f"📥 Starting to consume commands from {len(robot_names)} streams")
            self.logger.info(f"🔍 Monitoring streams: {list(streams.keys())}")
            self.logger.info(f"👥 Consumer Group: {self.consumer_group}, Consumer: {self.consumer_name}")
            self._is_running = True
            
            while self._is_running:
                try:
                    self.logger.debug(f"🔄 Waiting for messages from streams...")
                    # メッセージ読み取り（1秒タイムアウト）
                    messages = self.redis_client.xreadgroup(
                        self.consumer_group,
                        self.consumer_name,
                        streams,
                        count=1,
                        block=1000
                    )
                    
                    if messages:
                        self.logger.info(f"📨 Received {len(messages)} stream(s) with messages")
                    
                    for stream_key, stream_messages in messages:
                        robot_name = stream_key.split(":")[-1]
                        self.logger.info(f"🤖 Processing {len(stream_messages)} message(s) for robot: {robot_name}")
                        
                        for message_id, fields in stream_messages:
                            try:
                                self.logger.info(f"📦 Processing message {message_id} from {stream_key}")
                                # ペイロードデコード
                                payload = json.loads(fields["payload"])
                                command_id = fields["command_id"]
                                
                                self.logger.info(f"📦 Processing command {command_id} for {robot_name}")
                                
                                # コマンド処理
                                success = callback_handler(robot_name, payload)
                                
                                if success:
                                    # 成功時：ACK送信と結果記録
                                    self.redis_client.xack(stream_key, self.consumer_group, message_id)
                                    self._record_command_result(robot_name, command_id, "success")
                                    self.logger.info(f"✅ Command {command_id} processed successfully")
                                else:
                                    # 失敗時：結果記録（ACKは送信せず、再処理可能に）
                                    self._record_command_result(robot_name, command_id, "error", "Command processing failed")
                                    self.logger.error(f"❌ Command {command_id} processing failed")
                                    
                            except Exception as e:
                                self.logger.error(f"💥 Error processing message {message_id}: {e}")
                                self._record_command_result(robot_name, fields.get("command_id", "unknown"), "error", str(e))
                                
                except redis.RedisError as e:
                    self.logger.error(f"💥 Redis error in consume loop: {e}")
                    time.sleep(5)  # エラー時は5秒待機
                    
        except Exception as e:
            self.logger.error(f"💥 Error in consume_commands: {e}")
    
    def _record_command_result(self, robot_name: str, command_id: str, result: str, error_msg: str = None):
        """コマンド実行結果をストリームに記録"""
        try:
            result_stream = f"robot:responses:{robot_name}"
            result_entry = {
                "command_id": command_id,
                "result": result,
                "timestamp": str(int(time.time()))
            }
            
            if error_msg:
                result_entry["error"] = error_msg
                
            self.redis_client.xadd(result_stream, result_entry, maxlen=1000)  # 最新1000件保持
            
        except Exception as e:
            self.logger.error(f"💥 Failed to record command result: {e}")
    
    def get_command_history(self, robot_name: str, limit: int = 100) -> list:
        """コマンド履歴取得"""
        try:
            stream_key = f"robot:commands:{robot_name}"
            messages = self.redis_client.xrevrange(stream_key, count=limit)
            
            history = []
            for message_id, fields in messages:
                history.append({
                    "message_id": message_id,
                    "command_id": fields.get("command_id"),
                    "command_type": fields.get("command_type"),
                    "status": fields.get("status"),
                    "created_at": fields.get("created_at"),
                    "payload": json.loads(fields.get("payload", "{}"))
                })
            
            return history
            
        except Exception as e:
            self.logger.error(f"💥 Failed to get command history: {e}")
            return []
    
    def get_command_status(self, robot_name: str, command_id: str) -> dict:
        """特定コマンドのステータス取得"""
        try:
            # レスポンススストリームから検索
            result_stream = f"robot:responses:{robot_name}"
            messages = self.redis_client.xrevrange(result_stream, count=100)
            
            for message_id, fields in messages:
                if fields.get("command_id") == command_id:
                    return {
                        "command_id": command_id,
                        "status": fields.get("result", "unknown"),
                        "timestamp": fields.get("timestamp"),
                        "error": fields.get("error")
                    }
            
            return {
                "command_id": command_id,
                "status": "pending",
                "timestamp": None,
                "error": None
            }
            
        except Exception as e:
            self.logger.error(f"💥 Failed to get command status: {e}")
            return {
                "command_id": command_id,
                "status": "error",
                "error": str(e)
            }
    
    def get_pending_commands(self, robot_name: str) -> list:
        """未処理コマンド取得"""
        try:
            stream_key = f"robot:commands:{robot_name}"
            pending = self.redis_client.xpending(stream_key, self.consumer_group)
            
            if pending["pending"] > 0:
                self.logger.warning(f"⚠️ Found {pending['pending']} pending commands for {robot_name}")
                
            return pending
            
        except Exception as e:
            self.logger.error(f"💥 Failed to get pending commands: {e}")
            return {}
    
    def stop(self):
        """ストリーム消費停止"""
        self._is_running = False
        self.logger.info("🛑 Redis Streams consumer stopped")

# グローバルインスタンス
redis_streams_manager = RedisStreamsManager()
