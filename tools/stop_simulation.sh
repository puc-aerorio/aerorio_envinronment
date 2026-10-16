#!/usr/bin/env bash
# Encerra tudo que o start_simulation.sh subiu: a sessão tmux "drone" e os processos
# da simulação (Gazebo, SITL, MAVProxy, uav-api, ponte ROS 2, camera_saver).
#
# Uso: stop_simulation.sh [--purge]
#   --purge  apaga também os arquivos que o SITL deixa em $HOME
#            (eeprom.bin, logs/, terrain/, mav.parm, mav.tlog*)
set -uo pipefail

SESSION="drone"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

# Padrões (pgrep -f) dos processos da simulação, do mais "externo" ao mais "interno".
PATTERNS=(
  'camera_saver.py'
  'parameter_bridge'
  'uav-api|uav_api'
  'sim_vehicle.py'
  'mavproxy'
  'arducopter|arduplane'
  'gz sim'
)

# 1. Ctrl-C em cada painel da sessão, para os programas encerrarem de forma limpa.
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[stop] enviando Ctrl-C aos painéis da sessão '$SESSION'..."
  for pane in $(tmux list-panes -s -t "$SESSION" -F '#{pane_id}'); do
    tmux send-keys -t "$pane" C-c '' 2>/dev/null || true
  done
  sleep 3
fi

# 2. Processos que ainda estiverem vivos: SIGTERM, depois SIGKILL.
# Nunca mira no PID 1 (init do container), neste script nem no shell que o chamou.
alive() { pgrep -f "$1" 2>/dev/null | grep -vxE "1|$$|$PPID" || true; }
for p in "${PATTERNS[@]}"; do
  pids=$(alive "$p")
  [[ -n "$pids" ]] || continue
  echo "[stop] encerrando ($p): $(echo $pids | tr '\n' ' ')"
  kill $pids 2>/dev/null || true
done
sleep 2
for p in "${PATTERNS[@]}"; do
  pids=$(alive "$p")
  [[ -n "$pids" ]] || continue
  echo "[stop] forçando ($p): $(echo $pids | tr '\n' ' ')"
  kill -9 $pids 2>/dev/null || true
done

# 3. Sessão tmux.
if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION" && echo "[stop] sessão tmux '$SESSION' encerrada"
fi

# 4. Opcional: artefatos do SITL no $HOME.
if [[ $PURGE -eq 1 ]]; then
  for f in eeprom.bin mav.parm mav.tlog mav.tlog.raw logs terrain; do
    [[ -e "$HOME/$f" ]] && rm -rf "$HOME/$f" && echo "[stop] removido ~/$f"
  done
fi

# 5. Relatório.
left=""
for p in "${PATTERNS[@]}"; do pids=$(alive "$p"); [[ -n "$pids" ]] && left+="$p "; done
if [[ -n "$left" ]]; then
  echo "[stop] ATENÇÃO: ainda rodando: $left" >&2; exit 1
fi
others=$(tmux list-sessions -F '#{session_name}' 2>/dev/null | tr '\n' ' ')
[[ -n "$others" ]] && echo "[stop] outras sessões tmux (não tocadas): $others"
echo "[stop] simulação encerrada"
