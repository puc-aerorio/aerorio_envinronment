#!/usr/bin/env python3
"""Avaliador automático da tarefa de pouso autônomo (sistema de pontos).

É chamado pelo main() do template missao.py: iniciar() antes da missão, finalizar() depois.
Durante o voo, uma thread amostra a pose do drone a cada 0,5 s; no fim, calcula a pontuação,
imprime o detalhamento no console e acrescenta uma linha em resultados.csv.

Regras (máximo 100 pontos):
  Pouso concluído   drone no chão ao final e script sem exceção ................ 10
  Base correta      base mais próxima do pouso é a pedida e d <= 0,80 m ......... 50
  Precisão          (só se base correta) 25 * max(0, 1 - d / 0,50) ............. 0-25
  Tempo             15 * clamp((300 - t) / 240, 0, 1), t de iniciar() ao pouso . 0-15
  Altitude          -2 pontos por amostra (0,5 s) com altura > 6 m ............. penalidade
  Arena             qualquer amostra fora de 14x8 m (+0,5 m) -> eliminado, total 0

O gabarito (posição das bases) é lido do SDF do mundo; a pose do drone vem do Gazebo
(`gz model`), com fallback para /telemetry/ned da uav-api.

Teste sem simulação:  python3 avaliador.py --teste
"""
from __future__ import annotations

import csv
import math
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# Regras de pontuação
# ---------------------------------------------------------------------------
PTS_POUSO = 10.0
PTS_BASE = 50.0
RAIO_BASE_OK_M = 0.80          # distância máxima para contar "pousou na base"
PTS_PRECISAO_MAX = 25.0
PRECISAO_D_ZERO_M = 0.50       # distância em que a precisão vale 0
PTS_TEMPO_MAX = 15.0
TEMPO_CHEIO_S = 60.0           # até aqui, tempo vale o máximo
TEMPO_ZERO_S = 300.0           # a partir daqui, tempo vale 0
ALT_MAX_M = 6.0
PENALIDADE_POR_AMOSTRA = 2.0
INTERVALO_AMOSTRA_S = 0.5
ARENA_X_M = (-4.0, 4.0)        # limites da arena no frame do Gazebo (linhas azuis)
ARENA_Y_M = (-7.0, 7.0)
MARGEM_ARENA_M = 0.5
ALTURA_POUSADO_M = 0.3         # abaixo disso o drone é considerado no chão
ALTURA_DECOLOU_M = 1.0         # acima disso considera-se que decolou
ESPERA_POUSO_S = 60.0          # quanto finalizar() espera o drone tocar o solo
MODELO_DRONE = "iris_with_gimbal"

FORMAS = {"triangulo": "Triangulo", "estrela": "Estrela", "hexagono": "Hexagono"}
_RE_BASE = re.compile(r"^(hexagono|triangulo|estrela)(\d)$")


def pontos_precisao(d: float) -> float:
    """Linear contínua: 25 em d=0, 0 em d >= 0,50 m."""
    return PTS_PRECISAO_MAX * max(0.0, 1.0 - d / PRECISAO_D_ZERO_M)


def pontos_tempo(t: float) -> float:
    """Linear contínua: 15 até 60 s, decai a 0 em 300 s."""
    frac = (TEMPO_ZERO_S - t) / (TEMPO_ZERO_S - TEMPO_CHEIO_S)
    return PTS_TEMPO_MAX * min(1.0, max(0.0, frac))


def penalidade_altitude(amostras_acima: int) -> float:
    return PENALIDADE_POR_AMOSTRA * amostras_acima


def dentro_da_arena(x: float, y: float) -> bool:
    m = MARGEM_ARENA_M
    return (ARENA_X_M[0] - m <= x <= ARENA_X_M[1] + m) and (ARENA_Y_M[0] - m <= y <= ARENA_Y_M[1] + m)


def calcular_pontuacao(pousou: bool, sem_erro: bool, base_correta: bool, dist_m: float | None,
                       tempo_s: float, amostras_acima: int, saiu_arena: bool) -> dict:
    """Aplica as regras e devolve as parcelas e o total. Função pura (testável)."""
    pts_pouso = PTS_POUSO if (pousou and sem_erro) else 0.0
    pts_base = PTS_BASE if base_correta else 0.0
    pts_prec = pontos_precisao(dist_m) if (base_correta and dist_m is not None) else 0.0
    pts_tempo = pontos_tempo(tempo_s) if pousou else 0.0
    pen_alt = penalidade_altitude(amostras_acima)
    bruto = pts_pouso + pts_base + pts_prec + pts_tempo - pen_alt
    total = 0.0 if saiu_arena else max(0.0, bruto)
    return {
        "pts_pouso": pts_pouso, "pts_base": pts_base, "pts_precisao": pts_prec,
        "pts_tempo": pts_tempo, "penalidade_altitude": pen_alt,
        "eliminado": saiu_arena, "pontos_total": total,
    }


# ---------------------------------------------------------------------------
# Gabarito: bases do mundo, lidas do SDF
# ---------------------------------------------------------------------------
@dataclass
class BaseGabarito:
    nome: str
    forma: str
    numero: int
    x: float
    y: float


def normalizar_forma(forma: str) -> str:
    s = unicodedata.normalize("NFKD", forma).encode("ascii", "ignore").decode().lower().strip()
    if s not in FORMAS:
        raise ValueError(f"forma inválida: {forma!r} (use Triangulo, Estrela ou Hexagono)")
    return FORMAS[s]


def localizar_sdf(mundo: str, inicio: str | None = None) -> str | None:
    """Procura gazebo/worlds/<mundo>.sdf: $MISSAO_SDF; depois subindo os diretórios a partir
    de `inicio` e da pasta deste módulo; por fim ~/workspace/gazebo/worlds."""
    env = os.environ.get("MISSAO_SDF")
    if env and os.path.isfile(env):
        return env
    nome = mundo if mundo.endswith(".sdf") else mundo + ".sdf"
    pontos_de_partida = [inicio, os.path.dirname(os.path.abspath(__file__))]
    for d in filter(None, pontos_de_partida):
        d = os.path.abspath(d)
        for _ in range(8):
            cand = os.path.join(d, "gazebo", "worlds", nome)
            if os.path.isfile(cand):
                return cand
            pai = os.path.dirname(d)
            if pai == d:
                break
            d = pai
    cand = os.path.expanduser(f"~/workspace/gazebo/worlds/{nome}")
    return cand if os.path.isfile(cand) else None


def ler_bases_sdf(caminho: str) -> list[BaseGabarito]:
    """Bases brancas (forma+número) incluídas no mundo. Ignora gabarito (ArUco) e base azul."""
    bases = []
    for inc in ET.parse(caminho).getroot().iter("include"):
        nome = (inc.findtext("name") or inc.findtext("uri") or "").strip()
        nome = nome.replace("model://", "")
        m = _RE_BASE.match(nome)
        if not m:
            continue
        pose = (inc.findtext("pose") or "0 0 0 0 0 0").split()
        bases.append(BaseGabarito(nome, FORMAS[m.group(1)], int(m.group(2)),
                                  float(pose[0]), float(pose[1])))
    return bases


# ---------------------------------------------------------------------------
# Fontes de pose (x, y, z no frame do Gazebo, o mesmo das bases do SDF)
# ---------------------------------------------------------------------------
_RE_XYZ = re.compile(r"\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]")


def pose_gz(modelo: str = MODELO_DRONE) -> tuple[float, float, float] | None:
    """Pose do modelo pelo CLI do Gazebo (`gz model -m <modelo> -p`)."""
    try:
        r = subprocess.run(["gz", "model", "-m", modelo, "-p"], capture_output=True,
                           text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    saida = r.stdout
    i = saida.find("Pose")
    m = _RE_XYZ.search(saida, i if i >= 0 else 0)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


class PoseTelemetria:
    """Fallback: /telemetry/ned convertido para o frame do Gazebo.

    Suposição (plugin ArduPilot com gazeboXYZToNED = 0 0 0 180 0 90, ENU padrão):
    Gazebo x = leste, Gazebo y = norte, Gazebo z = -down. A origem NED (EKF) é tomada como a
    posição inicial do drone, que no mundo missao1 é a origem do Gazebo.
    """

    def __init__(self, api: str):
        self.api = api
        self.origem = None

    def __call__(self) -> tuple[float, float, float] | None:
        import requests  # importado aqui para o módulo funcionar sem requests no modo --teste
        try:
            p = requests.get(self.api + "/telemetry/ned", timeout=5).json()["info"]["position"]
        except Exception:
            return None
        n, e, d = float(p["x"]), float(p["y"]), float(p["z"])
        if self.origem is None:
            self.origem = (n, e, d)
        n0, e0, d0 = self.origem
        return e - e0, n - n0, -(d - d0)


# ---------------------------------------------------------------------------
# Avaliador
# ---------------------------------------------------------------------------
CSV_COLUNAS = ["data_hora", "aluno", "mundo", "forma", "numero", "status", "pontos_total",
               "eliminado", "pts_pouso", "pts_base", "pts_precisao", "pts_tempo",
               "penalidade_altitude", "dist_base_m", "base_mais_proxima", "tempo_s",
               "alt_max_m", "amostras_acima_6m", "saiu_arena", "erro"]


class Avaliador:
    def __init__(self, forma: str, numero: int, api: str = "http://127.0.0.1:8000",
                 mundo: str = "missao1", pasta_saida: str | None = None, aluno: str | None = None,
                 fonte_pose=None, sdf: str | None = None, intervalo: float = INTERVALO_AMOSTRA_S,
                 relogio=time.monotonic):
        self.forma = normalizar_forma(forma)
        self.numero = int(numero)
        self.api = api
        self.mundo = mundo
        self.pasta_saida = pasta_saida or os.path.dirname(os.path.abspath(__file__))
        self.aluno = aluno or os.environ.get("ALUNO") or os.path.basename(self.pasta_saida.rstrip("/"))
        self.intervalo = intervalo
        self.relogio = relogio
        self._fonte_pose = fonte_pose

        self.sdf = sdf or localizar_sdf(mundo, self.pasta_saida)
        if not self.sdf:
            raise FileNotFoundError(
                f"avaliador: não achei gazebo/worlds/{mundo}.sdf a partir de {self.pasta_saida}; "
                "defina MISSAO_SDF=/caminho/para/o/mundo.sdf")
        self.bases = ler_bases_sdf(self.sdf)
        if not self.bases:
            raise RuntimeError(f"avaliador: nenhuma base (forma+número) encontrada em {self.sdf}")
        if not any(b.forma == self.forma and b.numero == self.numero for b in self.bases):
            print(f"[avaliador] AVISO: não existe base {self.forma} {self.numero} em {self.sdf}")

        # estado da execução
        self.t0 = None
        self.z0 = 0.0
        self.ultima_pose = None
        self.alt_max = 0.0
        self.amostras_acima = 0
        self.saiu_arena = False
        self.ponto_saida = None
        self.decolou = False
        self.t_pouso = None
        self.erro = ""
        self.status = "ok"
        self._parar = threading.Event()
        self._thread = None

    # ------------------------------------------------------------------ pose
    def _escolher_fonte(self):
        if self._fonte_pose is not None:
            return self._fonte_pose
        if pose_gz() is not None:
            print("[avaliador] pose do drone: Gazebo (gz model)")
            return pose_gz
        print("[avaliador] pose do drone: /telemetry/ned (fallback; gz model indisponível)")
        return PoseTelemetria(self.api)

    def _amostrar(self) -> None:
        p = self._fonte_pose()
        if p is None:
            return
        x, y, z = p
        alt = z - self.z0
        self.ultima_pose = (x, y, alt)
        self.alt_max = max(self.alt_max, alt)
        if alt > ALT_MAX_M:
            self.amostras_acima += 1
        if not dentro_da_arena(x, y) and not self.saiu_arena:
            self.saiu_arena = True
            self.ponto_saida = (x, y)
            print(f"[avaliador] ELIMINADO: drone saiu da arena em x={x:.2f} y={y:.2f}")
        if alt > ALTURA_DECOLOU_M:
            self.decolou = True
        elif self.decolou and alt < ALTURA_POUSADO_M and self.t_pouso is None:
            self.t_pouso = self.relogio()

    def _loop(self) -> None:
        while not self._parar.is_set():
            try:
                self._amostrar()
            except Exception as e:  # noqa: BLE001 - a amostragem nunca pode derrubar a missão
                print(f"[avaliador] erro ao amostrar pose: {e}")
            self._parar.wait(self.intervalo)

    # ------------------------------------------------------------------ API
    def iniciar(self, thread: bool = True) -> None:
        """Chame imediatamente antes de armar/decolar."""
        self._fonte_pose = self._escolher_fonte()
        limite = time.monotonic() + 10
        p = None
        while p is None and time.monotonic() < limite:
            p = self._fonte_pose()
            if p is None:
                time.sleep(0.5)
        if p is None:
            print("[avaliador] AVISO: sem pose inicial; altura será relativa a z=0")
        else:
            self.z0 = p[2]
        self.t0 = self.relogio()
        self._amostrar()
        print(f"[avaliador] objetivo {self.forma} {self.numero} | {len(self.bases)} bases em "
              f"{os.path.basename(self.sdf)} | amostragem a cada {self.intervalo:g}s")
        if thread:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="avaliador")
            self._thread.start()

    def registrar_erro(self, erro) -> None:
        if isinstance(erro, BaseException):
            self.erro = f"{type(erro).__name__}: {erro}"
            self.status = "excecao"
        else:
            self.erro = str(erro)
            self.status = "interrompido" if "interromp" in self.erro else "erro"

    def finalizar(self) -> dict:
        """Para a amostragem, espera o pouso, pontua, imprime e grava o CSV."""
        if self.t0 is None:
            raise RuntimeError("avaliador: finalizar() chamado antes de iniciar()")
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=5)

        # Espera o drone tocar o solo (o /command/land pode voltar antes do desarme).
        limite = time.monotonic() + ESPERA_POUSO_S
        avisou = False
        while time.monotonic() < limite:
            self._amostrar()
            alt = self.ultima_pose[2] if self.ultima_pose else None
            if alt is not None and alt < ALTURA_POUSADO_M:
                break
            if not avisou:
                print("[avaliador] aguardando o drone tocar o solo...")
                avisou = True
            time.sleep(self.intervalo)

        alt_final = self.ultima_pose[2] if self.ultima_pose else None
        pousou = alt_final is not None and alt_final < ALTURA_POUSADO_M
        fim = self.t_pouso if (pousou and self.t_pouso is not None) else self.relogio()
        tempo_s = fim - self.t0

        dist, mais_proxima, base_correta = None, None, False
        if self.ultima_pose:
            x, y, _ = self.ultima_pose
            mais_proxima = min(self.bases, key=lambda b: math.hypot(b.x - x, b.y - y))
            dist = math.hypot(mais_proxima.x - x, mais_proxima.y - y)
            base_correta = (pousou and mais_proxima.forma == self.forma
                            and mais_proxima.numero == self.numero and dist <= RAIO_BASE_OK_M)

        pts = calcular_pontuacao(pousou, self.status == "ok", base_correta, dist, tempo_s,
                                 self.amostras_acima, self.saiu_arena)
        res = {
            "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "aluno": self.aluno, "mundo": self.mundo, "forma": self.forma, "numero": self.numero,
            "status": self.status, **pts,
            "dist_base_m": None if dist is None else round(dist, 3),
            "base_mais_proxima": mais_proxima.nome if mais_proxima else "",
            "tempo_s": round(tempo_s, 1), "alt_max_m": round(self.alt_max, 2),
            "amostras_acima_6m": self.amostras_acima, "saiu_arena": self.saiu_arena,
            "erro": self.erro, "pousou": pousou, "base_correta": base_correta,
        }
        self._imprimir(res, mais_proxima)
        self._gravar_csv(res)
        return res

    # ------------------------------------------------------------------ saída
    def _imprimir(self, r: dict, mais_proxima) -> None:
        L = 78

        def linha(rotulo, descricao, pontos=None, maximo=None):
            direita = ""
            if pontos is not None:
                direita = f"{pontos:7.2f}" + (f" / {maximo:.0f}" if maximo is not None else "")
            esquerda = f" {rotulo:<17} {descricao}"
            return f"{esquerda:<{L - len(direita)}}{direita}"

        alvo = f"{self.forma} {self.numero}"
        prox = f"{mais_proxima.forma} {mais_proxima.numero}" if mais_proxima else "?"
        d = "-" if r["dist_base_m"] is None else f"{r['dist_base_m']:.2f} m"
        sim_nao = lambda v: "sim" if v else "não"  # noqa: E731
        linhas = [
            "",
            "=" * L,
            f" AVALIAÇÃO   objetivo: {alvo}   aluno: {self.aluno}   status: {r['status']}",
            "=" * L,
            linha("Pouso concluído", f"no chão: {sim_nao(r['pousou'])}, sem exceção: "
                  f"{sim_nao(r['status'] == 'ok')}", r["pts_pouso"], PTS_POUSO),
            linha("Base correta", f"mais próxima: {prox}, d = {d} (limite {RAIO_BASE_OK_M:.2f} m)",
                  r["pts_base"], PTS_BASE),
            linha("Precisão", f"25 · max(0, 1 − d/{PRECISAO_D_ZERO_M:.2f})", r["pts_precisao"],
                  PTS_PRECISAO_MAX),
            linha("Tempo", f"t = {r['tempo_s']:.1f} s; 15 · clamp((300 − t)/240, 0, 1)",
                  r["pts_tempo"], PTS_TEMPO_MAX),
            linha("Altitude", f"máx {r['alt_max_m']:.2f} m; {r['amostras_acima_6m']} amostra(s) "
                  f"> {ALT_MAX_M:.0f} m × (−{PENALIDADE_POR_AMOSTRA:.0f})", -r["penalidade_altitude"]),
            linha("Arena", "SAIU DA ARENA → ELIMINADO (total = 0)" if r["saiu_arena"]
                  else "permaneceu dentro"),
            "-" * L,
            linha("TOTAL", "", r["pontos_total"], 100),
            "=" * L,
        ]
        if r["erro"]:
            linhas.append(f" erro: {r['erro']}")
        linhas.append(f" csv:  {os.path.join(self.pasta_saida, 'resultados.csv')}")
        print("\n".join(linhas), flush=True)

    def _gravar_csv(self, r: dict) -> None:
        caminho = os.path.join(self.pasta_saida, "resultados.csv")
        novo = not os.path.exists(caminho)
        with open(caminho, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUNAS, extrasaction="ignore")
            if novo:
                w.writeheader()
            linha = dict(r)
            for k in ("pontos_total", "pts_pouso", "pts_base", "pts_precisao", "pts_tempo",
                      "penalidade_altitude"):
                linha[k] = f"{r[k]:.2f}"
            linha["eliminado"] = "sim" if r["eliminado"] else "nao"
            linha["saiu_arena"] = "sim" if r["saiu_arena"] else "nao"
            w.writerow(linha)


# ---------------------------------------------------------------------------
# Modo de teste (sem Gazebo nem uav-api): trajetórias sintéticas
# ---------------------------------------------------------------------------
def _teste() -> int:
    import tempfile

    class Relogio:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

    def trajetoria(destino, duracao_s, alt=5.0, n_acima=0, fora_arena=False, z0=0.225):
        """Poses (x, y, z) com pose k no instante k·0,5 s: sobe, cruza, (opcionais), desce e
        toca o solo exatamente em duracao_s."""
        n = int(round(duracao_s / INTERVALO_AMOSTRA_S))
        tx, ty = destino
        poses = []
        for k in range(n + 1):
            f = k / n
            if f < 0.2:
                poses.append((0.0, 0.0, z0 + alt * (f / 0.2)))
            elif f < 0.8:
                g = (f - 0.2) / 0.6
                poses.append((tx * g, ty * g, z0 + alt))
            else:
                g = (f - 0.8) / 0.2
                poses.append((tx, ty, z0 + max(0.5, alt * (1 - g))))  # só toca o solo no fim
        poses[-1] = (tx, ty, z0)
        meio = n // 2
        for i in range(n_acima):
            x, y, _ = poses[meio + i]
            poses[meio + i] = (x, y, z0 + ALT_MAX_M + 0.5)
        if fora_arena:
            poses[meio] = (ARENA_X_M[1] + 2.0, 0.0, z0 + alt)
        return poses

    def rodar(nome, forma, numero, poses, status_erro=None):
        rel = Relogio()
        estado = {"k": -1}

        def fonte():
            # 1ª chamada (sondagem em iniciar) devolve a pose 0 em t=0; depois avança 0,5 s por chamada
            if estado["k"] >= 0:
                rel.t += INTERVALO_AMOSTRA_S
            estado["k"] += 1
            return poses[min(estado["k"], len(poses) - 1)]

        av = Avaliador(forma, numero, pasta_saida=pasta, aluno="teste", fonte_pose=fonte,
                       intervalo=0.0, relogio=rel, sdf=sdf)
        av.iniciar(thread=False)
        for _ in range(len(poses)):
            av._amostrar()
        if status_erro:
            av.registrar_erro(status_erro)
        print(f"\n### caso: {nome}")
        return av.finalizar()

    pasta = tempfile.mkdtemp(prefix="avaliador_teste_")
    sdf = localizar_sdf("missao1")
    if not sdf:
        print("não achei gazebo/worlds/missao1.sdf (defina MISSAO_SDF)")
        return 1
    print("SDF:", sdf)
    bases = ler_bases_sdf(sdf)
    print("bases do gabarito:", ", ".join(f"{b.nome}({b.x:.1f},{b.y:.1f})" for b in bases))
    alvo = next(b for b in bases if b.nome == "hexagono5")
    outra = next(b for b in bases if b.nome == "triangulo4")
    perto = (alvo.x + 0.15, alvo.y)

    falhas = []

    def espera(nome, r, total, **campos):
        ok = abs(r["pontos_total"] - total) < 0.05
        for k, v in campos.items():
            ok = ok and r[k] == v
        print(f"--> {nome}: total {r['pontos_total']:.2f} (esperado {total:.2f}) {'OK' if ok else 'FALHOU'}")
        if not ok:
            falhas.append(nome)

    r = rodar("pouso a 0,15 m da hexagono5, 120 s", "Hexagono", 5, trajetoria(perto, 120))
    espera("A", r, 10 + 50 + 17.5 + 11.25, eliminado=False)
    r = rodar("idem + 6 amostras acima de 6 m", "Hexagono", 5, trajetoria(perto, 120, n_acima=6))
    espera("B", r, 10 + 50 + 17.5 + 11.25 - 12, amostras_acima_6m=6)
    r = rodar("idem + uma amostra fora da arena", "Hexagono", 5, trajetoria(perto, 120, fora_arena=True))
    espera("C", r, 0.0, eliminado=True)
    r = rodar("base errada (triangulo4)", "Hexagono", 5, trajetoria((outra.x, outra.y), 120))
    espera("D", r, 10 + 0 + 0 + 11.25, base_mais_proxima="triangulo4")
    r = rodar("400 s de voo", "Hexagono", 5, trajetoria(perto, 400))
    espera("E", r, 10 + 50 + 17.5 + 0)
    r = rodar("exceção no script (pousado)", "Hexagono", 5, trajetoria(perto, 120),
              status_erro=RuntimeError("falha simulada"))
    espera("F", r, 0 + 50 + 17.5 + 11.25, status="excecao")

    print("\nCSV gerado:", os.path.join(pasta, "resultados.csv"))
    with open(os.path.join(pasta, "resultados.csv"), encoding="utf-8") as f:
        print(f.read())
    if falhas:
        print("FALHAS:", falhas)
        return 1
    print("todos os casos OK")
    return 0


if __name__ == "__main__":
    if "--teste" in sys.argv:
        sys.exit(_teste())
    print(__doc__)
