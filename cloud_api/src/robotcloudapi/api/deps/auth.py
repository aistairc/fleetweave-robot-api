from fastapi import HTTPException, Header, Request
from typing import Optional, Union, Dict
import base64
import binascii
from ...settings import AREA_IP_RESTRICTIONS, MAP_TO_AREA_MAPPING, POSITION_TO_AREA_MAPPING
from ..deps.redis import get_redis
import ipaddress

def verify_auth_with_ip_restriction(
    request: Request, 
    robot_name: Optional[str] = None,
    authorization: Optional[str] = Header(None)
) -> Dict[str, Union[str, bool]]:
    """認証トークンとIP制限を検証する（エリア管理付き）"""
    # 基本的な認証チェック
    auth_result = verify_auth_token(authorization)
    
    # IPアドレス取得
    client_ip = get_client_ip(request)
    
    # ロボット名が指定されている場合、エリア判定してIP制限をチェック
    if robot_name:
        area = determine_robot_area(robot_name)
        if area:
            check_ip_restriction(client_ip, area)
    
    # 認証結果に情報追加
    auth_result["client_ip"] = client_ip
    if robot_name:
        auth_result["robot_area"] = area
    
    return auth_result

def verify_auth_token(authorization: Optional[str] = Header(None)) -> Dict[str, Union[str, bool]]:
    """認証トークンを検証する（Bearer認証とBasic認証の両方に対応）"""
    print(f"DEBUG: verify_auth_token called with: {authorization}")
    
    if not authorization:
        print("DEBUG: Authorization is None or empty")
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authorization header is missing",
                "result": False
            }
        )
    
    # Bearer認証の場合
    if authorization.startswith("Bearer "):
        print("DEBUG: Bearer authentication detected")
        return _verify_bearer_token(authorization)
    
    # Basic認証の場合
    elif authorization.startswith("Basic "):
        print("DEBUG: Basic authentication detected")
        return _verify_basic_auth(authorization)
    
    # 無効な認証形式
    else:
        print(f"DEBUG: Invalid auth format: {authorization}")
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Invalid authorization format. Expected 'Bearer <token>' or 'Basic <credentials>'",
                "result": False
            }
        )

def get_client_ip(request: Request) -> str:
    """クライアントIPアドレスを取得"""
    # X-Forwarded-Forヘッダーをチェック（プロキシ経由の場合）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # X-Real-IPヘッダーをチェック
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # ダイレクト接続のIPアドレス
    return request.client.host

def determine_robot_area(robot_name: str) -> str:
    """ロボット名から現在のエリアを判定"""
    try:
        redis_client = get_redis()
        robot_data = redis_client.hgetall(f"robot:status:{robot_name}")
        
        if not robot_data:
            # ロボットが見つからない場合はデフォルトエリア
            return "area_a"
        
        # 1. マップ名からエリア判定
        map_name = robot_data.get("map_name", "")
        if map_name in MAP_TO_AREA_MAPPING:
            return MAP_TO_AREA_MAPPING[map_name]
        
        # 2. ロボット位置からエリア判定
        try:
            pos_x = float(robot_data.get("pos_x", 0))
            pos_y = float(robot_data.get("pos_y", 0))
            
            for area, position_range in POSITION_TO_AREA_MAPPING.items():
                x_min, x_max = position_range["x_range"]
                y_min, y_max = position_range["y_range"]
                
                if x_min <= pos_x <= x_max and y_min <= pos_y <= y_max:
                    return area
        except (ValueError, TypeError):
            pass
        
        # デフォルトエリア
        return "area_a"
        
    except Exception:
        # Redis接続エラーなどの場合はデフォルトエリア
        return "area_a"

def check_ip_restriction(client_ip: str, area: str):
    """指定されたエリアのIP制限をチェック"""
    print(f"DEBUG: check_ip_restriction called with IP: {client_ip}, area: {area}")
    
    if area not in AREA_IP_RESTRICTIONS:
        print(f"DEBUG: Unknown area: {area}")
        print(f"DEBUG: Available areas: {list(AREA_IP_RESTRICTIONS.keys())}")
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"Unknown area: {area}",
                "result": False
            }
        )
    
    allowed_ips = AREA_IP_RESTRICTIONS[area]["allowed_ips"]
    print(f"DEBUG: Allowed IPs for area {area}: {allowed_ips}")
    
    # IPアドレスのチェックを実行
    is_allowed = is_ip_allowed(client_ip, allowed_ips)
    print(f"DEBUG: IP {client_ip} allowed: {is_allowed}")
    
    if not is_allowed:
        area_description = AREA_IP_RESTRICTIONS[area]["description"]
        print(f"DEBUG: Access denied for IP {client_ip} in area {area}")
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"Access denied. IP {client_ip} is not allowed in {area_description}",
                "result": False
            }
        )
    
    print(f"DEBUG: IP restriction check passed for {client_ip} in area {area}")

def is_ip_allowed(client_ip: str, allowed_ips: list) -> bool:
    """クライアントIPが許可リストに含まれるかチェック"""
    try:
        client_addr = ipaddress.ip_address(client_ip)
        
        for allowed_ip in allowed_ips:
            try:
                # CIDR表記をサポート
                if "/" in allowed_ip:
                    allowed_network = ipaddress.ip_network(allowed_ip, strict=False)
                    if client_addr in allowed_network:
                        return True
                else:
                    # 個別IPアドレス
                    allowed_addr = ipaddress.ip_address(allowed_ip)
                    if client_addr == allowed_addr:
                        return True
            except ValueError:
                # 無効なIPアドレスはスキップ
                continue
        
        return False
    except ValueError:
        # 無効なクライアントIPの場合は拒否
        return False

def _verify_bearer_token(authorization: str) -> Dict[str, Union[str, bool]]:
    """Bearerトークンの検証"""
    token = authorization.replace("Bearer ", "")
    
    # 有効なトークンリスト（実際の環境ではJWTやAPIキーの検証を行う）
    valid_tokens = [
        "robot_api_token_example",
        "test_token",
        "admin_token_456",
        "robot_control_token_789"
    ]
    
    if token not in valid_tokens:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Invalid or expired Bearer token",
                "result": False
            }
        )
    
    return {
        "auth_type": "bearer",
        "token": token,
        "valid": True
    }

def _verify_basic_auth(authorization: str) -> Dict[str, Union[str, bool]]:
    """Basic認証の検証"""
    try:
        print(f"DEBUG: _verify_basic_auth called with: {authorization}")
        
        # "Basic "を削除してbase64デコード
        encoded_credentials = authorization.replace("Basic ", "")
        print(f"DEBUG: Encoded credentials: {encoded_credentials}")
        
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        print(f"DEBUG: Decoded credentials: {decoded_credentials}")
        
        # username:passwordの形式をパース
        if ':' not in decoded_credentials:
            print("DEBUG: No colon found in decoded credentials")
            raise HTTPException(
                status_code=401,
                detail={
                    "message": "Invalid Basic auth format. Expected 'username:password'",
                    "result": False
                }
            )
        
        username, password = decoded_credentials.split(':', 1)
        print(f"DEBUG: Username: {username}, Password: {password}")
        
        # 有効なユーザー認証情報（実際の環境ではデータベースやLDAPで検証）
        valid_users = {
            "admin": "admin123",
            "robot_user": "robot_pass",
            "robot_operator": "robot123",
            "test_user": "test_pass"
        }
        
        if username not in valid_users or valid_users[username] != password:
            print(f"DEBUG: Invalid credentials. Username in valid_users: {username in valid_users}")
            print(f"DEBUG: Password match: {valid_users.get(username) == password}")
            raise HTTPException(
                status_code=401,
                detail={
                    "message": "Invalid username or password",
                    "result": False
                }
            )
        
        print("DEBUG: Basic auth successful!")
        return {
            "auth_type": "basic",
            "username": username,
            "valid": True
        }
        
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Invalid Base64 encoding in Basic auth credentials",
                "result": False
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail={
                "message": f"Basic authentication failed: {str(e)}",
                "result": False
            }
        )

# 認証不要のエンドポイント用（オプション）
def optional_auth(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Union[str, bool]]]:
    """オプション認証（認証があれば検証、なければNone）"""
    if authorization:
        return verify_auth_token(authorization)
    return None

def verify_auth_with_ip_restriction_safe(
    request: Request, 
    robot_name: Optional[str] = None
) -> Optional[Dict[str, Union[str, bool]]]:
    """認証トークンとIP制限を検証する（例外なしバージョン）"""
    try:
        # Authorizationヘッダーを取得（大文字小文字を考慮）
        authorization = request.headers.get("Authorization") or request.headers.get("authorization")
        
        # デバッグ: ヘッダー情報をログ出力
        print(f"DEBUG: All headers: {dict(request.headers)}")
        print(f"DEBUG: Authorization header: {authorization}")
        
        # 基本的な認証チェック
        if not authorization:
            print("DEBUG: No authorization header found")
            return None
            
        print(f"DEBUG: Calling verify_auth_token with: {authorization}")
        try:
            auth_result = verify_auth_token(authorization)
            print(f"DEBUG: verify_auth_token returned: {auth_result}")
        except Exception as e:
            print(f"DEBUG: verify_auth_token failed with exception: {type(e).__name__}: {e}")
            return None
        
        # IPアドレス取得
        client_ip = get_client_ip(request)
        print(f"DEBUG: Client IP: {client_ip}")
        
        # ロボット名が指定されている場合、エリア判定してIP制限をチェック
        if robot_name:
            print(f"DEBUG: Robot name specified: {robot_name}")
            area = determine_robot_area(robot_name)
            print(f"DEBUG: Determined area: {area}")
            if area:
                print(f"DEBUG: Checking IP restriction for area: {area}")
                try:
                    check_ip_restriction(client_ip, area)
                    print(f"DEBUG: IP restriction check passed for {client_ip} in area {area}")
                except Exception as e:
                    print(f"DEBUG: IP restriction check failed: {type(e).__name__}: {e}")
                    raise
        else:
            print("DEBUG: No robot name specified - skipping IP restriction check")
            area = None
        
        # 認証結果に情報追加
        auth_result["client_ip"] = client_ip
        if robot_name:
            auth_result["robot_area"] = area
        
        print(f"DEBUG: Final auth result: {auth_result}")
        return auth_result
        
    except HTTPException:
        # 認証エラーの場合はNoneを返す（例外は発生させない）
        return None
    except Exception:
        # その他のエラーの場合もNoneを返す
        return None