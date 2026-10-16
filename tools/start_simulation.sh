#!/usr/bin/env bash
# Sobe a simulação completa numa sessão tmux chamada "drone", com seis painéis:
#   0: Gazebo (gz sim)            1: SITL do ArduPilot (sim_vehicle.py)
#   2: uav-api                    3: ponte ROS 2 (imagens da câmera -> sensor_msgs/Image)
#   4: camera_saver.py (salva uma foto por segundo em $DRONE_PHOTOS_DIR)
#   5: shell livre para o usuário
#
# Uso: start_simulation.sh [mundo]
#   mundo: "missao1", "missao1.sdf" ou um caminho absoluto (padrão: iris_runway.sdf).
#   Procura primeiro em ~/tools/gazebo/worlds (customizados), depois em ~/ardupilot_gazebo/worlds.
#   Se a sessão "drone" já existir, apenas anexa a ela. Para encerrar tudo: stop_simulation.sh
#   Para voltar o drone ao estado inicial sem derrubar o Gazebo: reset_drone.sh
#
# Uso interno (comandos dos painéis 1 a 4; reset_drone.sh reusa --sitl e --api):
#   start_simulation.sh --sitl MUNDO IP | --api IP | --bridge | --saver
set -euo pipefail

SESSION="drone"
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
WORLD_DIRS=("$HOME/tools/gazebo/worlds" "$HOME/ardupilot_gazebo/worlds")

# ---------------------------------------------------------------------------
# Painel 3: espera o Gazebo publicar tópicos de câmera e faz a ponte de todos.
# Descobre os tópicos em vez de fixar o caminho, então funciona em qualquer mundo.
# ---------------------------------------------------------------------------
bridge() {
  set +u                                   # os setup.bash do ROS usam variáveis não definidas
  source "$HOME/ros_env.sh"                # ROS 2 + correção do PATH/GZ_CONFIG_PATH do gz
  set -u
  echo "[bridge] aguardando tópicos de câmera do Gazebo..."
  local topics=()
  while true; do
    mapfile -t topics < <(gz topic -l 2>/dev/null | grep -E '/sensor/[^/]+/image$' || true)
    [[ ${#topics[@]} -gt 0 ]] && break
    sleep 2
  done
  local args=() t
  for t in "${topics[@]}"; do
    args+=("${t}@sensor_msgs/msg/Image@gz.msgs.Image")
    args+=("${t%/image}/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo")
  done
  echo "[bridge] tópicos GZ -> ROS 2:"; printf '  %s\n' "${topics[@]}"
  exec ros2 run ros_gz_bridge parameter_bridge "${args[@]}"
}

# Painel 4: salva fotos da câmera. O script espera sozinho o tópico da ponte aparecer.
saver() {
  set +u
  source "$HOME/ros_env.sh"
  set -u
  exec /usr/bin/python3 "$(dirname "$SELF")/camera_saver.py"
}
# Parâmetros padrão do frame (.parm) para passar ao sim_vehicle.py via --add-param-file.
# No ArduPilot master (desde set/2026) o sim_vehicle.py não passa mais --defaults: o binário
# resolve os .parm do frame pelo nome do --model. Como usamos "--model JSON" (ardupilot_gazebo),
# nada casa e FRAME_CLASS fica 0 -> "Frame: UNSUPPORTED" e o copter não arma.
# Em checkouts antigos (sem vehicleinfo.json) a função não imprime nada e o sim_vehicle.py
# continua passando --defaults sozinho.
frame_param_args() {
  python3 - "$1" "$2" <<'EOF'
import json, os, sys
vehicle, frame = sys.argv[1:3]
root = os.path.expanduser("~/ardupilot/Tools/autotest")
try:
    info = json.load(open(os.path.join(root, "pysim", "vehicleinfo.json")))
    files = info[vehicle]["frames"][frame].get("default_params_filename", [])
except Exception:
    sys.exit(0)
if isinstance(files, str):
    files = [files]
print(" ".join("--add-param-file=" + os.path.join(root, f) for f in files))
EOF
}

# Veículo conforme o mundo: zephyr* é avião, o resto é o Iris (copter). Imprime "VEICULO FRAME".
vehicle_for_world() {
  case "$(basename "$1")" in
    zephyr*) echo "ArduPlane gazebo-zephyr" ;;
    *)       echo "ArduCopter gazebo-iris" ;;
  esac
}

# Painel 1: SITL (-N: não recompila; o binário já vem pronto na imagem). O sim_vehicle.py abre
# o binário numa janela tmux "ArduCopter" e o MAVProxy fica neste painel; Ctrl-C aqui encerra os dois.
sitl() {
  local world="$1" ip="$2" vehicle frame param_args
  read -r vehicle frame <<<"$(vehicle_for_world "$world")"
  param_args="$(frame_param_args "$vehicle" "$frame")"
  # shellcheck disable=SC2086  # param_args são vários argumentos separados por espaço
  exec sim_vehicle.py -N -v "$vehicle" -f "$frame" --model JSON $param_args --map --console --out "$ip:14550"
}

# Painel 2: uav-api. Ele desiste se o SITL ainda não responde (o Gazebo pode demorar a carregar
# o mundo), então tenta de novo até conectar. Ctrl-C interrompe o laço.
api() {
  local ip="$1" n=0
  until uav-api start --uav_connection "$ip:14550" --connection_type udpin --sysid 1; do
    n=$((n + 1))
    if [[ $n -ge 40 ]]; then echo "[api] desisti após $n tentativas" >&2; return 1; fi
    echo "[api] SITL ainda não respondeu; nova tentativa em 5s ($n/40)..."
    sleep 5
  done
}
case "${1:-}" in
  --sitl)   sitl "${2:?uso: --sitl MUNDO IP}" "${3:?uso: --sitl MUNDO IP}" ;;
  --api)    api "${2:?uso: --api IP}" ;;
  --bridge) bridge ;;
  --saver)  saver ;;
esac

# ---------------------------------------------------------------------------
# Resolve o mundo pedido
# ---------------------------------------------------------------------------
resolve_world() {
  local w="$1" d
  [[ "$w" == *.sdf ]] || w="$w.sdf"
  if [[ "$w" == /* ]]; then
    [[ -f "$w" ]] && { echo "$w"; return 0; }
    return 1
  fi
  for d in "${WORLD_DIRS[@]}"; do
    [[ -f "$d/$w" ]] && { echo "$d/$w"; return 0; }
  done
  return 1
}

WORLD_ARG="${1:-iris_runway.sdf}"
if ! WORLD_PATH="$(resolve_world "$WORLD_ARG")"; then
  echo "Mundo '$WORLD_ARG' não encontrado. Disponíveis:" >&2
  for d in "${WORLD_DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    echo "  $d:" >&2
    ls "$d"/*.sdf 2>/dev/null | xargs -rn1 basename | sed 's/^/    /' >&2
  done
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Sessão '$SESSION' já existe; anexando (tmux kill-session -t $SESSION para reiniciar)."
  exec tmux attach -t "$SESSION"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
IP="${IP:-127.0.0.1}"

read -r VEHICLE FRAME <<<"$(vehicle_for_world "$WORLD_PATH")"

echo "mundo:    $WORLD_PATH"
echo "veículo:  $VEHICLE ($FRAME)"
echo "mavlink:  $IP:14550   uav-api: http://$IP:8000"
echo "fotos:    ${DRONE_PHOTOS_DIR:-$HOME/workspace/photos}"

# ---------------------------------------------------------------------------
# Sessão tmux
# ---------------------------------------------------------------------------
tmux new-session -d -s "$SESSION" -n sim

# 0: Gazebo
tmux send-keys -t "$SESSION" "gz sim -v4 -r '$WORLD_PATH'" C-m

# 1: SITL. Guardamos o id do painel (e os parâmetros) no ambiente da sessão tmux para o
#    reset_drone.sh relançar o SITL e a uav-api nos mesmos painéis.
SITL_PANE="$(tmux split-window -h -P -F '#{pane_id}' -t "$SESSION")"
tmux send-keys -t "$SITL_PANE" "sleep 5; '$SELF' --sitl '$WORLD_PATH' $IP" C-m

# 2: uav-api (SITL externo: sem --simulated, que no uav_api >= 0.3 é flag sem valor)
API_PANE="$(tmux split-window -v -P -F '#{pane_id}' -t "$SESSION")"
tmux send-keys -t "$API_PANE" "sleep 15; '$SELF' --api $IP" C-m

tmux set-environment -t "$SESSION" SIM_WORLD "$WORLD_PATH"
tmux set-environment -t "$SESSION" SIM_IP "$IP"
tmux set-environment -t "$SESSION" SIM_PANE_SITL "$SITL_PANE"
tmux set-environment -t "$SESSION" SIM_PANE_API "$API_PANE"

# 3: ponte ROS 2
tmux select-pane -t "$SESSION:0.0"
tmux split-window -v -t "$SESSION"
tmux send-keys -t "$SESSION" "'$SELF' --bridge" C-m

# 4: fotos da câmera
tmux split-window -v -t "$SESSION"
tmux send-keys -t "$SESSION" "'$SELF' --saver" C-m

# 5: shell livre para o usuário (fica selecionado ao anexar). Guardamos o id do painel porque
#    o tmux renumera os índices conforme a posição; "0.5" não é necessariamente este painel.
FREE_PANE="$(tmux split-window -v -P -F '#{pane_id}' -t "$SESSION")"
tmux send-keys -t "$FREE_PANE" "clear; echo 'Painel livre: rode aqui seus comandos e scripts (ex.: curl http://$IP:8000/telemetry/gps).'" C-m

tmux select-layout -t "$SESSION" tiled
tmux select-pane -t "$FREE_PANE"
exec tmux attach -t "$SESSION"
