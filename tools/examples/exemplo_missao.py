#!/usr/bin/env python3
"""Exemplo mínimo de missão: uav_api (HTTP) + fotos gravadas pelo camera_saver.py.

Rode dentro do container, com a simulação no ar (start_simulation.sh):
    python3 ~/tools/examples/exemplo_missao.py

O que faz: espera a API, arma, decola a 5 m, voa 10 m para o norte, lê a foto mais recente
da câmera em $DRONE_PHOTOS_DIR (gravada pelo painel do camera_saver), mede o brilho médio
e pousa. Não usa ROS: as imagens chegam como arquivos PNG.
"""
import glob
import os
import time

import cv2
import requests

API = os.environ.get("UAV_API", "http://127.0.0.1:8000")
FOTOS = os.environ.get("DRONE_PHOTOS_DIR", os.path.expanduser("~/workspace/photos"))


def checar(r):
    if not r.ok:
        raise SystemExit(f"{r.request.method} {r.url} -> HTTP {r.status_code}: {r.text}")
    return r.json()


def get(path, **params):
    return checar(requests.get(API + path, params=params, timeout=180))


def post(path, body):
    return checar(requests.post(API + path, json=body, timeout=180))


def esperar_api():
    while True:
        try:
            get("/telemetry/gps")
            return
        except requests.RequestException:
            print("esperando uav-api em", API)
            time.sleep(3)


def foto_mais_recente():
    """Último frame_NNNNN.png gravado pelo camera_saver.py (espera até existir um)."""
    while True:
        fotos = sorted(glob.glob(os.path.join(FOTOS, "frame_*.png")))
        if fotos:
            return fotos[-1]
        print("esperando fotos em", FOTOS)
        time.sleep(2)


esperar_api()
print("arm:", get("/command/arm")["result"])
print("takeoff:", get("/command/takeoff", alt=5)["result"])
print("go_to:", post("/movement/go_to_ned_wait", {"x": 10, "y": 0, "z": -5})["result"])
pos = get("/telemetry/ned")["info"]["position"]
print(f"posição NED: x={pos['x']:.1f} y={pos['y']:.1f} z={pos['z']:.1f}")

caminho = foto_mais_recente()
img = cv2.imread(caminho)                     # numpy BGR, pronto para o OpenCV
print(f"foto {caminho}: {img.shape[1]}x{img.shape[0]}, brilho médio {img.mean():.0f}")

# /command/land bloqueia até pousar E desarmar; no Gazebo o desarme pode passar do limite de 30 s
# do uav_api e a chamada volta HTTP 500 com o drone já no chão. Então pousamos e conferimos a altura.
r = requests.get(API + "/command/land", timeout=180)
print("land:", r.json().get("result") or r.json().get("detail"))
while (z := get("/telemetry/ned")["info"]["position"]["z"]) < -0.3:
    print(f"descendo... altura {-z:.1f} m")
    time.sleep(2)
print("pousado")
