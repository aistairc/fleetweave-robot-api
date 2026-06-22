import zenoh
from typing import Optional
from ...common.logging import get_logger

logger = get_logger("gateway.zenoh.session")

class ZenohSession:
    """Zenohセッションを管理するクラス"""
    
    def __init__(self, config: Optional[dict] = None):
        """Zenohセッションを初期化
        
        Args:
            config: Zenohの設定辞書（Noneの場合はデフォルト設定を使用）
        """
        self.config = config or {}
        self.session: Optional[zenoh.Session] = None
        
    async def open(self):
        """Zenohセッションを開く"""
        try:
            logger.info("🔌 Opening Zenoh session...")
            self.session = zenoh.open(self.config)
            logger.info("✅ Zenoh session opened successfully")
            return self.session
        except Exception as e:
            logger.error(f"❌ Failed to open Zenoh session: {e}")
            raise
    
    async def close(self):
        """Zenohセッションを閉じる"""
        if self.session:
            try:
                logger.info("🔌 Closing Zenoh session...")
                self.session.close()
                self.session = None
                logger.info("✅ Zenoh session closed successfully")
            except Exception as e:
                logger.error(f"❌ Failed to close Zenoh session: {e}")
                raise
    
    def get_session(self) -> zenoh.Session:
        """現在のセッションを取得
        
        Returns:
            アクティブなZenohセッション
            
        Raises:
            RuntimeError: セッションが開かれていない場合
        """
        if not self.session:
            raise RuntimeError("Zenoh session is not opened. Call open() first.")
        return self.session
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        await self.open()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのイグジット"""
        await self.close()

# グローバルセッションインスタンス
_global_session: Optional[ZenohSession] = None

def get_zenoh_session() -> ZenohSession:
    """グローバルZenohセッションを取得
    
    Returns:
        グローバルZenohセッションインスタンス
    """
    global _global_session
    if _global_session is None:
        _global_session = ZenohSession()
    return _global_session

async def initialize_zenoh_session(config: Optional[dict] = None) -> ZenohSession:
    """Zenohセッションを初期化
    
    Args:
        config: Zenoh設定辞書
        
    Returns:
        初期化されたZenohセッション
    """
    global _global_session
    _global_session = ZenohSession(config)
    await _global_session.open()
    return _global_session

async def cleanup_zenoh_session():
    """Zenohセッションをクリーンアップ"""
    global _global_session
    if _global_session:
        await _global_session.close()
        _global_session = None