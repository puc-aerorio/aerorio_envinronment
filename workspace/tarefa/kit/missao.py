#!/usr/bin/env python3
"""Tarefa: pouso autônomo na base com a forma e o número pedidos (mundo missao1).

Uso (no painel livre do container, com a simulação no ar):
    python3 missao.py --forma Hexagono --numero 5

Implemente SOMENTE a função missao() abaixo. O restante do arquivo (CLI, helpers HTTP e
avaliador) faz parte do contrato da tarefa e não deve ser alterado.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

import requests

from avaliador import Avaliador
from take_photo import take_photo                                   # noqa: F401
from vision import Base, findBase, identifyBase, pixel_to_arena_offset  # noqa: F401

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
API = os.environ.get("UAV_API", "http://127.0.0.1:8000")   # uav-api (painel 2)
MUNDO = "missao1"

IMG_W, IMG_H = 1280, 720     # resolução da câmera do gimbal
FOV_H, FOV_V = 66.0, 40.1    # campo de visão horizontal/vertical (graus)


# ---------------------------------------------------------------------------
# Helpers HTTP para a uav-api (documentação interativa em http://localhost:8000/docs)
# ---------------------------------------------------------------------------
def checar(r: requests.Response) -> dict:
    if not r.ok:
        raise RuntimeError(f"{r.request.method} {r.url} -> HTTP {r.status_code}: {r.text}")
    return r.json()


def get(path: str, **params) -> dict:
    """GET na uav-api. Ex.: get("/command/takeoff", alt=5)"""
    return checar(requests.get(API + path, params=params, timeout=180))


def post(path: str, body: dict) -> dict:
    """POST na uav-api. Ex.: post("/movement/go_to_ned_wait", {"x": 2, "y": 0, "z": -5})"""
    return checar(requests.post(API + path, json=body, timeout=180))


def altura_m() -> float:
    """Altura atual acima do ponto de decolagem, em metros (NED: z negativo = para cima)."""
    return -float(get("/telemetry/ned")["info"]["position"]["z"])


def esperar_api() -> None:
    while True:
        try:
            get("/telemetry/gps")
            return
        except requests.RequestException:
            print("esperando uav-api em", API)
            time.sleep(3)


# ---------------------------------------------------------------------------
# SUA SOLUÇÃO
# ---------------------------------------------------------------------------
def missao(forma: str, numero: int) -> None:
    """Controla o drone até pousar sobre a base branca com `forma` e `numero`.

    forma:  "Triangulo", "Estrela" ou "Hexagono"
    numero: 3, 4 ou 5

    Ao retornar, o drone deve estar no chão. Se a base não for encontrada, pouse em
    segurança e informe no console. Veja o PDF da tarefa para a interface de
    take_photo(), findBase(), identifyBase(), pixel_to_arena_offset() e da uav-api.
    """
    # TODO: implemente aqui a lógica de controle.
    raise NotImplementedError("missao() ainda não foi implementada")


# ---------------------------------------------------------------------------
# Programa principal (não alterar)
# ---------------------------------------------------------------------------
def main() -> int:
    global API
    ap = argparse.ArgumentParser(description="Pouso autônomo na base indicada (mundo missao1).")
    ap.add_argument("--forma", required=True, choices=["Triangulo", "Estrela", "Hexagono"])
    ap.add_argument("--numero", required=True, type=int, choices=[3, 4, 5])
    ap.add_argument("--api", default=API, help=f"URL da uav-api (padrão: {API})")
    args = ap.parse_args()
    API = args.api

    print(f"objetivo: {args.forma} {args.numero}   api: {API}   mundo: {MUNDO}")
    esperar_api()

    av = Avaliador(forma=args.forma, numero=args.numero, api=API, mundo=MUNDO,
                   pasta_saida=os.path.dirname(os.path.abspath(__file__)))
    av.iniciar()
    try:
        missao(args.forma, args.numero)
    except KeyboardInterrupt:
        print("\ninterrompido pelo usuário (Ctrl+C)")
        av.registrar_erro("interrompido")
    except Exception as e:  # noqa: BLE001 - o avaliador precisa registrar qualquer falha
        traceback.print_exc()
        av.registrar_erro(e)
    finally:
        resultado = av.finalizar()
    return 0 if resultado["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
