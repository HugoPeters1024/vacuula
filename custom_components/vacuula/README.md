# Vacuula integration for Home Assistant

This custom integration adds Battery, Charging, Docked, and Problem sensors for each Gen3 or Gen4 robot registered with Vacuula.
It connects directly to the existing Vacuula HTTP API and works with the add-on, Docker, and standalone installations.
The add-on runs the server. This integration runs in Home Assistant and creates the devices and entities.

## Installation

1. Copy this `vacuula` directory into your Home Assistant configuration directory at `custom_components/vacuula`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Select **Vacuula**.
5. Enter the direct URL of your Vacuula web app, such as `http://192.168.1.50:80`.

For the add-on, the URL uses the Home Assistant host's LAN address and the add-on's `VACUULA_PORT` value.
The default port is `80`. The Home Assistant UI port (`8123`) and ingress URL are not Vacuula API addresses.

This integration requires no MQTT broker or additional add-on permissions.
It is a custom integration, not a built-in Home Assistant integration or a published HACS package.

## Sensors

Each robot gets one device with these sensors:

| Sensor | Meaning |
| --- | --- |
| Battery | Battery percentage |
| Charging | Whether the battery is charging |
| Docked | Whether the robot is on its base |
| Problem | Whether the robot reports an error state, error, or alert |

The Problem sensor includes an `error_codes` attribute with the reported error and alert codes.
Gen4 warnings also turn this sensor on. Missing or malformed fields make the affected sensor unavailable.
All four sensors share one status request per robot during each poll.
Serial numbers identify the devices and entities, so changing a robot's name does not create another sensor.
The integration polls every 60 seconds, even when the Vacuula web app is closed.
Robots paired later appear automatically on the next successful poll.

A disconnected robot or failed command makes all that robot's sensors unavailable.
A server failure makes all its sensors unavailable. Sensors recover after the next successful poll.
An empty robot inventory is valid, so the integration can be configured before pairing a robot.

Vacuum controls and automatic server discovery remain future work.
Device names are read when entities are created. Reload the integration after renaming a robot in Vacuula.

## Troubleshooting

If setup fails, check that the direct Vacuula URL opens from the Home Assistant network.
The `/api/robots` endpoint must return a JSON object.
If one sensor is unavailable, check that its robot is connected in the Vacuula web app.

To remove the integration, delete its entry under **Settings → Devices & services → Vacuula**.
The Vacuula server and its robot registrations remain available.

## Development

The integration uses these existing server endpoints:

| Request | Purpose |
| --- | --- |
| `GET /api/robots` | Robot names, generations, serial numbers, and connection status |
| `POST /api/robot/{serial}/command` with `{"cmd":"getRobotState"}` | Gen3 battery at `details.charge` |
| `POST /api/robot/{serial}/command` with `{"ability":"state.show"}` | Gen4 battery at `body.details.charge` |

From the repository root, run the tests with Python 3.13:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r tests/homeassistant/requirements.txt
.venv/bin/python -m pytest -c tests/homeassistant/pytest.ini tests/homeassistant
```

The test dependencies pin Home Assistant through `pytest-homeassistant-custom-component`.
Tests cover setup, entity registration, both robot responses, invalid readings, disconnections, recovery, new robots, and unload.

For a hardware check, compare the Battery sensor with the Vacuula web app.
Then disconnect the robot and check that the sensor becomes unavailable after the next poll.
Reconnect the robot and check that the sensor recovers.
