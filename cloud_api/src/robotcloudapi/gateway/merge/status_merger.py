from ...domain.models.robot import RobotStatus
from ...common.time import now_iso

def merge(old: dict, new: RobotStatus) -> dict:
    for k, v in new.__dict__.items():
        if v is not None:
            old[k] = v
    old["updated_at"] = now_iso()
    return old
