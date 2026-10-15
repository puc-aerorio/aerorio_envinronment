from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2 as cv
import numpy as np

@dataclass
class Base:
    centro: tuple[int, int]
    raio: int
    roi: np.ndarray
    forma: str | None = None
    numero: str | None = None
    aruco_id: int | None = None

# Referências de Hu moments — lista de observações por dígito.
# Populadas pelo script calibrar.py (K-means + medoides em espaço log-Hu).
# _match_digit faz 1-NN sobre todas as referências e retorna o dígito vencedor.
_REF_HU = {
    "3": [
        np.array([4.265288680371161e-01, 4.884663031517317e-02, 3.984147956139412e-03, 1.409054382723394e-03, -3.334834006469622e-06, -3.027418101383652e-04, -1.577151153755995e-07]),  # roi_020 from photo_6.034885227680206alt_20260512_143858.jpg (cluster 1, medoid 1/3)
        np.array([4.051028313097600e-01, 4.862491033585514e-02, 3.893840498959718e-03, 1.002617124527862e-03, -1.899710332275807e-06, -2.208141110259050e-04, -5.617768501438582e-07]),  # roi_089 from photo_7.035557568073273alt_20260512_144054.jpg (cluster 1, medoid 2/3)
        np.array([3.886696478064013e-01, 4.524667471059238e-02, 3.240715674156082e-03, 9.664920485062293e-04, -1.668540162562141e-06, -2.054328948118725e-04, -3.764493407039925e-07]),  # roi_049 from photo_6.193895697593689alt_20260512_142721.jpg (cluster 1, medoid 3/3)
    ],
    "4": [
        np.array([2.224654522895572e-01, 7.980281826738230e-03, 5.380714773608327e-03, 1.678094199183005e-04, 7.240811946832502e-08, 7.085001413238223e-06, -1.420693652710506e-07]),  # roi_091 from photo_7.466715633869171alt_20260512_143640.jpg (cluster 0, medoid 1/3)
        np.array([2.292256675884874e-01, 8.568385055136402e-03, 6.216505541385667e-03, 1.612526645253438e-04, 1.556639441983076e-08, 3.401997915954415e-06, -1.606961269255422e-07]),  # roi_093 from photo_7.615683376789093alt_20260512_143646.jpg (cluster 0, medoid 2/3)
        np.array([2.313355186040588e-01, 9.626064384349948e-03, 6.334809358718611e-03, 1.827287976920591e-04, 6.121213988583294e-09, 2.699912620882766e-06, -1.965018559858268e-07]),  # roi_083 from photo_6.62640655040741alt_20260512_135424.jpg (cluster 0, medoid 3/3)
    ],
    "5": [
        np.array([4.961975768552906e-01, 6.705419544827732e-02, 5.722911805074713e-04, 1.987399248584893e-04, -6.347890446909888e-08, 5.102479408483498e-05, 2.151201074604460e-08]),  # roi_069 from photo_6.259570002555847alt_20260512_142649.jpg (cluster 2, medoid 1/3)
        np.array([4.487869430623660e-01, 4.869070949530716e-02, 3.435385498493055e-04, 2.439419422445206e-04, -6.401750312675983e-08, 5.302262971690774e-05, 2.981120762361785e-08]),  # roi_052 from photo_6.216342329978943alt_20260512_142751.jpg (cluster 2, medoid 2/3)
        np.array([4.792168881015124e-01, 5.299094080456345e-02, 7.300093896912327e-04, 2.309687220067969e-04, -9.359410280787359e-08, 5.315747758925415e-05, 1.532548119123154e-08]),  # roi_027 from photo_6.045324146747589alt_20260512_143929.jpg (cluster 2, medoid 3/3)
    ],
}

def _calc_hough_params(altitude_m, hfov_deg, img_width_px, base_diameter_m=0.8):
    """Calcula minRadius, maxRadius e minDist baseado na altitude e FOV da câmera."""
    ground_width = 2 * altitude_m * math.tan(math.radians(hfov_deg / 2))
    px_per_m = img_width_px / ground_width
    base_radius_px = (base_diameter_m / 2) * px_per_m
    return {
        "minRadius": int(base_radius_px * 0.5),
        "maxRadius": int(base_radius_px * 1.5),
        "minDist": int(base_radius_px * 1.5),
    }

def _validate_circle(gray, x, y, r):
    """Valida se o círculo detectado é uma base (branca, com contraste contra o chão)."""
    h, w = gray.shape[:2]

    # Região interna (70% do raio)
    inner_mask = np.zeros((h, w), dtype=np.uint8)
    cv.circle(inner_mask, (x, y), int(r * 0.7), 255, -1)
    inner_pixels = gray[inner_mask == 255]

    # Anel externo (1.1r a 1.4r)
    outer_mask = np.zeros((h, w), dtype=np.uint8)
    cv.circle(outer_mask, (x, y), int(r * 1.4), 255, -1)
    cv.circle(outer_mask, (x, y), int(r * 1.1), 0, -1)
    outer_pixels = gray[outer_mask == 255]

    if len(inner_pixels) == 0:
        return False

    inner_mean = np.mean(inner_pixels)
    outer_mean = np.mean(outer_pixels) if len(outer_pixels) > 0 else inner_mean
    contrast = inner_mean - outer_mean

    if inner_mean > 140 and contrast > 30:
        return True

    # Fallback: base do gabarito tem ArUco escuro que baixa o brilho do centro,
    # mas a borda do círculo (anel 0.5r–1.0r) continua branca.
    ring_mask = np.zeros((h, w), dtype=np.uint8)
    cv.circle(ring_mask, (x, y), r, 255, -1)
    cv.circle(ring_mask, (x, y), int(r * 0.5), 0, -1)
    ring_pixels = gray[ring_mask == 255]
    ring_mean = np.mean(ring_pixels) if len(ring_pixels) > 0 else 0
    if ring_mean > 140 and (ring_mean - outer_mean) > 30:
        return True

    return False

def findBase(imagem, altitude_m, hfov_deg):

    gray = cv.cvtColor(imagem, cv.COLOR_BGR2GRAY)
    img_width_px = imagem.shape[1]
    hough_params = _calc_hough_params(altitude_m, hfov_deg, img_width_px)

    # CLAHE para realce de contraste local
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Filtro bilateral: suaviza textura do chão preservando bordas da base
    filtered = cv.bilateralFilter(enhanced, 9, 75, 75)

    # Suavização final para HoughCircles
    blur = cv.GaussianBlur(filtered, (9, 9), 2)


    circles = cv.HoughCircles(blur, cv.HOUGH_GRADIENT, dp=1.2,
                              minDist=hough_params["minDist"],
                              param1=50, param2=30,
                              minRadius=hough_params["minRadius"],
                              maxRadius=hough_params["maxRadius"])
    bases = []

    if circles is not None:
        circles = np.uint16(np.around(circles))
        altura, largura = gray.shape

        for i in circles[0, :]:
            x, y, r = int(i[0]), int(i[1]), int(i[2])

            if not _validate_circle(gray, x, y, r):
                continue

            y1, y2 = max(y-r, 0), min(y+r, altura)
            x1, x2 = max(x-r, 0), min(x+r, largura)

            roi = imagem[y1:y2, x1:x2]

            bases.append(Base(centro=(x, y), raio=r, roi=roi))

    return bases

# --- FUNÇÕES DE APOIO (Identify, Estimar, etc) ---

def _simple_classify_shape(roi):
    if roi is None or roi.size == 0:
        return {"forma": "Desconhecido", "numero": "N/A", "erro": 1.0}

    gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)

    # 2. Aumentar resolução (upscale)
    upscale = cv.resize(gray, None, fx=2, fy=2, interpolation=cv.INTER_CUBIC)

    # 3. Melhorar contraste
    contraste = cv.equalizeHist(upscale)

    # 4. Reduzir ruído
    blur = cv.GaussianBlur(contraste, (5, 5), 0)

    # 5. Binarização (separar objeto do fundo)
    _, thresh = cv.threshold(blur, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)

    # 6. Operação morfológica (fechar buracos)
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv.morphologyEx(thresh, cv.MORPH_CLOSE, kernel)

    # 7. Encontrar contornos — selecionar o blob mais centrado (interior da figura)
    h2, w2 = upscale.shape
    cx, cy = w2 // 2, h2 // 2
    r2 = min(h2, w2) // 2
    circle_area = math.pi * r2 * r2

    contornos, _ = cv.findContours(thresh, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)

    melhor = None
    melhor_dist = float("inf")

    for contorno in contornos:
        area = cv.contourArea(contorno)
        rel = area / circle_area
        if rel < 0.01 or rel > 0.85:
            continue
        M = cv.moments(contorno)
        if M["m00"] == 0:
            continue
        ccx = M["m10"] / M["m00"]
        ccy = M["m01"] / M["m00"]
        dist = math.sqrt((ccx - cx) ** 2 + (ccy - cy) ** 2)
        if dist > r2 * 0.6:
            continue
        if dist < melhor_dist:
            melhor_dist = dist
            melhor = contorno

    # melhor_contorno = None
    # melhor_rel = float("inf")

    # for contorno in contornos:
    #     peri = cv.arcLength(contorno, True)
    #     aprox = cv.approxPolyDP(contorno, 0.03 * peri, True)
    #     original_area = cv.contourArea(contorno)
    #     poli_area = cv.contourArea(aprox)
    #     if poli_area <=0:
    #         continue
    #     rel = original_area / poli_area

    #     #if rel < 0.2:
    #     #    continue

    #     if rel > melhor_rel:
    #         melhor_contorno = contorno
    #         melhor_rel = rel
        
    # melhor = melhor_contorno
    if melhor is None:
        return "Indefinida"

    
    area = cv.contourArea(melhor)
    peri = cv.arcLength(melhor, True)
    aprox = cv.approxPolyDP(melhor, 0.03 * peri, True)
    vertices = len(aprox)
    hull = cv.convexHull(melhor)
    hull_area = cv.contourArea(hull)
    convexidade = area / hull_area if hull_area > 0 else 1.0

    if vertices <= 4 and convexidade > 0.90:
        return "Triangulo"
    elif convexidade < 0.68:
        return "Estrela"
    else:
        return "Hexagono"
    # if vertices == 3:
    #     return "Triângulo"
    # if vertices == 5:
    #     return "Estrela"
    # if vertices == 6:
    #     return "Hexágono"
    # return "Indefinida"


def identifyBase(base: Base) -> Base:
    if base.roi is None or base.roi.size == 0:
        base.forma = "Indefinida"
        base.numero = None
        return base

    # 1. Tenta detectar o ArUco primeiro
    aruco_dict = cv.aruco.getPredefinedDictionary(cv.aruco.DICT_5X5_1000)
    aruco_params = cv.aruco.DetectorParameters()
    
    # Ajuste opcional de parâmetros para ROIs pequenas/com ruído
    aruco_params.adaptiveThreshWinSizeMin = 3
    aruco_params.adaptiveThreshWinSizeMax = 23
    aruco_params.adaptiveThreshWinSizeStep = 10
    
    detector = cv.aruco.ArucoDetector(aruco_dict, aruco_params)
    corners, ids, _ = detector.detectMarkers(base.roi)

    # 2. Classifica a forma geométrica (atribuindo a string corretamente)
    #forma_detectada = _simple_classify_shape(base.roi)
    #base.forma = forma_detectada if isinstance(forma_detectada, str) else "Indefinida"
    base.forma = _simple_classify_shape(base.roi)

    # 3. Se detectou ArUco, salva o ID e ignora a leitura do número por Hu Moments
    if ids is not None and len(ids) > 0:
        base.aruco_id = int(ids[0][0])
        base.numero = None  # O número será inferido via ID do ArUco na missão
        return base
    
    # 4. Se não for ArUco, estima o número impresso tradicional
    num = estimar_numero(base.roi)
    base.numero = num if num else None
    return base

def _extract_number_contour(roi):
    """Extrai o contorno do número central do ROI."""
    gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
    # Normalizar para tamanho fixo para garantir kernels consistentes
    # independente de altitude (3m real vs 6m Gazebo)
    TARGET = 400
    h0, w0 = gray.shape
    scale = TARGET / min(h0, w0)
    gray = cv.resize(gray, (int(w0 * scale), int(h0 * scale)), interpolation=cv.INTER_CUBIC)

    h, w = gray.shape
    cx, cy = w // 2, h // 2
    r = min(h, w) // 2

    # Máscara central (50% do raio) para isolar o número
    mask = np.zeros((h, w), dtype=np.uint8)
    cv.circle(mask, (cx, cy), int(r * 0.50), 255, -1)

    # CLAHE para melhorar contraste local (útil em imagens do Gazebo)
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    blur = cv.GaussianBlur(gray, (5, 5), 0)

    # Otsu apenas nos pixels dentro da máscara
    pixels_inside = blur[mask == 255]
    otsu_thresh, _ = cv.threshold(pixels_inside, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)

    # Aplica threshold: número escuro → branco
    _, thresh = cv.threshold(blur, otsu_thresh, 255, cv.THRESH_BINARY_INV)
    thresh = cv.bitwise_and(thresh, mask)

    # Morphological close para unir partes do número (kernel 3×3 preserva topologia do 5)
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv.morphologyEx(thresh, cv.MORPH_CLOSE, kernel)

    contours, _ = cv.findContours(thresh, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv.contourArea)


def _match_digit(contour):
    """Classifica o contorno como 3, 4 ou 5 via 1-NN sobre referências Hu.

    Compara contra todas as referências em _REF_HU (várias por dígito) usando
    distância I1 em espaço log. Retorna o dígito da referência mais próxima,
    ou None se nenhuma referência tem score abaixo de _MAX_SCORE.
    """
    mu = cv.moments(contour)
    if mu["m00"] == 0:
        return None
    hu = cv.HuMoments(mu).flatten()
    _MAX_SCORE = 15.0

    best_digit, best_score = None, float("inf")
    for digit, refs in _REF_HU.items():
        for ref in refs:
            score = 0.0
            for a, b in zip(hu[:7], ref[:7]):
                ma = -math.copysign(1, a) * math.log10(abs(a)) if a != 0 else 0
                mb = -math.copysign(1, b) * math.log10(abs(b)) if b != 0 else 0
                score += abs(ma - mb)
            if score < best_score:
                best_score = score
                best_digit = digit

    if best_score > _MAX_SCORE:
        return None
    return int(best_digit)

def desenhar_contorno_em_fundo_preto(contorno, largura, altura):
    """
    Cria uma imagem preta e desenha o contorno fornecido em verde.
    
    :param contorno: O contorno (array do OpenCV) a ser desenhado.
    :param largura: Largura da imagem de saída.
    :param altura: Altura da imagem de saída.
    :return: Imagem com o contorno desenhado.
    """
    # 1. Cria o fundo preto (zeros) com 3 canais de cor (BGR)
    # A ordem no numpy é (altura, largura, canais)
    fundo_preto = np.zeros((altura, largura, 3), dtype=np.uint8)
    
    # 2. Desenha o contorno
    # [contorno]: colocamos em uma lista
    # -1: indica para desenhar o contorno da lista (índice 0)
    # (0, 255, 0): Cor Verde em BGR
    # 2: Espessura da linha
    cv.drawContours(fundo_preto, [contorno], -1, (0, 255, 0), 2)
    
    return fundo_preto

def estimar_numero(roi):
    if roi is None or roi.size == 0:
        return None
    h, w = roi.shape[:2]
    if min(h, w) / max(h, w) < 0.85:
        return None
    contour = _extract_number_contour(roi)
    
    if contour is None:
        return None
    return _match_digit(contour)

def pixel_to_arena_offset(
    px: int, py: int,
    img_w: int, img_h: int,
    altitude: float,
    fov_h: float,
    fov_v: float,
) -> tuple[float, float]:
    """Converte coordenada em pixel para offset NED (norte, leste) em metros.

    A câmera aponta para baixo. O centro da imagem corresponde à posição do drone.
    px, py: coordenadas do pixel na imagem.
    altitude: altitude positiva em metros (ex: 2.0 para 2m de altura).
    Retorna (delta_x, delta_y).
    """
    # Offset em pixels do centro da imagem
    dx_px = px - img_w / 2
    dy_px = py - img_h / 2

    # Metros por pixel
    ground_w = 2 * altitude * math.tan(math.radians(fov_h / 2))
    ground_h = 2 * altitude * math.tan(math.radians(fov_v / 2))
    m_per_px_x = ground_w / img_w
    m_per_px_y = ground_h / img_h

    # Imagem: x→direita (leste), y→baixo (frente/norte)
    delta_x = dx_px * m_per_px_x
    delta_y = dy_px * m_per_px_y

    return (delta_y, delta_x)

# --- TESTE OFFLINE ---
# Uso: python3 vision.py caminho/para/frame.png [altitude_m]
# Imprime as bases detectadas na foto e grava final.png com as detecções desenhadas.
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("uso: python3 vision.py caminho/para/frame.png [altitude_m]")
        sys.exit(1)

    caminho = sys.argv[1]
    altitude = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    img = cv.imread(caminho)

    if img is None:
        print(f"Erro ao carregar imagem: {caminho}")
        sys.exit(1)

    canvas = img.copy()
    bases = findBase(img, altitude_m=altitude, hfov_deg=66.0)

    print("-" * 50)
    print(f"RESULTADOS DA ANÁLISE - {len(bases)} BASES DETECTADAS (altitude {altitude} m)")
    print("-" * 50)

    for i, base in enumerate(bases):
        identifyBase(base)

        print(f"BASE ID: {i}")
        print(f"  > Posição: Centro {base.centro}, Raio {base.raio}")
        print(f"  > Forma Detectada: {base.forma}")
        print(f"  > Número Lido: {base.numero}")
        if base.aruco_id is not None:
            print(f"  > ArUco ID: {base.aruco_id}")
        print("-" * 30)

        cv.circle(canvas, base.centro, base.raio, (0, 255, 0), 2)
        txt = f"ID:{i} {base.forma} #{base.numero}"
        cv.putText(canvas, txt, (base.centro[0]-base.raio, base.centro[1]-base.raio-10),
                   cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    cv.imwrite("final.png", canvas)
    print("imagem anotada gravada em final.png")
