from dataclasses import dataclass
# pylint: disable=too-few-public-methods
@dataclass
class RobotStatus:
    name: str
    battery_soc: float | None = None
    map_name: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    pos_z: float | None = None  # z座標を追加
    pos_theta: float | None = None
    pos_w: float | None = None  # クォータニオンのw成分を追加
    status: str | None = None
    mode: int | None = None
    task_no: str | None = None
