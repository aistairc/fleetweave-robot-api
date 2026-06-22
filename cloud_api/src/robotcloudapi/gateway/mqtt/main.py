"""
MQTT Gateway メインプログラム
"""
import time
from .client import create_client
from .subscribe import on_message
from ...common.logging import get_logger

logger = get_logger("mqtt_gateway")

def start_mqtt_gateway():
    """MQTTゲートウェイを開始"""
    try:
        logger.info("🚀 Starting MQTT Gateway...")
        
        client = create_client(on_message)
        
        # ロボットステータスの購読（レガシートピック）
        client.subscribe("robot/+/status")
        logger.info("📡 Subscribed to legacy topics: robot/+/status")
        
        # ロボットステータスの購読（zenohスタイルトピック）
        client.subscribe("/+/robotstatus")
        logger.info("📡 Subscribed to zenoh-style topics: /+/robotstatus")
        
        # レスポンストピックの購読（zenohスタイル）
        response_topics = [
            "/+/robotmodechange/response",
            "/+/robotmapchange/response", 
            "/+/2dgoal/response",
            "/+/2dgoalplan/response",
            "/+/2dgoalcancel/response",
            "/+/initialpose/response"
        ]
        
        for topic in response_topics:
            client.subscribe(topic)
            logger.info(f"📡 Subscribed to response topic: {topic}")
        
        client.loop_start()
        logger.info("✅ MQTT Gateway started successfully")
        
        return client
        
    except Exception as e:
        logger.error(f"💥 Failed to start MQTT Gateway: {e}")
        raise

def main():
    """メイン関数"""
    client = start_mqtt_gateway()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down MQTT Gateway...")
        client.loop_stop()
        client.disconnect()
        logger.info("👋 MQTT Gateway stopped")

if __name__ == "__main__":
    main()