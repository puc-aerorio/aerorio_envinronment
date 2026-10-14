#!/usr/bin/env bash
# Sobe o container de simulação. Usa a GPU NVIDIA se (1) nvidia-smi funciona e
# (2) o Docker tem o runtime "nvidia" (NVIDIA Container Toolkit). Caso contrário roda com Mesa.
#
#   ./run.sh            # abre um shell no container (ou entra no container já em execução)
#   ./run.sh --build    # (re)constrói a imagem antes de subir
#   ./run.sh --cpu      # força o modo sem GPU
set -euo pipefail

IMAGE="aerorio/sim"
NAME="aerorio-sim"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$HERE/.." && pwd)"   # pasta aerorio/ montada em /home/ardupilot/aerorio

BUILD=0; FORCE_CPU=0
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --cpu)   FORCE_CPU=1 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "argumento desconhecido: $arg" >&2; exit 1 ;;
  esac
done

if [[ $BUILD -eq 1 ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" "$HERE"
fi

# Container já rodando? Só abre outro shell nele (útil para o fluxo Gazebo + SITL + uav-api).
if docker container inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; then
  exec docker exec -it "$NAME" bash
fi

GPU_ARGS=()
if [[ $FORCE_CPU -eq 0 ]] && command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1 \
   && docker info 2>/dev/null | grep -qi 'nvidia'; then
  GPU_ARGS=(--gpus all)
  echo "[run.sh] GPU NVIDIA detectada: rodando com --gpus all"
else
  echo "[run.sh] Sem GPU NVIDIA utilizável pelo Docker: rodando com renderização por software (Mesa)."
  echo "         Para usar a GPU instale o NVIDIA Container Toolkit (ver README.md)."
fi

# Libera o X (XWayland) para o container. DISPLAY normalmente é :0.
if command -v xhost >/dev/null; then xhost +local:docker >/dev/null || true; fi

exec docker run -it --rm \
  --name "$NAME" \
  --network host \
  "${GPU_ARGS[@]}" \
  -e DISPLAY="${DISPLAY:-:0}" \
  -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "$WORKSPACE":/home/ardupilot/aerorio \
  "$IMAGE"
