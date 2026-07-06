from app.models.delivery import RobotStatus, Status

_ROBOT_TRANSITIONS: dict[RobotStatus, Status] = {
    RobotStatus.MOVING: Status.REQUESTED,
    RobotStatus.ARRIVED: Status.MOVING,
}


def robot_status_required_current(target: RobotStatus) -> Status:
    return _ROBOT_TRANSITIONS[target]


def robot_target_as_status(target: RobotStatus) -> Status:
    return Status(target.value)
