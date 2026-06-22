from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi import HTTPException

class Position(BaseModel):
    x: float
    y: float
    theta: float

class NavParam(BaseModel):
    x: float
    y: float
    theta: float

class Task(BaseModel):
    name: str
    navParam: NavParam

class NavigationStartRequest(BaseModel):
    robot_name: str
    mode: Optional[str] = None
    map_name: Optional[str] = None
    tasks: List[Task]

class NavigationStopRequest(BaseModel):
    robot_name: str

class ExtraToolRequest(BaseModel):
    robot_name: str
    tool: str

class RobotReserveRequest(BaseModel):
    robot_name: str
    user_id: str
    duration: Optional[int] = None
    purpose: Optional[str] = None
    task_id: Optional[str] = Field(None, alias="taskid")
    fms_id: Optional[str] = None

    class Config:
        allow_population_by_field_name = True

class RobotReleaseRequest(BaseModel):
    robot_name: str
    user_id: str
    reservation_id: Optional[str] = None

class MapChangeRequest(BaseModel):
    robot_name: str
    map_name: str
    relocate: Optional[Position] = None

class AreaChangeRequest(BaseModel):
    robot_name: str
    area: str
    map: str
    fms_id: str

class CommandResponse(BaseModel):
    status: str
    message: str
    robot_name: str
    command_id: Optional[str] = None
    task_id: Optional[str] = None

class StandardResponse(BaseModel):
    message: str
    result: bool

class ExtraToolResponse(BaseModel):
    message: Optional[str] = None
    result:  bool

class NavigationCompleteResponse(BaseModel):
    message: str
    result: bool

class RobotReserveResponse(BaseModel):
    message: str
    result: bool
    reservation_id: str
    start_time: str
    end_time: str

class RobotReleaseResponse(BaseModel):
    message: str
    result: bool
    reservation_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class RobotInfo(BaseModel):
    robot_name: str
    status: str
    battery_soc: float
    current_map: str
    reserved_by: Optional[str] = None
    reserved_until: Optional[str] = None
    fms_id: Optional[str] = None

class AvailableRobotsResponse(BaseModel):
    robots: List[RobotInfo]
    total_count: int
    available_count: int

class ErrorResponse(BaseModel):
    message: str
    result: bool = False

class MapResponse(BaseModel):
    map_name: str

class BatteryResponse(BaseModel):
    battery_soc: float

class SwitchSimRequest(BaseModel):
    simSwitch: bool
    
class SwitchSimResponse(BaseModel):
    message: str
    result: bool

class RobotStatusResponse(BaseModel):
    name: str
    battery_soc: float
    mapname: str  # api.jsonに合わせてmapnameに変更
    position: List[float]  # api.jsonに合わせて4要素の配列に変更
    status: str
    taskNo: str  # api.jsonに合わせてcamelCaseに変更（文字列型）
    fms_id: Optional[str] = None  # FMS ID追加
    robot_updatetime: Optional[str] = None  # ロボットの最終更新時間追加
    timestamp: str  # ISO形式のタイムスタンプ


# エラーハンドリング用ユーティリティ関数
def create_error_response(status_code: int, message: str):
    """統一されたエラーレスポンスを作成"""
    return HTTPException(
        status_code=status_code,
        detail={
            "message": message,
            "result": False
        }
    )
