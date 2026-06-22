import logging
import sys

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """共通のロガー設定"""
    logger = logging.getLogger(name)
    
    # 既にハンドラが設定されている場合はスキップ
    if logger.handlers:
        return logger
    
    # ログレベル設定
    logger.setLevel(level)
    
    # コンソールハンドラを作成
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # フォーマット設定
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # ハンドラをロガーに追加
    logger.addHandler(handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """ロガーを取得"""
    return logging.getLogger(name)