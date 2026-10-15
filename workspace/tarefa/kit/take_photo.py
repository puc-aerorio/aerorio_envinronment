#!/usr/bin/env python3
"""Leitura da última foto da câmera do drone gravada pelo camera_saver.py.

O painel do camera_saver (start_simulation.sh) grava uma foto por segundo em
$DRONE_PHOTOS_DIR (padrão ~/workspace/photos) como frame_00000.png, frame_00001.png, ...
Este módulo só lê esses arquivos; não usa ROS.

Uso no script da missão:
    from take_photo import take_photo
    img = take_photo()               # última foto disponível (numpy BGR 1280x720)
    img = take_photo(wait_new=True)  # espera uma foto mais nova que a última devolvida

Teste no host/container:  python3 take_photo.py
"""
from __future__ import annotations

import os
import re
import time

import cv2
import numpy as np

FOTOS = os.environ.get("DRONE_PHOTOS_DIR", os.path.expanduser("~/workspace/photos"))
_FRAME_RE = re.compile(r"^frame_(\d{5})\.png$")

_ultimo_numero_devolvido = -1


def ultima_foto_path(pasta: str = FOTOS) -> str | None:
    """Caminho do frame_NNNNN.png de maior número em `pasta`, ou None se não houver nenhum."""
    try:
        nomes = os.listdir(pasta)
    except FileNotFoundError:
        return None
    melhor, melhor_n = None, -1
    for nome in nomes:
        m = _FRAME_RE.match(nome)
        if m and int(m.group(1)) > melhor_n:
            melhor, melhor_n = nome, int(m.group(1))
    return os.path.join(pasta, melhor) if melhor else None


def _numero(caminho: str) -> int:
    return int(_FRAME_RE.match(os.path.basename(caminho)).group(1))


def take_photo(wait_new: bool = False, timeout: float = 10.0, pasta: str = FOTOS) -> np.ndarray:
    """Devolve a última foto da câmera como imagem BGR (numpy), pronta para o OpenCV.

    wait_new=True: bloqueia até existir um frame mais novo que o último devolvido por esta
    função (o saver grava um por segundo, então a espera é de até ~1 s). Útil logo depois de
    um movimento, para a foto refletir a posição atual do drone.
    timeout: segundos máximos de espera (por foto nova ou por um arquivo ainda sendo gravado).
    Levanta RuntimeError se não houver foto utilizável dentro do prazo.
    """
    global _ultimo_numero_devolvido
    limite = time.monotonic() + timeout
    while True:
        caminho = ultima_foto_path(pasta)
        if caminho is not None and (not wait_new or _numero(caminho) > _ultimo_numero_devolvido):
            img = cv2.imread(caminho)  # None se o PNG ainda estiver sendo escrito
            if img is not None:
                _ultimo_numero_devolvido = _numero(caminho)
                return img
        if time.monotonic() > limite:
            if caminho is None:
                raise RuntimeError(f"take_photo: nenhuma foto frame_*.png em {pasta} "
                                   "(o painel do camera_saver está rodando?)")
            raise RuntimeError(f"take_photo: nenhuma foto nova/legível em {pasta} após {timeout:g}s")
        time.sleep(0.1)


if __name__ == "__main__":
    caminho = ultima_foto_path()
    print("pasta de fotos:", FOTOS)
    if caminho is None:
        raise SystemExit("nenhuma foto encontrada; inicie a simulação (start_simulation.sh) primeiro")
    img = take_photo()
    print(f"última foto: {caminho}")
    print(f"tamanho: {img.shape[1]}x{img.shape[0]}, brilho médio {img.mean():.0f}")
