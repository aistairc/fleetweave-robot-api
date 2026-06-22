import asyncio
import zenoh
from typing import Optional
from ...settings import ZENOH_HOST, ZENOH_PORT, ZENOH_CONFIG
from ...common.logging import get_logger
from .sesstion import initialize_zenoh_session, cleanup_zenoh_session
from .subscribe import start_zenoh_robot_monitoring, stop_zenoh_robot_monitoring
from .publisher import get_zenoh_publisher

logger = get_logger("gateway.zenoh")

class ZenohGateway:
    """Zenoh Gateway メインクラス"""
    
    def __init__(self, config: Optional[dict] = None):
        """Zenoh Gatewayを初期化
        
        Args:
            config: Zenoh設定辞書（Noneの場合はデフォルト設定を使用）
        """
        self.config = config or self._get_default_config()
        self.session = None
        self.is_running = False
        self.monitoring_task = None
    
    def _get_default_config(self) -> dict:
        """デフォルトのZenoh設定を取得
        
        Returns:
            デフォルトのZenoh設定辞書
        """
        try:
            # settings.pyから設定を読み込み（存在しない場合はデフォルト値）
            host = getattr(__import__('...settings', fromlist=['ZENOH_HOST']), 'ZENOH_HOST', 'localhost')
            port = getattr(__import__('...settings', fromlist=['ZENOH_PORT']), 'ZENOH_PORT', 7447)
            
            return {
                "connect/endpoints": [f"tcp/{host}:{port}"]
            }
        except:
            # フォールバック設定
            return {
                "connect/endpoints": ["tcp/localhost:7447"]
            }
    
    async def start(self):
        """Zenoh Gatewayを開始"""
        try:
            logger.info("🚀 Starting Zenoh Gateway...")
            
            # Zenohセッションを初期化
            self.session = await initialize_zenoh_session(self.config)
            logger.info("✅ Zenoh session initialized")
            
            # ロボット監視を開始
            start_zenoh_robot_monitoring()
            logger.info("🤖 Robot monitoring started")
            
            self.is_running = True
            logger.info("🎉 Zenoh Gateway started successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to start Zenoh Gateway: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Zenoh Gatewayを停止"""
        try:
            logger.info("🛑 Stopping Zenoh Gateway...")
            
            # ロボット監視を停止
            stop_zenoh_robot_monitoring()
            logger.info("🤖 Robot monitoring stopped")
            
            # Zenohセッションをクリーンアップ
            await cleanup_zenoh_session()
            logger.info("✅ Zenoh session cleaned up")
            
            self.session = None
            self.is_running = False
            logger.info("🎉 Zenoh Gateway stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to stop Zenoh Gateway: {e}")
    
    async def run_forever(self):
        """Zenoh Gatewayを永続的に実行"""
        try:
            await self.start()
            
            logger.info("🔄 Zenoh Gateway running indefinitely...")
            logger.info("Press Ctrl+C to stop")
            
            # 無限ループで動作継続
            while self.is_running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("⚠️ Received interrupt signal")
        except Exception as e:
            logger.error(f"💥 Zenoh Gateway error: {e}")
        finally:
            await self.stop()
    
    def get_publisher(self):
        """Zenohパブリッシャーを取得
        
        Returns:
            ZenohPublisherインスタンス
        """
        return get_zenoh_publisher()
    
    async def send_command_to_robot(self, robot_name: str, command: dict):
        """ロボットにコマンドを送信
        
        Args:
            robot_name: ロボット名
            command: 送信するコマンド辞書
        """
        if not self.is_running:
            raise RuntimeError("Zenoh Gateway is not running")
        
        publisher = self.get_publisher()
        publisher.publish_robot_command(robot_name, command)
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのイグジット"""
        await self.stop()

# Zenoh Gateway の実行用関数
async def run_zenoh_gateway(config: Optional[dict] = None):
    """Zenoh Gatewayを実行
    
    Args:
        config: Zenoh設定辞書
    """
    gateway = ZenohGateway(config)
    await gateway.run_forever()

def main():
    """メイン関数（コマンドライン実行用）"""
    try:
        asyncio.run(run_zenoh_gateway())
    except KeyboardInterrupt:
        logger.info("🛑 Zenoh Gateway stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")

if __name__ == "__main__":
    main()