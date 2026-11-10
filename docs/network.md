# Network map

Who listens where during a Simulation. The Container uses host networking on every Host (ADR-0003), so every port below is on the Host's own network (on a WSL Host: the distro's). Update this table in the same PR that moves a port.

| Process | Port | Proto | Listens on / sends to | Talks to | Source |
| --- | --- | --- | --- | --- | --- |
| uav-api (HTTP + `/docs`) | 8000 | TCP | listens `0.0.0.0` | missions, browsers | verified: `uav_api/run_api.py` |
| uav-api (MAVLink in) | 14550 | UDP | listens `<IP>` (`udpin`; `<IP>` = first address of `hostname -I`) | MAVProxy | `tools/start_simulation.sh` |
| MAVProxy → uav-api | 14550 | UDP | sends to `<IP>` (`--out`) | uav-api | `tools/start_simulation.sh` |
| MAVProxy → Ground Station | 14550 | UDP | sends to `127.0.0.1` (Linux Host) or the default gateway, i.e. Windows (WSL Host) | Mission Planner / QGroundControl | verified: sim_vehicle.py's built-in output, WSL2 detected from the kernel release |
| SITL ↔ MAVProxy | 5760 | TCP | SITL listens | MAVProxy | ArduPilot SITL default, not checked here |
| SITL spare serial ports | 5762, 5763 | TCP | SITL listens | free | ArduPilot SITL default, not checked here |
| ardupilot_gazebo plugin ↔ SITL | 9002 | UDP | JSON flight dynamics | SITL (`--model JSON`) | plugin default, not checked here |
| Gazebo transport | multicast discovery + dynamic ports | UDP/TCP | gz-transport defaults | Gazebo GUI, ROS 2 bridge | needs host networking; doesn't survive a bridge network |

## Gotchas

- **Two things on UDP 14550 on a Linux Host.** uav-api listens on `<IP>:14550` and a Ground Station on the same Host listens on `0.0.0.0:14550`. Whether both can bind depends on their socket options. #12 moves uav-api's input to 14555 to give the Ground Station 14550 alone.
- **WSL forwards TCP only.** In WSL2's default NAT mode, Windows `localhost` reaches TCP ports in the distro (so `localhost:8000/docs` opens in a Windows browser), but not UDP. MAVLink to a Windows Ground Station therefore goes out to the Windows address (the default gateway) instead, and Windows Firewall can drop it silently.
- **Docker Desktop** needs its "Enable host networking" setting for any of this to reach the Host; its default gateway is Docker's VM, not Windows.
