#!/usr/bin/env bash
# Sobe o container de simulação via docker compose (arquivos em compose/).
# Detecta a GPU: NVIDIA se nvidia-smi funciona e o Docker tem o runtime "nvidia" (NVIDIA Container
# Toolkit); GPU integrada se existe /dev/dri; senão renderização por software (Mesa).
#
#   ./run.sh            # abre um shell no container (ou entra no container já em execução)
#   ./run.sh --build    # (re)constrói a imagem antes de subir
#   ./run.sh --cpu      # força renderização por software (sem GPU)
#   ./run.sh --dry-run  # só mostra o comando docker que seria executado (não inicia nada)
set -euo pipefail

IMAGE="aerorio/sim"
NAME="aerorio-sim"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"   # os arquivos do compose e o contexto do build são relativos à raiz do clone

# Raiz onde a detecção procura /dev/dri etc. Os testes apontam para um sistema de arquivos falso
# (e põem stubs de docker/nvidia-smi no PATH); fora dos testes é a raiz de verdade.
HOST_ROOT="${AERORIO_HOST_ROOT:-}"

BUILD=0; FORCE_CPU=0; DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --build)   BUILD=1 ;;
    --cpu)     FORCE_CPU=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) awk 'NR > 1 && !/^#/ {exit} NR > 1 {sub(/^# ?/, ""); print}' "$0"; exit 0 ;;
    *) echo "argumento desconhecido: $arg" >&2; exit 1 ;;
  esac
done

say() { echo "[run.sh] $*" >&2; }

# step CMD...: roda o comando, ou só o mostra com --dry-run.
step() {
  if [[ $DRY_RUN -eq 1 ]]; then printf '%q ' "$@"; echo; else "$@"; fi
}

# finish [VAR=valor...] -- CMD...: substitui este script pelo comando (ou só o mostra com --dry-run).
finish() {
  local vars=()
  while [[ $1 != -- ]]; do vars+=("$1"); shift; done
  shift
  if [[ $DRY_RUN -eq 1 ]]; then printf '%q ' "${vars[@]}" "$@"; echo; exit 0; fi
  exec env "${vars[@]}" "$@"
}

# ---------------------------------------------------------------------------
# Imagem e ciclo de vida: o primeiro ./run.sh é dono do container; os outros só abrem shells nele.
# ---------------------------------------------------------------------------
if [[ $BUILD -eq 1 ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  step docker build --build-arg HOST_UID="$(id -u)" --build-arg HOST_GID="$(id -g)" -t "$IMAGE" .
fi

# (Saídas do docker vão para variáveis antes do teste: com pipefail, um "docker | grep -q" pode
# falhar por SIGPIPE quando o grep sai cedo.)
if [[ "$(docker container inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" == true ]]; then
  finish -- docker exec -it "$NAME" bash
fi

# ---------------------------------------------------------------------------
# Detecção do host -> overrides do compose
# ---------------------------------------------------------------------------
nvidia_gpu_works() { command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; }
docker_has_nvidia_runtime() { local info; info="$(docker info 2>/dev/null)"; grep -qi nvidia <<<"$info"; }

# Grupo dono de /dev/dri/renderD* no host (normalmente "render"). Sem como saber, usa o grupo
# "video" do próprio container (o usuário já está nele), só para o group_add não ficar vazio.
render_gid() {
  local dev
  for dev in "$HOST_ROOT"/dev/dri/renderD*; do
    [[ -e "$dev" ]] && { stat -c %g "$dev"; return; }
  done
  # O getent lê o host de verdade, então só vale quando a detecção não usa uma raiz falsa.
  [[ -z "$HOST_ROOT" ]] && getent group render | cut -d: -f3 | grep . && return
  echo video
}

FILES=(compose/base.yaml compose/linux-x11.yaml)
VARS=("DISPLAY=${DISPLAY:-:0}")   # VAR=valor que os arquivos do compose interpolam
HAS_GPU=0
if [[ $FORCE_CPU -eq 1 ]]; then
  say "--cpu: renderização por software (Mesa llvmpipe)."
else
  if [[ -d "$HOST_ROOT/dev/dri" ]]; then
    FILES+=(compose/linux-dri.yaml)
    VARS+=("RENDER_GID=$(render_gid)")
    HAS_GPU=1
  fi
  if nvidia_gpu_works; then
    if docker_has_nvidia_runtime; then
      say "GPU NVIDIA detectada: renderizando na NVIDIA."
      FILES+=(compose/linux-nvidia.yaml)
      HAS_GPU=1
    else
      say "AVISO: há GPU NVIDIA, mas o Docker não tem o NVIDIA Container Toolkit; ela não será usada."
      say "       Instale o toolkit para usar a GPU (ver README.md)."
    fi
  fi
  [[ $HAS_GPU -eq 1 ]] || say "Sem GPU utilizável: renderização por software (Mesa llvmpipe)."
fi
[[ $HAS_GPU -eq 1 ]] || FILES+=(compose/cpu.yaml)

# Libera o X (XWayland) para o container.
if [[ $DRY_RUN -eq 0 ]] && command -v xhost >/dev/null; then xhost +local:docker >/dev/null || true; fi

COMPOSE=(docker compose --project-directory .)
for f in "${FILES[@]}"; do COMPOSE+=(-f "$f"); done
# "compose run" ignora o container_name do base.yaml, por isso o --name.
finish "${VARS[@]}" -- "${COMPOSE[@]}" run --rm --name "$NAME" sim
