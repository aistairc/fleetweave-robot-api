from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..deps.redis import get_redis
from ..deps.auth import verify_auth_with_ip_restriction, verify_auth_with_ip_restriction_safe
from ..schemas.robot_status import (
    NavigationStartRequest, 
    NavigationStopRequest, 
    MapChangeRequest,
    StandardResponse,
    create_error_response
)
import json
import uuid
from datetime import datetime

router = APIRouter()

@router.post("/navigation_start", response_model=StandardResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def post_navigation_start(
    request: Request,
    nav_request: NavigationStartRequest, 
    redis=Depends(get_redis)
):
    """ナビゲーションスタート登録API（エリア別IP制限付き）"""
    # ロボット名を使ってIP制限チェック
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
        # リクエストバリデーション
        if not nav_request.robot_name or nav_request.robot_name.strip() == "":
            raise create_error_response(400, "robot_name is required")
        
        if not nav_request.tasks or len(nav_request.tasks) == 0:
            raise create_error_response(400, "At least one task is required")
        
        # タスクをRedisに保存
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "robot_name": nav_request.robot_name,
            "mode": nav_request.mode,
            "map_name": nav_request.map_name,
            "tasks": [task.dict() for task in nav_request.tasks],
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        
        # タスクキューに追加
        redis.hset(f"navigation:task:{task_id}", mapping={
            "data": json.dumps(task_data),
            "status": "pending"
        })
        
        # ロボット別のタスクリストに追加
        redis.lpush(f"robot:tasks:{nav_request.robot_name}", task_id)
        
        # ロボットのステータスを更新
        redis.hset(f"robot:status:{nav_request.robot_name}", "status", "working")
        
        return {
            "message": "Navigation task registered successfully",
            "result": True
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "message": f"Failed to register navigation task: {str(e)}",
            "result": False
        }

@router.post("/navigation_stop", response_model=dict, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def post_navigation_stop(
    request: Request,
    stop_request: NavigationStopRequest, 
    redis=Depends(get_redis)
):
    """ナビゲーションストップ登録API（エリア別IP制限付き）"""
    auth_info = verify_auth_with_ip_restriction_safe(request, stop_request.robot_name)
    
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
        if not stop_request.robot_name or stop_request.robot_name.strip() == "":
            raise create_error_response(400, "robot_name is required")
            
        # 実行中のタスクを停止
        task_keys = redis.keys(f"navigation:task:*")
        for task_key in task_keys:
            task_data_str = redis.hget(task_key, "data")
            if task_data_str:
                task_data = json.loads(task_data_str)
                if (task_data["robot_name"] == stop_request.robot_name and 
                    task_data["status"] in ["pending", "running"]):
                    redis.hset(task_key, "status", "stopped")
        
        # ロボットのステータスを更新
        redis.hset(f"robot:status:{stop_request.robot_name}", "status", "idle")
        
        return {}
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Failed to stop navigation: {str(e)}")

@router.get("/navigation_iscomplate", response_model=StandardResponse, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"}
})
def get_navigation_iscomplate(
    request: Request,
    robot_name: str = Query(...), 
    redis=Depends(get_redis)
):
    """ナビゲーション完了確認API（エリア別IP制限付き）"""
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
    
    try:
        if not robot_name or robot_name.strip() == "":
            raise create_error_response(400, "robot_name parameter is required")
            
        # ロボットのタスクリストを確認
        task_ids = redis.lrange(f"robot:tasks:{robot_name}", 0, -1)
        
        # アクティブなタスクがあるかチェック
        has_active_tasks = False
        for task_id in task_ids:
            task_status = redis.hget(f"navigation:task:{task_id}", "status")
            if task_status and task_status.decode() in ["pending", "running"]:
                has_active_tasks = True
                break
        
        # すべてのタスクが完了している場合, if not has_active_tasks は　Falseを返す
        if not has_active_tasks:
            return {
                "message": "All navigation tasks completed",
                "result": True
            }
        else:
            return {
                "message": "Navigation tasks still in progress",
                "result": False
            }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "message": f"Failed to check navigation status: {str(e)}",
            "result": False
        }

@router.post("/robot_map_change", response_model=dict, responses={
    400: {"model": dict, "description": "Bad Request"},
    401: {"model": dict, "description": "Unauthorized"},
    403: {"model": dict, "description": "Forbidden - IP not allowed in area"},
    404: {"model": dict, "description": "Not Found"}
})
def post_robot_map_change(
    request: Request,
    map_request: MapChangeRequest, 
    redis=Depends(get_redis)
):
    """ロボットのマップ変更API（エリア別IP制限付き）"""
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
        if not map_request.robot_name or map_request.robot_name.strip() == "":
            raise create_error_response(400, "robot_name is required")
        
        if not map_request.map_name or map_request.map_name.strip() == "":
            raise create_error_response(400, "map_name is required")
            
        # マップ変更タスクをRedisに保存
        map_change_data = {
            "robot_name": map_request.robot_name,
            "new_map_name": map_request.map_name,
            "relocate_position": {
                "x": map_request.relocate.x,
                "y": map_request.relocate.y,
                "theta": map_request.relocate.theta
            },
            "created_at": datetime.now().isoformat()
        }
        
        # マップ変更コマンドをキューに追加
        redis.lpush(f"robot:map_change:{map_request.robot_name}", json.dumps(map_change_data))
        
        # ロボットのステータスを更新
        redis.hset(f"robot:status:{map_request.robot_name}", mapping={
            "map_name": map_request.map_name,
            "pos_x": str(map_request.relocate.x),
            "pos_y": str(map_request.relocate.y),
            "pos_theta": str(map_request.relocate.theta),
            "status": "relocating"
        })
        
        return {}
    except HTTPException:
        raise
    except Exception as e:
        raise create_error_response(500, f"Failed to change robot map: {str(e)}")