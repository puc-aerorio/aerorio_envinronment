#!/usr/bin/env bash
# Normaliza a pasta de mundos/modelos vinda do Google Drive para funcionar no container:
#   1. remove arquivos "*Zone.Identifier*" (lixo do Windows);
#   2. troca caminhos absolutos da máquina de origem (file:///home/grelhas/gz_ws/src/ardupilot_gazebo/models/X)
#      por URIs portáveis model://X, resolvidas via GZ_SIM_RESOURCE_PATH;
#   3. falha se ainda sobrar alguma referência a "grelhas".
# Idempotente. Uso: normalize.sh [pasta]   (padrão: a pasta deste script)
set -euo pipefail

ROOT="$(readlink -f "${1:-$(dirname "${BASH_SOURCE[0]}")}")"
cd "$ROOT"

removed=$(find . -name '*Zone.Identifier*' -type f -print -delete | wc -l)
echo "[normalize] $ROOT: $removed arquivo(s) Zone.Identifier removido(s)"

# Só arquivos de texto (grep -I ignora binários: texturas, meshes binários etc.)
mapfile -t files < <(grep -rIl --exclude='normalize.sh' 'grelhas' . || true)
if [[ ${#files[@]} -gt 0 ]]; then
  sed -i \
    -e 's#file:///home/grelhas/gz_ws/src/ardupilot_gazebo/models/#model://#g' \
    -e 's#/home/grelhas/gz_ws/src/ardupilot_gazebo/#/home/ardupilot/tools/gazebo/#g' \
    -e 's#/home/grelhas/#/home/ardupilot/#g' \
    "${files[@]}"
  echo "[normalize] ${#files[@]} arquivo(s) reescrito(s):"; printf '  %s\n' "${files[@]}"
else
  echo "[normalize] nenhuma referência a 'grelhas' encontrada"
fi

if grep -rIn --exclude='normalize.sh' 'grelhas' . ; then
  echo "[normalize] ERRO: ainda há referências a 'grelhas' acima" >&2
  exit 1
fi
echo "[normalize] OK"
