"""What `run.sh` decides on each kind of Linux Host, observed through `--dry-run`."""

import shlex

import pytest

pytestmark = pytest.mark.launcher

LINUX = ["compose/base.yaml", "compose/linux-x11.yaml"]


def test_igpu_only_renders_on_dri(host):
    host.dri = True
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*LINUX, "compose/linux-dri.yaml"]
    assert run.env["RENDER_GID"] == str(host.render_device.stat().st_gid)
    assert run.env["DISPLAY"] == ":1"
    # First shell owns the Container: attached, removed on exit, under the usual name.
    assert run.command[-5:] == ["run", "--rm", "--name", "aerorio-sim", "sim"]


def test_nvidia_with_toolkit_renders_on_nvidia(host):
    host.nvidia_smi_works = True
    host.docker_nvidia_runtime = True
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*LINUX, "compose/linux-nvidia.yaml"]


def test_nvidia_without_toolkit_falls_back_with_a_warning(host):
    host.nvidia_smi_works = True
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*LINUX, "compose/cpu.yaml"]
    assert "NVIDIA Container Toolkit" in run.stderr


def test_hybrid_laptop_offloads_rendering_to_nvidia(host):
    host.dri = True
    host.nvidia_smi_works = True
    host.docker_nvidia_runtime = True
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*LINUX, "compose/linux-dri.yaml", "compose/linux-nvidia.yaml"]
    env = run.container_environment()
    assert env["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert env["__GLX_VENDOR_LIBRARY_NAME"] == "nvidia"


def test_cpu_flag_forces_software_rendering_even_with_gpus(host):
    host.dri = True
    host.nvidia_smi_works = True
    host.docker_nvidia_runtime = True
    run = host.dry_run("--cpu")
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*LINUX, "compose/cpu.yaml"]
    assert run.container_environment()["LIBGL_ALWAYS_SOFTWARE"] == "1"


def test_second_shell_execs_into_the_running_container(host):
    host.container_running = True
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.command == ["docker", "exec", "-it", "aerorio-sim", "bash"]


def test_missing_image_is_built_first(host):
    host.image_present = False
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    first = shlex.split(run.stdout.splitlines()[0])
    assert first[:2] == ["docker", "build"] and "aerorio/sim" in first
    assert run.command[-1] == "sim"


def test_dri_without_render_node_uses_the_containers_video_group(host):
    (host.root / "dev/dri").mkdir(parents=True)
    run = host.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.env["RENDER_GID"] == "video"


HOST_CASES = {
    "no-gpu": ({}, ()),
    "igpu": ({"dri": True}, ()),
    "nvidia": ({"nvidia_smi_works": True, "docker_nvidia_runtime": True}, ()),
    "hybrid": ({"dri": True, "nvidia_smi_works": True, "docker_nvidia_runtime": True}, ()),
    "cpu-flag": ({"dri": True}, ("--cpu",)),
}


@pytest.mark.parametrize("case", HOST_CASES, ids=str)
def test_container_uses_host_networking_and_publishes_no_ports(host, case):
    # ADR-0003: published ports cut the Host off from the SITL, Ground Stations and Gazebo.
    fields, args = HOST_CASES[case]
    for name, value in fields.items():
        setattr(host, name, value)
    run = host.dry_run(*args)
    assert run.returncode == 0, run.stderr
    config = run.container_config()
    assert config.get("network_mode") == "host"
    assert not config.get("ports"), "see docs/adr/0003-host-networking-on-every-host.md"
