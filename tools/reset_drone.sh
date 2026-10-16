#!/usr/bin/env bash
# Volta o drone ao estado inicial sem derrubar a simulação: reinicia só o SITL (ArduPilot) e a
# uav-api, nos mesmos painéis do tmux, e põe o modelo de volta na pose inicial do mundo.
# Gazebo, ponte ROS 2 e camera_saver.py continuam rodando (as fotos seguem a numeração).
#
# Uso: reset_drone.sh [--purge] [--no-wait]
#   --purge    apaga também eeprom.bin, logs/, terrain/ e mav.* do SITL (parâmetros voltam ao padrão)
#   --no-wait  não espera a uav-api voltar a responder
#
# Por que assim: os modelos usam o plugin do ArduPilot em lock_step. Quando o SITL morre, o
# plugin bloqueia a física do Gazebo esperando pacotes (é isso que "quebra" a simulação). Com o
# mundo PAUSADO o plugin não espera, então: pausa -> derruba SITL -> reset das poses -> despausa
# -> novo SITL. A pose é reposta pelo serviço set_pose do mundo (teleporte para a pose do
# <include> do drone no .sdf), que mantém o tempo de simulação. Não usamos o "reset" do mundo:
# o gz-sim 8 não implementa "model_only", e o reset completo zera o tempo, mas o plugin nunca
# zera o seu relógio interno e ficaria travado até o tempo antigo passar de novo.
set -uo pipefail

SESSION="drone"
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
START="$HERE/start_simulation.sh"
PURGE=0; WAIT=1
for arg in "$@"; do
  case "$arg" in
    --purge)   PURGE=1 ;;
    --no-wait) WAIT=0 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "argumento desconhecido: $arg" >&2; exit 1 ;;
  esac
done

log() { echo "[reset] $*"; }
die() { echo "[reset] ERRO: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Sessão, parâmetros gravados pelo start_simulation.sh e serviço do mundo no Gazebo
# ---------------------------------------------------------------------------
tmux has-session -t "$SESSION" 2>/dev/null \
  || die "sessão tmux '$SESSION' não existe; a simulação não está rodando (start_simulation.sh)"

env_get() { tmux show-environment -t "$SESSION" "$1" 2>/dev/null | sed -n 's/^[^=]*=//p'; }
SIM_WORLD="$(env_get SIM_WORLD)"; SIM_IP="$(env_get SIM_IP)"
SIM_PANE_SITL="$(env_get SIM_PANE_SITL)"; SIM_PANE_API="$(env_get SIM_PANE_API)"
[[ -n "$SIM_WORLD" && -n "$SIM_IP" && -n "$SIM_PANE_SITL" && -n "$SIM_PANE_API" ]] \
  || die "a sessão não tem os dados do start_simulation.sh (versão antiga?); use stop/start_simulation.sh"
for p in "$SIM_PANE_SITL" "$SIM_PANE_API"; do
  tmux list-panes -s -t "$SESSION" -F '#{pane_id}' | grep -qx "$p" || die "painel $p não existe mais"
done

CONTROL="$(gz service -l 2>/dev/null | grep -m1 -oE '^/world/[^/]+/control$')"
[[ -n "$CONTROL" ]] || die "Gazebo não respondeu (serviço /world/*/control não encontrado)"
SET_POSE="${CONTROL%/control}/set_pose"
world_control() {   # world_control 'pause: true' | 'pause: false'
  gz service -s "$CONTROL" --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean \
    --timeout 5000 --req "$1" >/dev/null
}
# Pose inicial do drone no .sdf do mundo: o <include> cujo model:// é iris*/zephyr*.
# Imprime a requisição gz.msgs.Pose pronta (nome + posição + quaternion).
drone_pose_req() {
  python3 - "$SIM_WORLD" <<'PY'
import math, sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
for inc in root.iter("include"):
    uri = inc.findtext("uri", "")
    base = uri.rstrip("/").split("/")[-1]
    if not (base.startswith("iris") or base.startswith("zephyr")):
        continue
    name = inc.findtext("name") or base
    pose_el = inc.find("pose")
    vals = [float(v) for v in (pose_el.text if pose_el is not None else "0 0 0 0 0 0").split()]
    x, y, z, r, p, yw = (vals + [0.0] * 6)[:6]
    if pose_el is not None and pose_el.get("degrees", "false").lower() == "true":
        r, p, yw = map(math.radians, (r, p, yw))
    cr, sr, cp, sp, cy, sy = math.cos(r/2), math.sin(r/2), math.cos(p/2), math.sin(p/2), math.cos(yw/2), math.sin(yw/2)
    qw = cr*cp*cy + sr*sp*sy; qx = sr*cp*cy - cr*sp*sy
    qy = cr*sp*cy + sr*cp*sy; qz = cr*cp*sy - sr*sp*cy
    print(f'name: "{name}", position: {{x: {x}, y: {y}, z: {z}}}, '
          f'orientation: {{x: {qx}, y: {qy}, z: {qz}, w: {qw}}}')
    break
else:
    sys.exit(1)
PY
}

# ---------------------------------------------------------------------------
# Utilidades: parar o que roda num painel e matar o que sobrar
# ---------------------------------------------------------------------------
# Ctrl-C no painel e espera o shell dele ficar sem filhos (comando terminou), até $2 segundos.
# (pane_current_command não serve: os painéis rodam o start_simulation.sh, que também é bash.)
stop_pane() {
  local pane="$1" max="${2:-15}" i shell
  shell="$(tmux display -p -t "$pane" '#{pane_pid}')"
  tmux send-keys -t "$pane" C-c '' 2>/dev/null
  for ((i = 0; i < max * 2; i++)); do
    [[ -z "$(pgrep -P "$shell")" ]] && return 0
    sleep 0.5
  done
  return 1
}
# Ignora zumbis (<defunct>): já morreram, só esperam o pai recolher.
alive() {
  local pids
  pids=$(pgrep -f "$1" 2>/dev/null | grep -vxE "1|$$|$PPID") || return 0
  ps -o pid= -o stat= -p $(echo $pids | tr ' ' ',') 2>/dev/null | awk '$2 !~ /Z/ {print $1}'
}
kill_pattern() {   # kill_pattern PADRAO: SIGTERM, depois SIGKILL
  local pids
  pids=$(alive "$1"); [[ -n "$pids" ]] || return 0
  log "encerrando ($1): $(echo $pids | tr '\n' ' ')"
  kill $pids 2>/dev/null; sleep 1
  pids=$(alive "$1"); [[ -n "$pids" ]] || return 0
  kill -9 $pids 2>/dev/null; sleep 0.5
}

# ---------------------------------------------------------------------------
# 1. uav-api
# ---------------------------------------------------------------------------
log "parando a uav-api..."
stop_pane "$SIM_PANE_API" 10 || log "painel da uav-api não voltou ao shell; forçando"
kill_pattern 'uav-api|uav_api'

# 2. Pausa o mundo: com a física parada o plugin do ArduPilot não trava esperando o SITL.
log "pausando o Gazebo..."
world_control 'pause: true' || die "não consegui pausar o mundo ($CONTROL)"

# 3. SITL: Ctrl-C no MAVProxy encerra o sim_vehicle.py, que derruba o binário (janela ArduCopter).
log "parando o SITL..."
stop_pane "$SIM_PANE_SITL" 20 || log "painel do SITL não voltou ao shell; forçando"
for p in 'sim_vehicle.py' 'mavproxy' 'arducopter|arduplane'; do kill_pattern "$p"; done
left=""
for p in 'uav-api|uav_api' 'sim_vehicle.py' 'mavproxy' 'arducopter|arduplane'; do
  [[ -n "$(alive "$p")" ]] && left+="$p "
done
if [[ -n "$left" ]]; then
  world_control 'pause: false'
  die "ainda rodando: $left (use stop_simulation.sh)"
fi

# 4. Opcional: artefatos do SITL no $HOME (parâmetros gravados, logs).
if [[ $PURGE -eq 1 ]]; then
  for f in eeprom.bin mav.parm mav.tlog mav.tlog.raw logs terrain; do
    [[ -e "$HOME/$f" ]] && rm -rf "$HOME/$f" && log "removido ~/$f"
  done
fi

# 5. Drone de volta à pose inicial do mundo (teleporte com o mundo pausado, ver cabeçalho).
POSE_REQ="$(drone_pose_req)" || { world_control 'pause: false'; die "não achei o drone (iris*/zephyr*) em $SIM_WORLD"; }
log "repondo o drone na pose inicial (${POSE_REQ%%,*})..."
gz service -s "$SET_POSE" --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 5000 \
  --req "$POSE_REQ" >/dev/null || { world_control 'pause: false'; die "set_pose falhou ($SET_POSE)"; }
sleep 1
# 6. Despausa: o plugin volta a esperar o SITL (bloqueando a física) até o novo SITL conectar.
world_control 'pause: false' || die "não consegui despausar o mundo"

# 7/8. Relança SITL e uav-api nos mesmos painéis, com os mesmos parâmetros.
log "subindo o SITL de novo ($(basename "$SIM_WORLD"))..."
tmux send-keys -t "$SIM_PANE_SITL" "clear; '$START' --sitl '$SIM_WORLD' $SIM_IP" C-m
sleep 3
tmux send-keys -t "$SIM_PANE_API" "clear; '$START' --api $SIM_IP" C-m

# 9. Espera a API responder de novo (até 120 s), para "reset_drone.sh && python3 missao.py".
if [[ $WAIT -eq 1 ]]; then
  log "esperando a uav-api (http://$SIM_IP:8000)..."
  ok=0
  for ((i = 0; i < 60; i++)); do
    if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:8000/docs"; then ok=1; break; fi
    sleep 2
  done
  [[ $ok -eq 1 ]] || die "a uav-api não respondeu em 120 s; veja o painel dela"
fi
log "drone reiniciado (as fotos em ${DRONE_PHOTOS_DIR:-$HOME/workspace/photos} continuam a numeração)"
