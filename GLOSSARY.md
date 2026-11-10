# aerorio environment

The team's packaged development environment for simulated drone missions: ArduPilot SITL flying in Gazebo, controlled through uav_api, delivered as a Docker image that runs on each member's own machine.

## Language

### Packaging

**Host**:
The machine (and OS setup) a team member runs the Container on. Exactly two kinds are supported: Linux Host and WSL Host.
_Avoid_: machine, PC, local

**Linux Host**:
A native Ubuntu installation running Docker Engine directly.
_Avoid_: Linux machine, bare metal

**WSL Host**:
A Linux distro under WSL2 on Windows 11, with its clone inside the distro's filesystem.
_Avoid_: Windows host, Windows machine

**Host Check**:
The on-Host diagnostic (`run.sh --check`) that verifies a Host can run the Container and reports its Gazebo real-time factor.
_Avoid_: doctor, health check, benchmark

**RTF**:
Gazebo's real-time factor during a Simulation; the single measure of whether a Host runs "fast" (≥ 0.8) or "slow".
_Avoid_: FPS, speed, performance

**Image**:
The built `aerorio/sim` Docker image holding the whole toolchain.
_Avoid_: environment, build

**Container**:
The single running instance of the Image (`aerorio-sim`) that every shell on a Host attaches to.
_Avoid_: env, VM, box

**Tools**:
Team-maintained scripts, Worlds, Models and examples, baked into the Image and overlaid live from the clone.
_Avoid_: scripts folder, utils

**Workspace**:
The folder shared between Host and Container where all of a team member's work happens (missions, tasks, Photos); mounted from the clone, never baked into the Image.
_Avoid_: project folder, home

### Simulation

**Simulation**:
One running set of Gazebo, SITL, uav-api, camera bridge and Camera Saver, started by `start_simulation.sh` in the `drone` tmux session.
_Avoid_: sim session, run

**World**:
A Gazebo `.sdf` scene the Simulation loads; identified by its `<world name>`, not its file name.
_Avoid_: map, scenario, level

**Model**:
A Gazebo asset (drone, target, prop) referenced from a World as `model://<name>`.
_Avoid_: object, asset

**Photo**:
A camera frame saved as `frame_NNNNN.png` by the Camera Saver into the Workspace.
_Avoid_: image (reserved for the Docker Image), frame, snapshot

**uav-api**:
The HTTP API a Simulation exposes on port 8000, through which missions command and read the drone; its interactive docs are at `/docs`.
_Avoid_: the API, the server, uav_api (that is the Python package)

**Ground Station**:
Mission Planner or QGroundControl running on the Host, receiving the Simulation's MAVLink.
_Avoid_: GCS, QGC, MP

**Camera Saver**:
The process that writes one Photo per interval from the drone's camera topic.
_Avoid_: recorder, capture script
