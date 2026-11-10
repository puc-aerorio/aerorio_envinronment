"""What `run.sh` decides on a WSL Host, observed through `--dry-run`."""

import pytest

pytestmark = pytest.mark.launcher

WSL = ["compose/base.yaml", "compose/wsl.yaml"]
D3D12 = "compose/wsl-d3d12.yaml"


@pytest.fixture
def wsl(host):
    host.wsl = True
    host.dxg = True
    return host


def test_docker_engine_renders_through_d3d12_and_wslg(wsl):
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, D3D12]
    assert "AVISO" not in run.stderr
    env = run.container_environment()
    assert env["GALLIUM_DRIVER"] == "d3d12"
    assert env["MESA_D3D12_DEFAULT_ADAPTER_NAME"] == "NVIDIA"
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/wsl/lib"
    assert env["DISPLAY"] == ":1"
    assert env["WAYLAND_DISPLAY"] == "wayland-0"
    assert env["XDG_RUNTIME_DIR"] == "/mnt/wslg/runtime-dir"


def test_nvidia_gpu_still_renders_through_d3d12_not_the_nvidia_runtime(wsl):
    wsl.nvidia_smi_works = True
    wsl.docker_nvidia_runtime = True
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, D3D12]
    assert "--gpus" not in run.command
    assert "__NV_PRIME_RENDER_OFFLOAD" not in run.container_environment()


def test_adapter_override_from_the_host_environment_is_honoured(wsl):
    wsl.env["MESA_D3D12_DEFAULT_ADAPTER_NAME"] = "Intel"
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.container_environment()["MESA_D3D12_DEFAULT_ADAPTER_NAME"] == "Intel"


def test_without_dxg_falls_back_to_software_rendering(wsl):
    wsl.dxg = False
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, "compose/cpu.yaml"]


def test_cpu_flag_forces_software_rendering(wsl):
    run = wsl.dry_run("--cpu")
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, "compose/cpu.yaml"]


def test_clone_under_a_windows_drive_is_refused(wsl):
    wsl.clone_under = "/mnt/c/Users/aluno/aerorio_envinronment"
    run = wsl.dry_run()
    assert run.returncode != 0
    assert run.stdout == ""
    assert "/mnt/c" in run.stderr
    assert "git clone" in run.stderr  # how to move the clone into the distro


def test_wslg_mount_points_are_not_mistaken_for_windows_drives(wsl):
    wsl.clone_under = "/mnt/wslg/aerorio_envinronment"
    run = wsl.dry_run()
    assert "disco do Windows" not in run.stderr


def test_linux_host_may_run_from_a_clone_under_mnt(host):
    host.clone_under = "/mnt/d/aerorio_envinronment"
    run = host.dry_run()
    assert "disco do Windows" not in run.stderr


def test_docker_desktop_with_host_networking_starts_without_a_warning(wsl):
    wsl.docker_desktop = True
    wsl.host_networking = True
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, D3D12]
    assert "Docker Desktop" in run.stderr  # the flavour is reported
    assert "AVISO" not in run.stderr


def test_docker_desktop_without_host_networking_warns_how_to_enable_it(wsl):
    wsl.docker_desktop = True
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, D3D12]
    assert "AVISO" in run.stderr
    assert "Enable host networking" in run.stderr


def test_build_with_low_wsl_memory_warns(wsl):
    wsl.mem_total_kb = 4 * 1024 * 1024
    run = wsl.dry_run("--build")
    assert run.returncode == 0, run.stderr
    assert "AVISO" in run.stderr
    assert "4.0 GB" in run.stderr
    assert ".wslconfig" in run.stderr
    assert "docker build" in run.stdout.splitlines()[0]


def test_build_with_an_8gb_wsl_limit_does_not_warn(wsl):
    wsl.mem_total_kb = 8_098_000  # what the kernel reports under "memory=8GB"
    run = wsl.dry_run("--build")
    assert run.returncode == 0, run.stderr
    assert "AVISO" not in run.stderr


def test_low_memory_only_matters_for_a_build(wsl):
    wsl.mem_total_kb = 4 * 1024 * 1024
    run = wsl.dry_run()
    assert "AVISO" not in run.stderr


def test_docker_desktop_whose_settings_cannot_be_read_also_warns(wsl):
    wsl.docker_desktop = True
    wsl.host_networking = None
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert "Enable host networking" in run.stderr


def test_clone_reached_through_a_symlink_to_a_windows_drive_is_refused(wsl):
    wsl.clone_under = "/mnt/d/aerorio_envinronment"
    wsl._launcher()
    (wsl.root / "home").mkdir()
    (wsl.root / "home/clone").symlink_to(wsl.root / "mnt/d/aerorio_envinronment")
    wsl.clone_under = "/home/clone"
    run = wsl.dry_run()
    assert run.returncode != 0
    assert "/mnt/d" in run.stderr


def test_custom_kernel_is_recognised_by_the_wsl_interop_marker(wsl):
    wsl.wsl = False
    marker = wsl.root / "proc/sys/fs/binfmt_misc/WSLInterop"
    marker.parent.mkdir(parents=True)
    marker.touch()
    run = wsl.dry_run()
    assert run.returncode == 0, run.stderr
    assert run.compose_files == [*WSL, D3D12]
