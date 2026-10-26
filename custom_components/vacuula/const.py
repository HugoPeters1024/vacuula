"""Constants for the Vacuula integration."""

DOMAIN = "vacuula"
POLL_INTERVAL_SECONDS = 60
ROBOT_COMMANDS = {
    "neato.gen3": {"cmd": "getRobotState"},
    "neato.gen4": {"ability": "state.show"},
}
