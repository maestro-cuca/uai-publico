#!/usr/bin/env python3
"""Prepara o chão do mapa da UAI: rios, represa, matas, ruas, pontes e o relevo.

    pip install -r ferramentas/requirements.txt
    python3 ferramentas/preparar_mapa.py

Corre-se raramente (quando se quer o mapa mais fresco). Escreve:
    mapa/regiao.json   — camadas já projetadas em metros, simplificadas
    mapa/relevo.jpg    — o relevo sombreado, com a cor da altitude

Procedência (Lei 4 vale também para o chão):
    - geografia: © colaboradores do OpenStreetMap, licença ODbL (Overpass API)
    - altitude: Terrain Tiles (Mapzen / AWS Open Data, derivado do SRTM e outros)

Nada aqui se inventa: se um rio não está no OpenStreetMap, não está no mapa.
Os lugares da UAI não vêm daqui — vêm de mapa/onde.json, cada um com a sua fonte.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import contourpy
import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "mapa"

# Passos, com a margem sul da represa de Peixoto lá em cima. A missão agora é a cidade.
NORTE, SUL, OESTE, LESTE = -20.650, -20.775, -46.685, -46.555
LAT0 = (NORTE + SUL) / 2
KX = 111_320 * math.cos(math.radians(LAT0))  # metros por grau de longitude
KY = 110_574  # metros por grau de latitude
LARGURA = round((LESTE - OESTE) * KX)
ALTURA = round((NORTE - SUL) * KY)
MARGEM = 600  # metros para lá da moldura, para nada acabar à vista

ESPELHOS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
UA = {"User-Agent": "uai-mapa/0.1 (mapa comunitario)"}
CACHE = Path(__file__).resolve().parent / ".cache"  # o que se baixou (fora do git); apague para refrescar


def proj(lat: float, lon: float) -> tuple[float, float]:
    return (lon - OESTE) * KX, (NORTE - lat) * KY


# ───────────────────────── geometria ─────────────────────────


def dp(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas–Peucker, iterativo."""
    if len(pts) < 3:
        return pts
    manter = [False] * len(pts)
    manter[0] = manter[-1] = True
    pilha = [(0, len(pts) - 1)]
    while pilha:
        a, b = pilha.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1e-9
        pior, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / n if (dx or dy) else math.hypot(px - ax, py - ay)
            if d > pior:
                pior, idx = d, i
        if pior > tol:
            manter[idx] = True
            pilha += [(a, idx), (idx, b)]
    return [p for p, m in zip(pts, manter) if m]


def _dentro(p, x0=-MARGEM, y0=-MARGEM, x1=LARGURA + MARGEM, y1=ALTURA + MARGEM):
    return x0 <= p[0] <= x1 and y0 <= p[1] <= y1


def cortar_linha(pts):
    """Parte a linha nos troços que entram na moldura (com um ponto de folga)."""
    trocos, atual = [], []
    for i, p in enumerate(pts):
        perto = _dentro(p) or (i > 0 and _dentro(pts[i - 1])) or (i + 1 < len(pts) and _dentro(pts[i + 1]))
        if perto:
            atual.append(p)
        elif atual:
            trocos.append(atual)
            atual = []
    if atual:
        trocos.append(atual)
    return [t for t in trocos if len(t) > 1]


def cortar_anel(pts):
    """Sutherland–Hodgman contra a moldura alargada."""
    x0, y0, x1, y1 = -MARGEM, -MARGEM, LARGURA + MARGEM, ALTURA + MARGEM
    lados = [
        (lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
        (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1)),
    ]
    saida = list(pts)
    for dentro, cruza in lados:
        entrada, saida = saida, []
        if not entrada:
            break
        ant = entrada[-1]
        for p in entrada:
            if dentro(p):
                if not dentro(ant):
                    saida.append(cruza(ant, p))
                saida.append(p)
            elif dentro(ant):
                saida.append(cruza(ant, p))
            ant = p
    return saida if len(saida) > 2 else []


def juntar_aneis(caminhos: list[list]) -> list[list]:
    """Junta os troços de um multipolígono em anéis fechados (pontas iguais)."""
    abertos = [list(c) for c in caminhos if len(c) > 1]
    aneis = []
    while abertos:
        anel = abertos.pop()
        mudou = True
        while anel[0] != anel[-1] and mudou:
            mudou = False
            for i, c in enumerate(abertos):
                if c[0] == anel[-1]:
                    anel += c[1:]
                elif c[-1] == anel[-1]:
                    anel += c[::-1][1:]
                elif c[-1] == anel[0]:
                    anel = c + anel[1:]
                elif c[0] == anel[0]:
                    anel = c[::-1] + anel[1:]
                else:
                    continue
                abertos.pop(i)
                mudou = True
                break
        if anel[0] == anel[-1] and len(anel) > 3:
            aneis.append(anel)
    return aneis


def plano(pts) -> list[int]:
    """[(x, y), …] → [x, y, x, y, …] em metros inteiros (1 m chega)."""
    out = []
    for x, y in pts:
        out += [round(x), round(y)]
    return out


# ───────────────────────── OpenStreetMap ─────────────────────────

CONSULTA = """[out:json][timeout:180][bbox:{s},{w},{n},{e}];
(
  way[waterway~"^(river|stream|canal)$"];
  way[natural=water]; rel[natural=water];
  way[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential)$"];
  way[landuse~"^(forest|residential|meadow|grass|orchard|farmland|recreation_ground)$"];
  rel[landuse~"^(forest|residential)$"];
  way[natural~"^(wood|scrub|grassland|wetland)$"]; rel[natural~"^(wood|wetland)$"];
  way[leisure~"^(park|garden|pitch)$"];
  node[place~"^(city|town|village|hamlet|suburb|neighbourhood)$"];
);
out geom;"""


def baixar_osm() -> dict:
    guardado = CACHE / f"osm-{NORTE}-{SUL}-{OESTE}-{LESTE}.json"
    if guardado.exists():
        return json.loads(guardado.read_text(encoding="utf-8"))
    q = CONSULTA.format(s=SUL, w=OESTE, n=NORTE, e=LESTE)
    corpo = urllib.parse.urlencode({"data": q}).encode()
    for url in ESPELHOS:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, corpo, UA), timeout=240) as r:
                dados = json.load(r)
            print(f"  OSM: {len(dados['elements'])} elementos de {url}")
            CACHE.mkdir(exist_ok=True)
            guardado.write_text(json.dumps(dados), encoding="utf-8")
            return dados
        except Exception as ex:  # o próximo espelho
            print(f"  {url}: {ex}")
    raise SystemExit("nenhum espelho do Overpass respondeu")


def _pts(geom):
    return [proj(p["lat"], p["lon"]) for p in geom if p]


def camadas_osm(dados: dict) -> dict:
    c = {k: [] for k in ("agua", "matas", "campos", "parques", "urbano", "rios", "riachos",
                         "vias_grandes", "vias", "ruas", "pontes", "lugares")}

    def poligono(destino, aneis, tol):
        for anel in aneis:
            anel = cortar_anel(dp(anel, tol))
            if len(anel) > 3:
                destino.append(plano(anel))

    for el in dados["elements"]:
        t = el.get("tags", {})
        if el["type"] == "node":
            x, y = proj(el["lat"], el["lon"])
            if _dentro((x, y), 0, 0, LARGURA, ALTURA) and t.get("name"):
                c["lugares"].append({"nome": t["name"], "tipo": t["place"], "x": round(x), "y": round(y)})
            continue
        if el["type"] == "relation":
            outer = [_pts(m.get("geometry") or []) for m in el["members"] if m["type"] == "way" and m["role"] in ("outer", "")]
            inner = [_pts(m.get("geometry") or []) for m in el["members"] if m["type"] == "way" and m["role"] == "inner"]
            aneis = juntar_aneis(outer) + juntar_aneis(inner)  # evenodd faz os buracos
            if t.get("natural") == "water":
                poligono(c["agua"], aneis, 12)
                if t.get("name"):
                    c.setdefault("nomes_agua", []).append(t["name"])
            elif t.get("landuse") == "forest" or t.get("natural") in ("wood", "wetland"):
                poligono(c["matas"], aneis, 12)
            elif t.get("landuse") == "residential":
                poligono(c["urbano"], aneis, 8)
            continue
        pts = _pts(el.get("geometry") or [])
        if len(pts) < 2:
            continue
        fechado = pts[0] == pts[-1]
        ww, hw = t.get("waterway"), t.get("highway")
        if ww in ("river", "canal") or ww == "stream":
            for troco in cortar_linha(dp(pts, 5)):
                item = {"p": plano(troco)}
                if t.get("name"):
                    item["nome"] = t["name"]
                c["rios" if ww != "stream" else "riachos"].append(item)
        elif t.get("natural") == "water" and fechado:
            poligono(c["agua"], [pts], 4)
        elif hw:
            for troco in cortar_linha(dp(pts, 3)):
                p = plano(troco)
                if t.get("bridge") == "yes":
                    item = {"p": p}
                    if t.get("name", "").lower().startswith("ponte"):
                        item["nome"] = t["name"]
                    c["pontes"].append(item)
                if hw in ("motorway", "trunk", "primary"):
                    c["vias_grandes"].append(p)
                elif hw in ("secondary", "tertiary"):
                    c["vias"].append(p)
                else:
                    c["ruas"].append(p)
        elif fechado and (t.get("natural") in ("wood", "wetland") or t.get("landuse") == "forest"):
            poligono(c["matas"], [pts], 10)
        elif fechado and (t.get("natural") in ("scrub", "grassland") or t.get("landuse") in ("meadow", "grass", "orchard", "farmland")):
            poligono(c["campos"], [pts], 4)
        elif fechado and (t.get("leisure") in ("park", "garden", "pitch") or t.get("landuse") == "recreation_ground"):
            poligono(c["parques"], [pts], 3)
        elif fechado and t.get("landuse") == "residential":
            poligono(c["urbano"], [pts], 6)
    return c


# ───────────────────────── marcos: praças, rodoviária, exposição… ─────────────────────────

CONSULTA_MARCOS = """[out:json][timeout:120][bbox:{s},{w},{n},{e}];
(
  nwr[leisure~"^(park|garden|playground|stadium|sports_centre|fairground)$"][name];
  nwr[place=square][name];
  nwr[amenity~"^(bus_station|place_of_worship|hospital|clinic|university|college|school|library|theatre|arts_centre|community_centre|townhall|marketplace|courthouse|fire_station|police)$"][name];
  nwr[tourism~"^(museum|attraction|viewpoint)$"][name];
  nwr[railway~"^(station|halt)$"][name];
  nwr[historic][name];
  nwr[landuse=cemetery][name];
);
out center tags;"""

# uma praça só entra se o nome disser que é praça, parque, largo… — o resto do
# que vem marcado como «park» no OpenStreetMap é ruído (áreas verdes sem nome
# próprio, e até um nome que não é de praça nenhuma).
PRACA_RE = re.compile(r"^(praça|pracinha|pequena praça|parque|largo|área de lazer|pomar d)", re.I)


def categoria(t: dict) -> str | None:
    nome = t.get("name", "")
    if re.search(r"exposi", nome, re.I) or t.get("leisure") == "fairground":
        return "festa"
    if re.search(r"^mercado", nome, re.I) or t.get("amenity") == "marketplace":
        return "mercado"
    a, lz = t.get("amenity"), t.get("leisure")
    if lz in ("park", "garden", "playground") or t.get("place") == "square":
        return "praca" if PRACA_RE.match(nome) else None
    if a == "bus_station" or t.get("railway"):
        return "transporte"
    if a == "place_of_worship":
        return "fe"
    if a in ("hospital", "clinic"):
        return "saude"
    if a in ("university", "college", "school"):
        return "ensino"
    if lz in ("stadium", "sports_centre") or a == "stadium":
        return "esporte"
    if a in ("library", "theatre", "arts_centre", "community_centre") or t.get("tourism") in ("museum", "attraction", "viewpoint") or t.get("historic"):
        return "cultura"
    if a in ("townhall", "courthouse", "fire_station", "police") or t.get("landuse") == "cemetery":
        return "publico"
    return None


def baixar_marcos() -> list[dict]:
    guardado = CACHE / f"marcos-{NORTE}-{SUL}-{OESTE}-{LESTE}.json"
    if guardado.exists():
        dados = json.loads(guardado.read_text(encoding="utf-8"))
    else:
        q = CONSULTA_MARCOS.format(s=SUL, w=OESTE, n=NORTE, e=LESTE)
        corpo = urllib.parse.urlencode({"data": q}).encode()
        for url in ESPELHOS:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, corpo, UA), timeout=180) as r:
                    dados = json.load(r)
                break
            except Exception as ex:
                print(f"  {url}: {ex}")
        else:
            raise SystemExit("nenhum espelho do Overpass respondeu (marcos)")
        CACHE.mkdir(exist_ok=True)
        guardado.write_text(json.dumps(dados), encoding="utf-8")
    marcos, vistos = [], set()
    for el in dados["elements"]:
        t = el.get("tags", {})
        cat = categoria(t)
        c = el.get("center") or el
        if not cat or "lat" not in c:
            continue
        x, y = proj(c["lat"], c["lon"])
        chave = (t["name"].strip().lower(), round(x / 50), round(y / 50))
        if chave in vistos or not _dentro((x, y), 0, 0, LARGURA, ALTURA):
            continue
        vistos.add(chave)
        marcos.append({"nome": t["name"].strip(), "cat": cat, "x": round(x), "y": round(y), "osm": f'{el["type"]}/{el["id"]}'})
    print(f"  marcos: {len(marcos)}")
    return sorted(marcos, key=lambda m: (m["cat"], m["nome"]))


# ───────────────────────── a maquete: prédios, praças, quadras, árvores ─────────────────────────

CONSULTA_MAQUETE = """[out:json][timeout:120][bbox:{s},{w},{n},{e}];
(
  way[building];
  node[natural=tree]; way[natural=tree_row];
  way[leisure~"^(park|garden)$"][name]; rel[leisure=park][name]; way[place=square];
  way[leisure~"^(pitch|playground|swimming_pool|track)$"];
  nw[amenity=fountain];
);
out geom;"""


def baixar_maquete() -> dict:
    """Só o que está no OpenStreetMap: se um prédio não foi mapeado, não aparece."""
    guardado = CACHE / f"maquete-{NORTE}-{SUL}-{OESTE}-{LESTE}.json"
    if guardado.exists():
        dados = json.loads(guardado.read_text(encoding="utf-8"))
    else:
        q = CONSULTA_MAQUETE.format(s=SUL, w=OESTE, n=NORTE, e=LESTE)
        corpo = urllib.parse.urlencode({"data": q}).encode()
        for url in ESPELHOS:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, corpo, UA), timeout=180) as r:
                    dados = json.load(r)
                break
            except Exception as ex:
                print(f"  {url}: {ex}")
        else:
            raise SystemExit("nenhum espelho do Overpass respondeu (maquete)")
        CACHE.mkdir(exist_ok=True)
        guardado.write_text(json.dumps(dados), encoding="utf-8")
    c = {k: [] for k in ("predios", "pracas", "quadras", "brinquedos", "piscinas", "arvores", "fileiras", "fontes")}
    for el in dados["elements"]:
        t = el.get("tags", {})
        if el["type"] == "node":
            x, y = proj(el["lat"], el["lon"])
            if _dentro((x, y)):
                c["arvores" if t.get("natural") == "tree" else "fontes"].append([round(x), round(y)])
            continue
        if el["type"] == "relation":
            outer = [_pts(m.get("geometry") or []) for m in el["members"] if m["type"] == "way" and m["role"] in ("outer", "")]
            aneis = juntar_aneis(outer)
        else:
            aneis = [_pts(el.get("geometry") or [])]
        for pts in aneis:
            if len(pts) < 2:
                continue
            fechado = pts[0] == pts[-1]
            if t.get("natural") == "tree_row":
                for troco in cortar_linha(dp(pts, 1)):
                    c["fileiras"].append(plano(troco))
                continue
            if not fechado:
                continue
            if t.get("amenity") == "fountain":
                x, y = pts[0]
                c["fontes"].append([round(x), round(y)])
                continue
            if t.get("building"):
                destino, tol = c["predios"], 0.8
            elif t.get("place") == "square" or PRACA_RE.match(t.get("name", "")):
                destino, tol = c["pracas"], 1.5
            elif t.get("leisure") in ("pitch", "track"):
                destino, tol = c["quadras"], 1
            elif t.get("leisure") == "playground":
                destino, tol = c["brinquedos"], 1
            elif t.get("leisure") == "swimming_pool":
                destino, tol = c["piscinas"], 1
            else:
                continue
            anel = cortar_anel(dp(pts, tol))
            if len(anel) > 3:
                destino.append(plano(anel))
    print("  maquete: " + ", ".join(f"{k} {len(v)}" for k, v in c.items()))
    return c


# ───────────────────────── relevo ─────────────────────────

Z = 14  # ~9 m por pixel nesta latitude


def _merc(lat, lon, z=Z):
    n = 256 * 2**z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def baixar_altitude() -> tuple[np.ndarray, float, float]:
    """Mosaico Terrarium que cobre a moldura (com folga). Devolve (alt, x0, y0) em pixels-mercator."""
    xa, ya = _merc(NORTE + 0.02, OESTE - 0.02)
    xb, yb = _merc(SUL - 0.02, LESTE + 0.02)
    tx0, ty0, tx1, ty1 = int(xa // 256), int(ya // 256), int(xb // 256), int(yb // 256)
    mosaico = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), dtype=np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            guardado = CACHE / f"terrarium-{Z}-{tx}-{ty}.png"
            if not guardado.exists():
                url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{tx}/{ty}.png"
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                    CACHE.mkdir(exist_ok=True)
                    guardado.write_bytes(r.read())
            rgb = np.asarray(Image.open(guardado).convert("RGB"), dtype=np.float32)
            alt = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
            mosaico[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = alt
    print(f"  altitude: {(tx1 - tx0 + 1) * (ty1 - ty0 + 1)} ladrilhos z{Z}")
    return mosaico, tx0 * 256, ty0 * 256


PASSO = 12  # metros por célula da grelha de relevo


def grelha(mosaico, mx0, my0) -> np.ndarray:
    """Reamostra para a grelha em metros (a mesma projeção das camadas)."""
    nx, ny = LARGURA // PASSO + 1, ALTURA // PASSO + 1
    xs = np.arange(nx) * PASSO
    ys = np.arange(ny) * PASSO
    lon = OESTE + xs / KX
    lat = NORTE - ys / KY
    n = 256 * 2**Z
    px = (lon + 180) / 360 * n - mx0
    lr = np.radians(lat)
    py = (1 - np.log(np.tan(lr) + 1 / np.cos(lr)) / np.pi) / 2 * n - my0
    PX, PY = np.meshgrid(px, py)
    x0, y0 = np.floor(PX).astype(int), np.floor(PY).astype(int)
    fx, fy = PX - x0, PY - y0
    m = mosaico
    v = (m[y0, x0] * (1 - fx) * (1 - fy) + m[y0, x0 + 1] * fx * (1 - fy)
         + m[y0 + 1, x0] * (1 - fx) * fy + m[y0 + 1, x0 + 1] * fx * fy)
    return v


def suavizar(a: np.ndarray, r: int = 2) -> np.ndarray:
    for _ in range(2):
        k = 2 * r + 1
        p = np.pad(a, r, mode="edge")
        c = np.cumsum(np.cumsum(p, 0), 1)
        c = np.pad(c, ((1, 0), (1, 0)))
        a = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)
    return a


# rampa de cor: várzea verde-clara → campo → cerrado alto, cor de terra
RAMPA = [(640, (214, 226, 196)), (700, (226, 230, 200)), (760, (236, 230, 204)),
         (840, (234, 220, 190)), (920, (226, 204, 168)), (1050, (212, 186, 150))]


def relevo_jpg(alt: np.ndarray, destino: Path) -> None:
    gy, gx = np.gradient(alt * 1.6, PASSO)  # exagero vertical: o relevo aqui é manso
    declive = np.arctan(np.hypot(gx, gy))
    aspecto = np.arctan2(-gy, gx)
    az, zen = math.radians(315), math.radians(45)
    luz = math.cos(zen) * np.cos(declive) + math.sin(zen) * np.sin(declive) * np.cos(az + math.pi / 2 - aspecto)
    sombra = np.clip(luz / math.cos(zen), 0.5, 1.12)
    sombra = 1 + (sombra - 1) * 0.7  # sombra de lápis, não de carvão
    zs = [z for z, _ in RAMPA]
    cor = np.stack([np.interp(alt, zs, [c[i] for _, c in RAMPA]) for i in range(3)], -1)
    img = np.clip(cor * sombra[..., None], 0, 255).astype(np.uint8)
    Image.fromarray(img, "RGB").save(destino, quality=82, optimize=True, progressive=True)


def curvas(alt: np.ndarray) -> list[dict]:
    lisa = suavizar(alt, 3)
    xs = np.arange(alt.shape[1]) * PASSO
    ys = np.arange(alt.shape[0]) * PASSO
    gen = contourpy.contour_generator(x=xs, y=ys, z=lisa, line_type="Separate")
    saida = []
    for nivel in range(int(lisa.min() // 10 + 1) * 10, int(lisa.max()) + 1, 10):
        for linha in gen.lines(nivel):
            pts = dp([tuple(p) for p in linha.tolist()], 8)
            if len(pts) > 3:
                saida.append({"z": nivel, "p": plano(pts)})
    return saida


# ───────────────────────── tudo ─────────────────────────


def main() -> int:
    SAIDA.mkdir(exist_ok=True)
    print("a baixar o OpenStreetMap…")
    c = camadas_osm(baixar_osm())
    c["marcos"] = baixar_marcos()
    c.update(baixar_maquete())
    print("a baixar a altitude…")
    alt = grelha(*baixar_altitude())
    relevo_jpg(alt, SAIDA / "relevo.jpg")
    c["curvas"] = curvas(alt)
    regiao = {
        "moldura": {"norte": NORTE, "sul": SUL, "oeste": OESTE, "leste": LESTE,
                    "largura": LARGURA, "altura": ALTURA, "lat0": LAT0, "kx": KX, "ky": KY},
        "preparado": dt.date.today().isoformat(),
        "fontes": [
            "geografia: © colaboradores do OpenStreetMap, ODbL — openstreetmap.org/copyright",
            "altitude: Terrain Tiles (Mapzen / AWS Open Data), derivado do SRTM e outros",
        ],
        "altitude": {"min": round(float(alt.min())), "max": round(float(alt.max()))},
        "camadas": c,
    }
    (SAIDA / "regiao.json").write_text(json.dumps(regiao, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tam = (SAIDA / "regiao.json").stat().st_size // 1024
    print(f"mapa/regiao.json ({tam} KB), mapa/relevo.jpg ({(SAIDA / 'relevo.jpg').stat().st_size // 1024} KB)")
    for k, v in c.items():
        print(f"  {k}: {len(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
