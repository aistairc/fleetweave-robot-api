from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..deps.redis import get_redis
from ..deps.auth import verify_auth_with_ip_restriction, verify_auth_with_ip_restriction_safe
from ..schemas.robot_status import (
    RobotStatusResponse, 
    MapResponse, 
    BatteryResponse,
    NavigationStartRequest,
    NavigationStopRequest,
    ExtraToolRequest,
    RobotReserveRequest,
    RobotReleaseRequest,
    MapChangeRequest,
    AreaChangeRequest,
    CommandResponse,
    ExtraToolResponse,
    NavigationCompleteResponse,
    RobotReserveResponse,
    RobotReleaseResponse,
    RobotInfo,
    AvailableRobotsResponse,
    StandardResponse,
    SwitchSimRequest,
    SwitchSimResponse,
    create_error_response
)
from ...infra.redis.client import redis_streams_manager
from ...settings import AREA_MAP_NAMES
import json
import time
import uuid
import logging
import sys
from datetime import datetime, timedelta, timezone

router = APIRouter()

# ロガーの設定（強制的にINFOレベルでコンソール出力）
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ハンドラーがまだ設定されていない場合のみ追加
if not logger.handlers:
    # コンソールハンドラー追加
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # ルートログレベルも調整
    logging.getLogger().setLevel(logging.INFO)

# ISOタイムスタンプ
def now_iso_utc() -> str:
    return datetime.now(timezone.utc) \
        .isoformat(timespec="milliseconds") \
        .replace("+00:00", "Z")

@router.get("/robot_status", response_model=RobotStatusResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_status(
    request: Request,
    robot_name: str = Query(...), 
    redis=Depends(get_redis)
):
    """ロボットステータス取得API（エリア別IP制限付き）"""
    # ロボット名を使って認証チェック
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)
    
    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
        
    try:
        # リクエストデータをログ
        logger.info(f"get_robot_status called for robot_name: {robot_name}")
        # ロボットステータスをRedisから取得

        data = redis.hgetall(f"robot:status:{robot_name}")
        reserve_robot = redis.hgetall(f"robot:reservation:{robot_name}")
        taskList = redis.lrange(f"robot:tasks:{robot_name}", 0, -1)
        task_id = ""
        if not data:
            raise create_error_response(404, f"Robot '{robot_name}' not found")
        if len(taskList) == 0:
            taskList = []
        else:
            # アクティブなタスク（pending、running状態）のみを検索
            for task in taskList:
                task_id_str = task.decode() if isinstance(task, bytes) else task
                task_status = redis.hget(f"navigation:task:{task_id_str}", "status")
                if task_status:
                    status_str = task_status.decode() if isinstance(task_status, bytes) else task_status
                    if status_str in ["pending", "running"]:
                        task_id = task_id_str
                        break
        # positionを4要素の配列として返す（x, y, z, theta）
        position = [
            float(data.get("pos_x", 0)),
            float(data.get("pos_y", 0)),
            float(data.get("pos_z", 0)),  # z軸
            float(data.get("pos_theta", 0))   # theta（角度）
        ]

        # ロボット本来のマップ名を取得
        original_map_name = data.get("mapname", data.get("map_name", ""))
        
        # マップオーバーライド情報をチェック
        override_data = redis.hgetall(f"robot:map_override:{robot_name}")
        final_map_name = original_map_name
        
        if override_data and override_data.get("override_map_name"):
            final_map_name = override_data.get("override_map_name")
            # オーバーライド情報があることをログに記録
            logger.debug(f"Map override applied for {robot_name}: {original_map_name} -> {final_map_name}")

        return {
            "name": robot_name,
            "battery_soc": float(data.get("battery_soc", 0)),
            "mapname": "2F",  # オーバーライド情報があれば適用
            "position": position,  # スペル修正: posision -> position
            "status": data.get("status", "unknown"),
            "taskNo": reserve_robot.get("task_id", "") if reserve_robot else task_id,
            "fms_id": reserve_robot.get("fms_id", "") if reserve_robot else "",
            "robot_updatetime": data.get("updated_at", ""),
            "timestamp": now_iso_utc()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robot_map", response_model=MapResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_map(
    request: Request,
    robot_name: str = Query(...), 
    redis=Depends(get_redis)
):
    """ロボットの現在マップ取得API（エリア別IP制限付き）"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)
    
    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
        
    try:
        data = redis.hgetall(f"robot:status:{robot_name}")
        if not data:
            raise create_error_response(404, f"Robot '{robot_name}' not found")
        
        # ロボット本来のマップ名を取得
        original_map_name = data.get("map_name", "")
        
        # マップオーバーライド情報をチェック
        override_data = redis.hgetall(f"robot:map_override:{robot_name}")
        final_map_name = original_map_name
        
        if override_data and override_data.get("override_map_name"):
            final_map_name = override_data.get("override_map_name")
        
        return {
            "map_name": final_map_name
        }
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robot_battery", response_model=BatteryResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_battery(
    request: Request,
    robot_name: str = Query(...), 
    redis=Depends(get_redis)
):
    """ロボットのバッテリー残量取得API（エリア別IP制限付き）"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
        
    try:
        data = redis.hgetall(f"robot:status:{robot_name}")
        if not data:
            raise create_error_response(404, f"Robot '{robot_name}' not found")
        
        return {
            "battery_soc": float(data.get("battery_soc", 0))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/navigation_start", response_model=CommandResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def start_robot_navigation(
    request: Request,
    nav_request: NavigationStartRequest,
    redis=Depends(get_redis)
):
    """ロボットナビゲーション開始API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, nav_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        logger.info(f"Received navigation start request: {nav_request}")
        # ロボットの予約情報からtask_idとfms_idを取得
        reservation_data = redis.hgetall(f"robot:reservation:{nav_request.robot_name}")
        task_id = reservation_data.get("task_id") if reservation_data and reservation_data.get("task_id") else None
        fms_id = reservation_data.get("fms_id") if reservation_data and reservation_data.get("fms_id") else None
        
        # コマンドIDはtask_idを使用、なければ新しいUUIDを生成
        command_id = task_id if task_id else str(uuid.uuid4())
        
        # タスクを解析して適切なコマンドを送信
        navigation_tasks = [task for task in nav_request.tasks if task.name == "navigation_2d"]
        
        if len(navigation_tasks) == 1:
            # 1点のみ -> 2D移動コマンド
            task = navigation_tasks[0]
            command_data = {
                "command": "2d_goal",
                "command_id": command_id,
                "timestamp": int(time.time()),
                "robot_name": nav_request.robot_name,
                "x": task.navParam.x,
                "y": task.navParam.y,
                "z": 0.0,  # デフォルト値
                "t": task.navParam.theta
            }
            # task_idとfms_idがある場合は追加
            if task_id:
                command_data["task_id"] = task_id
            else:
                command_data["task_id"] = command_id  # 仮タスクIDを設定
            if fms_id:
                command_data["fms_id"] = fms_id
            
        elif len(navigation_tasks) > 1:
            # 複数ポイント -> 大局移動コマンド
            poses = []
            for task in navigation_tasks:
                poses.append({
                    "x": task.navParam.x,
                    "y": task.navParam.y,
                    "z": 0.0,  # デフォルト値
                    "t": task.navParam.theta
                })
            
            command_data = {
                "command": "2d_goal_plan",
                "command_id": command_id,
                "timestamp": int(time.time()),
                "robot_name": nav_request.robot_name,
                "pose": poses
            }
            # task_idとfms_idがある場合は追加
            if task_id:
                command_data["task_id"] = task_id
            else:
                command_data["task_id"] = command_id  # 仮タスクIDを設定
            if fms_id:
                command_data["fms_id"] = fms_id
            
        else:
            # 移動タスクがない場合は一般的なナビゲーションコマンドとして処理
            command_data = {
                "command": "navigation_start",
                "command_id": command_id,
                "timestamp": int(time.time()),
                "robot_name": nav_request.robot_name,
                "mode": nav_request.mode,
                "map_name": nav_request.map_name,
                "tasks": [task.dict() for task in nav_request.tasks]
            }
            # task_idとfms_idがある場合は追加
            if task_id:
                command_data["task_id"] = task_id
            else:
                command_data["task_id"] = command_id  # 仮タスクIDを設定
            if fms_id:
                command_data["fms_id"] = fms_id
        
        # Redis StreamsでGatewayに送信
        success = redis_streams_manager.add_command(nav_request.robot_name, command_data)
        
        if success:
            # 二重保護システム: ナビゲーションロック + recent_nav_start
            current_timestamp = str(time.time())
            
            # 第一層: ナビゲーションロック（20秒、より強固な保護）
            navigation_lock_key = f"robot:navigation_lock:{nav_request.robot_name}"
            redis.setex(navigation_lock_key, 20, current_timestamp)
            
            # 第二層: ナビゲーション開始時刻を記録（競合状態対策）
            recent_nav_start_key = f"robot:recent_nav_start:{nav_request.robot_name}"
            redis.setex(recent_nav_start_key, 15, current_timestamp)
            
            # 予約有無に関わらず、常にナビゲーションタスクを登録
            # これにより予約機能を使わない場合でも仮タスクIDで管理可能
            task_data = {
                "task_id": command_id,
                "robot_name": nav_request.robot_name,
                "mode": nav_request.mode,
                "map_name": nav_request.map_name,
                "tasks": [task.dict() for task in nav_request.tasks],
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "is_temporary": not bool(task_id),  # 予約なしの場合は仮タスクフラグ
                "original_task_id": task_id if task_id else None  # 元のタスクIDを保持
            }
            
            # タスクをRedisに保存
            redis.hset(f"navigation:task:{command_id}", mapping={
                "data": json.dumps(task_data),
                "status": "pending"
            })
            
            # ロボット別のタスクリストに追加（admin.pyと同じ処理）
            redis.lpush(f"robot:tasks:{nav_request.robot_name}", command_id)
            
            # ロボットのステータスを更新
            # redis.hset(f"robot:status:{nav_request.robot_name}", "status", "moving")
            
            return CommandResponse(
                status="command_sent",
                message=f"Navigation start command sent to robot {nav_request.robot_name}",
                robot_name=nav_request.robot_name,
                command_id=command_id,
                task_id=task_id if task_id else command_id
            )
        else:
            raise create_error_response(500, "Failed to send command to gateway")
            
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/navigation_stop", response_model=CommandResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def stop_robot_navigation(
    request: Request,
    nav_request: NavigationStopRequest,
    redis=Depends(get_redis)
):
    """ロボットナビゲーション停止API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, nav_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # requestのデバッグログ
        logger.info(f"Received navigation stop request: {nav_request}")
        # ロボットの予約情報からtask_idとfms_idを取得
        reservation_data = redis.hgetall(f"robot:reservation:{nav_request.robot_name}")
        task_id = reservation_data.get("task_id") if reservation_data and reservation_data.get("task_id") else None
        fms_id = reservation_data.get("fms_id") if reservation_data and reservation_data.get("fms_id") else None
        
        # 現在アクティブなタスクIDを取得してキャンセル対象とする
        command_id = task_id
        active_task_ids = redis.lrange(f"robot:tasks:{nav_request.robot_name}", 0, -1)
        
        # アクティブなタスクがある場合は最新のタスクIDを使用
        if active_task_ids:
            # 最新のタスク（リストの先頭）をキャンセル対象とする
            latest_task_id = active_task_ids[0].decode() if isinstance(active_task_ids[0], bytes) else active_task_ids[0]
            command_id = latest_task_id
        elif not task_id:
            # 予約もアクティブタスクもない場合は新規UUID
            command_id = str(uuid.uuid4())
        
        # Redis Streams でGatewayに送信
        command_data = {
            "command": "2d_goal_cancel",  # 統一されたコマンド名
            "command_id": command_id,
            "timestamp": int(time.time()),
            "robot_name": nav_request.robot_name
        }
        # task_idとfms_idがある場合は追加
        if task_id:
            command_data["task_id"] = task_id
        else:
            command_data["task_id"] = command_id  # 仮タスクIDを設定
        if fms_id:
            command_data["fms_id"] = fms_id
        
        success = redis_streams_manager.add_command(nav_request.robot_name, command_data)
        
        if success:
            # ナビゲーション停止時の保護システムクリーンアップ
            navigation_lock_key = f"robot:navigation_lock:{nav_request.robot_name}"
            recent_nav_start_key = f"robot:recent_nav_start:{nav_request.robot_name}"
            
            # 保護キーを削除してリソースを開放
            redis.delete(navigation_lock_key)
            redis.delete(recent_nav_start_key)
            
            # キャンセル対象タスクのステータスを即座に更新
            if active_task_ids:
                for active_task_id in active_task_ids:
                    task_id_str = active_task_id.decode() if isinstance(active_task_id, bytes) else active_task_id
                    # アクティブなタスクのステータスをキャンセル済みに更新
                    task_status = redis.hget(f"navigation:task:{task_id_str}", "status")
                    if task_status:
                        status_str = task_status.decode() if isinstance(task_status, bytes) else task_status
                        if status_str in ["pending", "running"]:
                            redis.hset(f"navigation:task:{task_id_str}", "status", "canceled")
        
            redis.hset(f"robot:status:{nav_request.robot_name}", "status", "idle")

            return CommandResponse(
                status="command_sent",
                message=f"Navigation stop command sent to robot {nav_request.robot_name}",
                robot_name=nav_request.robot_name,
                command_id=command_id,
                task_id=task_id if task_id else command_id
            )
        else:
            raise create_error_response(500, "Failed to send command to gateway")
            
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/robot_map_change", response_model=CommandResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def change_robot_map(
    request: Request,
    map_request: MapChangeRequest,
    redis=Depends(get_redis)
):
    """ロボットマップ変更API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, map_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # マップ名からエリア情報を取得
        area_info = None
        target_area = "maintenance"  # デフォルトエリア
        target_map_name = map_request.map_name  # リクエストされたマップ名をデフォルトとする
        
        # AREA_MAP_NAMESから対応するエリアとマップ名を検索
        for key, area_data in AREA_MAP_NAMES.items():
            if key == map_request.map_name or area_data["map_name"] == map_request.map_name:
                area_info = area_data
                target_area = area_data["area"]
                target_map_name = area_data["map_name"]
                break
        
        # エリア情報が見つからない場合はmaintenanceをデフォルトとする
        if not area_info and "maintenance" in AREA_MAP_NAMES:
            area_info = AREA_MAP_NAMES["maintenance"]
            target_area = "maintenance"
            target_map_name = AREA_MAP_NAMES["maintenance"]["map_name"]
            
        # ロボットの予約情報からtask_idとfms_idを取得
        reservation_data = redis.hgetall(f"robot:reservation:{map_request.robot_name}")
        task_id = reservation_data.get("task_id") if reservation_data and reservation_data.get("task_id") else None
        fms_id = reservation_data.get("fms_id") if reservation_data and reservation_data.get("fms_id") else None
        
        # コマンドIDはtask_idを使用、なければ新しいUUIDを生成
        command_id = task_id if task_id else str(uuid.uuid4())
        
        # マップオーバーライド情報を別途保存（ロボットの実際のステータスは変更しない）
        try:
            # logging for override process
            logger.info(f"Saving map override for robot {map_request.robot_name} to map {target_map_name} in area {target_area}")
            # 現在のロボットステータスを取得（参照のみ）
            status_key = f"robot:status:{map_request.robot_name}"
            current_status = redis.hgetall(status_key)
            current_map = current_status.get("mapname", "unknown") if current_status else "unknown"
            
            # マップオーバーライド情報を保存
            override_key = f"robot:map_override:{map_request.robot_name}"
            override_data = {
                "override_map_name": target_map_name,
                "override_area": target_area,
                "original_map": current_map,
                "override_timestamp": int(time.time()),
                "command_id": command_id
            }
            
            # オーバーライド情報をRedisに保存
            for key, value in override_data.items():
                redis.hset(override_key, key, value)
                
            # 変更履歴ログを作成
            status_log = {
                "timestamp": int(time.time()),
                "robot_name": map_request.robot_name,
                "action": "map_override",
                "from_map": current_map,
                "to_map": target_map_name,
                "to_area": target_area,
                "command_id": command_id,
                "type": "api_override"  # API側でのオーバーライドであることを明示
            }
            
            # ログを保存（最新30件まで保持）
            log_key = f"robot:map_change_log:{map_request.robot_name}"
            redis.lpush(log_key, json.dumps(status_log))
            redis.ltrim(log_key, 0, 29)  # 最新30件のみ保持
            
        except Exception as override_error:
            # オーバーライド保存エラーはログに記録するが、処理は継続
            logger.error(f"Failed to save map override for {map_request.robot_name}: {override_error}")
        
        # ロボット側でマップ切り替えは行わないため、Gateway送信部分はコメントアウト
        # Redis Pub/Sub でGatewayに送信
        # command_data = {
        #     "command": "robot_map_change",  # 統一されたコマンド名
        #     "command_id": command_id,
        #     "timestamp": int(time.time()),
        #     "robot_name": map_request.robot_name,
        #     "map_name": target_map_name,  # 決定されたマップ名を使用
        #     "target_area": target_area    # エリア情報も追加
        # }
        
        # # relocateデータがある場合のみ追加
        # if map_request.relocate:
        #     command_data["relocate"] = {
        #         "x": map_request.relocate.x,
        #         "y": map_request.relocate.y,
        #         "theta": map_request.relocate.theta
        #     }
        # # task_idとfms_idがある場合は追加
        # if task_id:
        #     command_data["task_id"] = task_id
        # if fms_id:
        #     command_data["fms_id"] = fms_id
        
        # success = redis_streams_manager.add_command(map_request.robot_name, command_data)
        
        # API側でmapnameのみ更新するため、常に成功として扱う
        success = True
        
        if success:
            return CommandResponse(
                status="map_changed",  # ステータス名を変更（実際のコマンド送信ではないため）
                message=f"Map name updated for robot {map_request.robot_name}. New map: {target_map_name} (area: {target_area})",
                robot_name=map_request.robot_name,
                command_id=command_id,
                task_id=task_id
            )
        else:
            raise create_error_response(500, "Failed to send command to gateway")
            
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robot_command_history", responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_command_history(
    request: Request,
    robot_name: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    redis=Depends(get_redis)
):
    """ロボットのコマンド履歴取得API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
    
    try:
        history = redis_streams_manager.get_command_history(robot_name, limit)
        return {
            "robot_name": robot_name,
            "command_history": history,
            "total_count": len(history)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robot_command_status", responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_command_status(
    request: Request,
    robot_name: str = Query(...),
    command_id: str = Query(...),
    redis=Depends(get_redis)
):
    """特定コマンドの実行ステータス取得API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
        
    if not command_id or command_id.strip() == "":
        raise create_error_response(400, "command_id parameter is required")
    
    try:
        status = redis_streams_manager.get_command_status(robot_name, command_id)
        return {
            "robot_name": robot_name,
            "command_status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robot_pending_commands", responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_pending_commands(
    request: Request,
    robot_name: str = Query(...),
    redis=Depends(get_redis)
):
    """ロボットの未処理コマンド取得API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
    
    try:
        pending = redis_streams_manager.get_pending_commands(robot_name)
        return {
            "robot_name": robot_name,
            "pending_commands": pending
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/extratool", response_model=ExtraToolResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def post_extra_tool(
    request: Request,
    tool_request: ExtraToolRequest,
    redis=Depends(get_redis)
):
    """アクション登録API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, tool_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # ロボットの予約情報からtask_idとfms_idを取得
        reservation_data = redis.hgetall(f"robot:reservation:{tool_request.robot_name}")
        task_id = reservation_data.get("task_id") if reservation_data and reservation_data.get("task_id") else None
        fms_id = reservation_data.get("fms_id") if reservation_data and reservation_data.get("fms_id") else None
        
        # コマンドIDはtask_idを使用、なければ新しいUUIDを生成
        command_id = task_id if task_id else str(uuid.uuid4())
        
        # Redis Pub/Sub でGatewayに送信
        command_data = {
            "command": "extra_tool",
            "command_id": command_id,
            "timestamp": int(time.time()),
            "robot_name": tool_request.robot_name,
            "tool": tool_request.tool
        }
        # task_idとfms_idがある場合は追加
        if task_id:
            command_data["task_id"] = task_id
        if fms_id:
            command_data["fms_id"] = fms_id
        
        success = redis_streams_manager.add_command(tool_request.robot_name, command_data)
        
        if success:
            return ExtraToolResponse(
                message=f"Extra tool command '{tool_request.tool}' sent to robot {tool_request.robot_name}",
                result=True
            )
        else:
            raise create_error_response(500, "Failed to send command to gateway")
            
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/job/navigation_iscomplate", response_model=NavigationCompleteResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_navigation_complete(
    request: Request,
    robot_name: str = Query(..., description="robot name"),
    redis=Depends(get_redis)
):
    """ナビゲーション完了確認API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)
    
    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
        
    try:
        logger.info(f"Checking navigation complete status for robot: {robot_name}")
        # ロボットの存在確認
        data = redis.hgetall(f"robot:status:{robot_name}")
        if not data:
            raise create_error_response(404, f"Robot '{robot_name}' not found")
        
        # ロボットのタスクリストを確認（admin.pyと同様の処理）
        task_ids = redis.lrange(f"robot:tasks:{robot_name}", 0, -1)
        # ロボットの現在のステータスを確認
        robot_status = data.get("status", "unknown")
        if isinstance(robot_status, bytes):
            robot_status = robot_status.decode()
        
        # ナビゲーション実行中を示すステータス
        navigation_active_statuses = ["moving", "moving_complete", "moving_complate", "moving_manual","working"]
        # ナビゲーション完了済みを示すステータス  
        navigation_complete_statuses = ["idle", "available"]
        
        # 複数層保護システム: recent_nav_start + navigation_lock
        recent_nav_start_key = f"robot:recent_nav_start:{robot_name}"
        navigation_lock_key = f"robot:navigation_lock:{robot_name}"
        
        # アクティブなナビゲーションロックをチェック
        navigation_lock = redis.get(navigation_lock_key)
        within_lock_window = False
        if navigation_lock:
            try:
                lock_timestamp = float(navigation_lock.decode() if isinstance(navigation_lock, bytes) else navigation_lock)
                current_timestamp = time.time()
                if (current_timestamp - lock_timestamp) < 20.0:  # 20秒のロック期間
                    within_lock_window = True
            except (ValueError, AttributeError):
                pass
        
        # 最近のナビゲーション開始リクエストをチェック（第二層保護）
        recent_nav_start = redis.get(recent_nav_start_key)
        within_navigation_start_window = False
        if recent_nav_start:
            try:
                start_timestamp = float(recent_nav_start.decode() if isinstance(recent_nav_start, bytes) else recent_nav_start)
                current_timestamp = time.time()
                if (current_timestamp - start_timestamp) < 15.0:  # 15秒の保護ウィンドウ
                    within_navigation_start_window = True
            except (ValueError, AttributeError):
                pass
        
        # 最優先でロック期間中は未完了を返す
        if within_lock_window:
            return NavigationCompleteResponse(
                message=f"Navigation complete status for {robot_name}: False (navigation lock active, lock protection window)",
                result=False
            )
        
        if not task_ids:
            # タスクがない場合の判定
            if within_navigation_start_window:
                # 最近ナビゲーション開始があった場合は処理中とみなす
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: False (recent navigation start within 15 seconds, robot status: {robot_status})",
                    result=False
                )
            elif robot_status in navigation_complete_statuses:
                # 完了時に保護キーをクリーンアップ
                redis.delete(navigation_lock_key)
                redis.delete(recent_nav_start_key)
                
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: True (robot status: {robot_status}, no tasks, no recent navigation start, protection cleaned up)",
                    result=True
                )
            else:
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: False (robot status: {robot_status}, no tasks but robot not idle)",
                    result=False
                )
        
        # アクティブなタスクがあるかチェック
        active_tasks = []
        for task_id in task_ids:
            task_status = redis.hget(f"navigation:task:{task_id}", "status")
            if task_status:
                status_str = task_status.decode() if isinstance(task_status, bytes) else task_status
                if status_str in ["pending", "running"]:
                    active_tasks.append({"task_id": task_id.decode() if isinstance(task_id, bytes) else task_id, "status": status_str})
        
        # すべてのタスクが完了している場合（admin.pyと同じロジック）
        if not active_tasks:
            # 完了した仮タスク（予約なしで作成されたタスク）があればリストから削除してリソースを開放
            completed_temp_tasks = []
            for task_id in task_ids:
                task_data_json = redis.hget(f"navigation:task:{task_id}", "data")
                if task_data_json:
                    try:
                        task_data = json.loads(task_data_json.decode() if isinstance(task_data_json, bytes) else task_data_json)
                        # 仮タスクかつ完了済みの場合、リストから削除
                        if task_data.get("is_temporary", False):
                            task_status = redis.hget(f"navigation:task:{task_id}", "status")
                            status_str = task_status.decode() if isinstance(task_status, bytes) else task_status
                            if status_str in ["completed", "failed", "canceled", "stopped"]:
                                completed_temp_tasks.append(task_id.decode() if isinstance(task_id, bytes) else task_id)
                    except (json.JSONDecodeError, AttributeError):
                        continue
            
            # 完了した仮タスクをリストから削除（開放）
            for temp_task_id in completed_temp_tasks:
                redis.lrem(f"robot:tasks:{robot_name}", 0, temp_task_id)
                # タスクデータも削除してリソースを開放
                redis.delete(f"navigation:task:{temp_task_id}")
            
            # タスクは全て完了しているが、ロボットステータスおよび開始タイミングに基づく最終判定
            if within_navigation_start_window:
                # 最近ナビゲーション開始があった場合は処理中とみなす（タスクリストの更新ラグ対策）
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: False (recent navigation start within 15 seconds, {len(completed_temp_tasks)} temp tasks released)",
                    result=False
                )
            elif robot_status in navigation_active_statuses:
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: False (robot status: {robot_status} indicates navigation still active, {len(completed_temp_tasks)} temp tasks released)",
                    result=False
                )
            elif robot_status in navigation_complete_statuses:
                # 完了時に保護キーをクリーンアップ
                redis.delete(navigation_lock_key)
                redis.delete(recent_nav_start_key)
                
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: True (robot status: {robot_status}, all navigation tasks completed, {len(completed_temp_tasks)} temp tasks released, protection cleaned up)",
                    result=True
                )
            else:
                # 不明なステータスの場合は保守的に未完了とする
                return NavigationCompleteResponse(
                    message=f"Navigation complete status for {robot_name}: False (unknown robot status: {robot_status}, being conservative)",
                    result=False
                )
        else:
            # アクティブなタスクがある場合は、必ず未完了とみなす
            # ロボットステータスと最近の開始情報も参考情報として含める
            active_task_info = ", ".join([f"{t['task_id']}({t['status']})" for t in active_tasks])
            start_info = "recent navigation start detected" if within_navigation_start_window else "no recent navigation start"
            return NavigationCompleteResponse(
                message=f"Navigation complete status for {robot_name}: False (active tasks: {active_task_info}, robot status: {robot_status}, {start_info})",
                result=False
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/robot_reserve", response_model=RobotReserveResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    409: {"model": dict, "description": "Conflict - Robot already reserved"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def reserve_robot(
    request: Request,
    reserve_request: RobotReserveRequest,
    redis=Depends(get_redis)
):
    """ロボット使用許可申請API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, reserve_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        logger.info(f"Received robot reserve request: {reserve_request}")
        # デバッグログ: リクエストデータを確認
        print(f"🔍 Debug - Reserve request data: task_id={reserve_request.task_id}")
        
        # ロボットが存在するかチェック
        robot_data = redis.hgetall(f"robot:status:{reserve_request.robot_name}")
        if not robot_data:
            raise create_error_response(404, f"Robot '{reserve_request.robot_name}' not found")
        
        # 既存の予約をチェック
        existing_reservation = redis.hgetall(f"robot:reservation:{reserve_request.robot_name}")
        if existing_reservation and existing_reservation.get("status") == "active":
            reserved_until = existing_reservation.get("end_time", "")
            if reserved_until and datetime.fromisoformat(reserved_until) > datetime.now():
                raise create_error_response(409, f"Robot '{reserve_request.robot_name}' is already reserved")
        
        # 予約ID生成
        reservation_id = str(uuid.uuid4())
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=reserve_request.duration or 60)
        
        # 予約データを保存
        reservation_data = {
            "reservation_id": reservation_id,
            "robot_name": reserve_request.robot_name,
            "user_id": reserve_request.user_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": str(reserve_request.duration or 600),
            "purpose": reserve_request.purpose or "",
            "task_id": reserve_request.task_id if reserve_request.task_id else "",
            "fms_id": reserve_request.fms_id or "",
            "status": "active",
            "created_at": start_time.isoformat()
        }
        
        redis.hset(f"robot:reservation:{reserve_request.robot_name}", mapping=reservation_data)
        
        # ロボットステータスを予約済みに更新
        redis.hset(f"robot:status:{reserve_request.robot_name}", "status", "reserved")
        redis.hset(f"robot:status:{reserve_request.robot_name}", "reserved_by", reserve_request.user_id)
        redis.hset(f"robot:status:{reserve_request.robot_name}", "reserved_until", end_time.isoformat())
        # fms_idもステータスに保存
        redis.hset(f"robot:status:{reserve_request.robot_name}", "fms_id", reserve_request.fms_id or "")
        
        return RobotReserveResponse(
            message=f"Robot '{reserve_request.robot_name}' reserved successfully",
            result=True,
            reservation_id=reservation_id,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robots/available", response_model=AvailableRobotsResponse, responses={
    401: {"model": dict, "description": "Unauthorized"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def get_available_robots(
    request: Request,
    redis=Depends(get_redis)
):
    """利用可能なロボットリスト取得API"""
    # 認証チェック（特定ロボット名は不要なのでNoneを渡す）
    auth_info = verify_auth_with_ip_restriction_safe(request, None)
    
    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # 全てのロボットのステータスを取得
        robot_keys = redis.keys("robot:status:*")
        robots = []
        available_count = 0
        
        for key in robot_keys:
            # キーが既に文字列の場合とbytesの場合を考慮
            if isinstance(key, bytes):
                robot_name = key.decode('utf-8').split(":")[-1]
            else:
                robot_name = str(key).split(":")[-1]
            
            robot_data = redis.hgetall(key)
            
            if not robot_data:
                continue
                
            # 予約情報を取得
            reservation_data = redis.hgetall(f"robot:reservation:{robot_name}")
            reserved_by = None
            reserved_until = None
            
            # ステータスの判定
            status = robot_data.get("status", "unknown")
            print(f"Robot: {robot_name}, Status: {status}")
            
            # 予約期限をチェック
            if reservation_data and reservation_data.get("status") == "active":
                end_time_str = reservation_data.get("end_time")
                if end_time_str:
                    try:
                        end_time = datetime.fromisoformat(end_time_str)
                        if end_time <= datetime.now():
                            # 期限切れの予約を削除
                            redis.delete(f"robot:reservation:{robot_name}")
                            redis.hset(f"robot:status:{robot_name}", "status", "idle")
                            redis.hdel(f"robot:status:{robot_name}", "reserved_by", "reserved_until")
                            status = "idle"
                        else:
                            reserved_by = reservation_data.get("user_id")
                            reserved_until = end_time_str
                            status = "reserved"
                    except ValueError:
                        # 不正な日時形式の場合は予約を削除
                        redis.delete(f"robot:reservation:{robot_name}")
            
            # ステータスによる分類
            if status in ["idle", "available"]:
                display_status = "available"
                available_count += 1
            elif status in ["working", "charging","moving"]:
                display_status = "busy"
            elif status == "reserved":
                display_status = "reserved"
            elif status == "error":
                display_status = "maintenance"
            else:
                display_status = "offline"
            
            robot_info = RobotInfo(
                robot_name=robot_name,
                status=display_status,
                battery_soc=float(robot_data.get("battery_soc", 0)),
                current_map=robot_data.get("map_name", ""),
                reserved_by=reserved_by,
                reserved_until=reserved_until,
                fms_id=robot_data.get("fms_id", None)
            )
            
            robots.append(robot_info)
        
        return AvailableRobotsResponse(
            robots=robots,
            total_count=len(robots),
            available_count=available_count
        )
        
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/robot_release", response_model=RobotReleaseResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    404: {"model": dict, "description": "Not Found - Invalid reservation"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def release_robot(
    request: Request,
    release_request: RobotReleaseRequest,
    redis=Depends(get_redis)
):
    """ロボット使用終了API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, release_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # デバッグログ: リクエストデータを確認
        logger.info(f"Received robot release request: {release_request}")
        # 予約情報を確認
        reservation_data = redis.hgetall(f"robot:reservation:{release_request.robot_name}")
        if not reservation_data:
            raise create_error_response(404, f"No active reservation found for robot '{release_request.robot_name}'")
        
        # ユーザーIDの確認（reservation_idが提供された場合は併せて確認）
        if reservation_data.get("user_id") != release_request.user_id:
            raise create_error_response(404, "Invalid user ID")
        
        # reservation_idが提供された場合は追加で確認
        # if (release_request.reservation_id and 
        #     reservation_data.get("reservation_id") != release_request.reservation_id):
        #     raise create_error_response(404, "Invalid reservation ID")
        
        if reservation_data.get("status") != "active":
            raise create_error_response(400, "Reservation is not active")
        
        # 予約を削除
        redis.delete(f"robot:reservation:{release_request.robot_name}")
        
        # ロボットステータスを更新
        redis.hset(f"robot:status:{release_request.robot_name}", "status", "idle")
        redis.hdel(f"robot:status:{release_request.robot_name}", "reserved_by", "reserved_until")
        
        return RobotReleaseResponse(
            message=f"Robot '{release_request.robot_name}' released successfully",
            result=True,
            reservation_id=reservation_data.get("reservation_id"),
            start_time=reservation_data.get("start_time"),
            end_time=reservation_data.get("end_time")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/area_change", response_model=CommandResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def change_robot_area(
    request: Request,
    area_request: AreaChangeRequest,
    redis=Depends(get_redis)
):
    """エリアスイッチAPI - FMS接続切り替え（ロボットマップ変更は別API）"""
    # 現在のエリアから指定エリアへの切り替えのためのIP制限チェック
    auth_info = verify_auth_with_ip_restriction_safe(request, area_request.robot_name)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # requestのデバッグログ
        logger.info(f"Received area change request: {area_request}")
        # ロボットが存在するかチェック
        robot_data = redis.hgetall(f"robot:status:{area_request.robot_name}")
        if not robot_data:
            raise create_error_response(404, f"Robot '{area_request.robot_name}' not found")
        
        # 現在のFMS接続情報とマップ情報を取得
        current_fms_id = robot_data.get("fms_id", "")
        current_area = robot_data.get("current_area", "")
        current_map = robot_data.get("mapname", "")
        
        # マップ名からエリア情報を取得（マップ切り替えAPIと同様の処理）
        area_info = None
        target_area = area_request.area if hasattr(area_request, 'area') else "maintenance"
        target_map_name = area_request.map if hasattr(area_request, 'map') and area_request.map else current_map
        
        # AREA_MAP_NAMESから対応するエリアとマップ名を検索
        for key, area_data in AREA_MAP_NAMES.items():
            if (key == target_map_name or area_data["map_name"] == target_map_name or 
                area_data["area"] == target_area):
                area_info = area_data
                target_area = area_data["area"]
                target_map_name = area_data["map_name"]
                break
        
        # エリア情報が見つからない場合はmaintenanceをデフォルトとする
        if not area_info and "maintenance" in AREA_MAP_NAMES:
            area_info = AREA_MAP_NAMES["maintenance"]
            target_area = "maintenance"
            target_map_name = AREA_MAP_NAMES["maintenance"]["map_name"]
        
        # コマンドIDを生成
        command_id = str(uuid.uuid4())
        
        # マップオーバーライド情報を保存（マップ切り替えAPIと同様）
        try:
            override_key = f"robot:map_override:{area_request.robot_name}"
            override_data = {
                "override_map_name": target_map_name,
                "override_area": target_area,
                "original_map": current_map,
                "override_timestamp": int(time.time()),
                "command_id": command_id,
                "source": "area_change"  # エリアチェンジAPIからの変更であることを記録
            }
            
            # オーバーライド情報をRedisに保存
            for key, value in override_data.items():
                redis.hset(override_key, key, value)
                
            # 変更履歴ログを作成
            status_log = {
                "timestamp": int(time.time()),
                "robot_name": area_request.robot_name,
                "action": "area_change_override",
                "from_map": current_map,
                "to_map": target_map_name,
                "from_area": current_area,
                "to_area": target_area,
                "from_fms": current_fms_id,
                "to_fms": area_request.fms_id,
                "command_id": command_id,
                "type": "api_override",
                "source": "area_change"
            }
            
            # ログを保存（最新30件まで保持）
            log_key = f"robot:map_change_log:{area_request.robot_name}"
            redis.lpush(log_key, json.dumps(status_log))
            redis.ltrim(log_key, 0, 29)  # 最新30件のみ保持
            
        except Exception as override_error:
            # オーバーライド保存エラーはログに記録するが、処理は継続
            logger.error(f"Failed to save map override for area change {area_request.robot_name}: {override_error}")
        
        # FMS接続情報とエリア情報を更新（従来通り）
        redis.hset(f"robot:status:{area_request.robot_name}", 
                  "fms_id", area_request.fms_id)
        redis.hset(f"robot:status:{area_request.robot_name}", 
                  "current_area", target_area)
        
        # ログ出力
        print(f"🔄 エリア切り替え: {area_request.robot_name}")
        print(f"   旧FMS: {current_fms_id} (エリア: {current_area}) マップ: {current_map}")
        print(f"   新FMS: {area_request.fms_id} (エリア: {target_area}) マップ: {target_map_name}")
        
        # エリア切り替えは常に成功として扱う（Redis Streamsには送信しない）
        success = True
        
        if success:
            return CommandResponse(
                status="area_switched",
                message=f"Area switched for robot {area_request.robot_name}. New FMS: {area_request.fms_id}, Area: {target_area}, Map: {target_map_name}",
                robot_name=area_request.robot_name,
                command_id=command_id,
                task_id=None
            )
        else:
            raise create_error_response(500, "Failed to send command to gateway")
            
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.get("/robot_area_info", responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def get_robot_area_info(
    request: Request,
    robot_name: str = Query(...), 
    redis=Depends(get_redis)
):
    """ロボットのエリア情報取得API"""
    auth_info = verify_auth_with_ip_restriction_safe(request, robot_name)
    
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    if not robot_name or robot_name.strip() == "":
        raise create_error_response(400, "robot_name parameter is required")
        
    try:
        data = redis.hgetall(f"robot:status:{robot_name}")
        if not data:
            raise create_error_response(404, f"Robot '{robot_name}' not found")

        # ロボット本来のマップ名とエリア情報
        original_map = data.get("mapname", "")
        
        # マップオーバーライド情報をチェック
        override_data = redis.hgetall(f"robot:map_override:{robot_name}")
        final_map = original_map
        final_area = "maintenance"  # デフォルト
        
        if override_data and override_data.get("override_map_name"):
            final_map = override_data.get("override_map_name")
            final_area = override_data.get("override_area", "maintenance")
        else:
            # オーバーライド情報がない場合は、元のマップ名からエリアを推定
            for key, area_data in AREA_MAP_NAMES.items():
                if key == original_map or area_data["map_name"] == original_map:
                    final_area = area_data["area"]
                    break
        
        # マップ切り替えログの履歴も取得
        log_key = f"robot:map_change_log:{robot_name}"
        recent_logs = redis.lrange(log_key, 0, 4)  # 最新5件
        change_history = []
        
        for log_entry in recent_logs:
            try:
                log_data = json.loads(log_entry)
                change_history.append({
                    "timestamp": log_data.get("timestamp"),
                    "from_map": log_data.get("from_map"),
                    "to_map": log_data.get("to_map"),
                    "from_area": log_data.get("from_area"),
                    "to_area": log_data.get("to_area"),
                    "command_id": log_data.get("command_id"),
                    "type": log_data.get("type", "unknown")
                })
            except json.JSONDecodeError:
                continue
        
        return {
            "robot_name": robot_name,
            "current_map": final_map,
            "current_area": final_area,
            "original_map": original_map,  # ロボット本来のマップ名も参考情報として返す
            "has_override": bool(override_data and override_data.get("override_map_name")),
            "override_timestamp": override_data.get("override_timestamp") if override_data else None,
            "available_areas": list(AREA_MAP_NAMES.keys()),
            "area_mappings": AREA_MAP_NAMES,
            "recent_changes": change_history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")

@router.post("/job/switch_sim", response_model=SwitchSimResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    500: {"model": dict, "description": "Internal Server Error"}
})
def switch_robot_sim(
    request: Request,
    sim_request: SwitchSimRequest,
    redis=Depends(get_redis)
):
    """SIMスイッチAPI"""
    auth_info = verify_auth_with_ip_restriction_safe(request, None)

    # 認証情報をチェック
    if not auth_info or not auth_info.get("valid", False):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Authentication required or invalid credentials",
                "result": False
            }
        )
    
    try:
        # SIMスイッチの状態をRedisに保存
        redis.set("system:sim_switch", "1" if sim_request.simSwitch else "0")

        # bashでSIMスイッチの状態を反映させるコマンドを実行
        import subprocess
        import os
        from pathlib import Path
        
        # スクリプトのパスを動的に決定
        current_file_dir = Path(__file__).parent.parent.parent.parent  # src/robotcloudapi/api/routers から4つ上
        sim_script_path = current_file_dir / "tests" / "mqtt_info" / "sim_switch.sh"
        
        if not sim_script_path.exists():
            raise create_error_response(500, f"Simulator script not found at {sim_script_path}")
        
        # 現在実行中のプロセスをチェック（重複防止）
        action = "on" if sim_request.simSwitch else "off"
        
        try:
            # バックグラウンドでスクリプト実行（非ブロッキング）
            process = subprocess.Popen(
                ["bash", str(sim_script_path), action], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 短時間待機してプロセス起動を確認
            import time
            time.sleep(2)  # 2秒待機
            
            # プロセスが異常終了していないかチェック
            if process.poll() is not None:
                # プロセスが既に終了（エラーの可能性）
                stdout, stderr = process.communicate()
                if process.returncode != 0:
                    error_msg = f"Simulator script failed with exit code {process.returncode}"
                    if stderr:
                        error_msg += f" Error: {stderr}"
                    raise create_error_response(500, error_msg)
                else:
                    # 正常終了（おそらく"off"コマンド）
                    print(f"Simulator script completed: {stdout}")
            else:
                # プロセスはまだ実行中（正常、"on"コマンドの場合）
                print(f"Simulator process started with PID: {process.pid}")
            
        except FileNotFoundError:
            raise create_error_response(500, "Bash shell not found. Please ensure bash is installed.")
        except Exception as proc_error:
            raise create_error_response(500, f"Process execution error: {str(proc_error)}")
        
        return SwitchSimResponse(
            message=f"SIM switch set to {'ON' if sim_request.simSwitch else 'OFF'} successfully",
            result=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Internal server error: {str(e)}")