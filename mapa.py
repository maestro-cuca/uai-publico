"""O mapa da UAI — o chão em quadrinhos (mapa/regiao.json) e, por cima, os lugares, os convites e as jornadas.

Python puro. O chão prepara-se à parte (ferramentas/preparar_mapa.py) e fica
guardado no repositório; aqui sai o traço para a HQ (e os quadradinhos de 10 m do relevo), traçam-se as
jornadas pelas ruas e escreve-se o que fica por cima (SVG). As coordenadas estão em metros,
com a origem no canto noroeste da moldura: x para leste, y para sul.
"""
from __future__ import annotations

import heapq
import html
import json
import math
import urllib.parse
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
REGIAO = RAIZ / "mapa" / "regiao.json"
ONDE = RAIZ / "mapa" / "onde.json"
PRECISOES = ("exato", "aproximado")

e = html.escape


def carregar_regiao(caminho: Path = REGIAO) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def carregar_onde(caminho: Path = ONDE) -> dict:
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {k: v for k, v in dados.items() if not k.startswith("_")}


def projetar(moldura: dict, lat: float, lon: float) -> tuple[float, float]:
    return (lon - moldura["oeste"]) * moldura["kx"], (moldura["norte"] - lat) * moldura["ky"]


# ───────────────────────── traço ─────────────────────────


def _num(n: int, primeiro: bool) -> str:
    # um número negativo já traz o seu separador (o sinal)
    return str(n) if primeiro or n < 0 else " " + str(n)


def caminho(plano: list[int], fechar: bool = False) -> str:
    """[x, y, x, y, …] → «M x y l dx dy …» (relativo: mais curto)."""
    if len(plano) < 4:
        return ""
    x, y = plano[0], plano[1]
    partes = [f"M{x}{_num(y, False)}l"]
    primeiro = True
    for i in range(2, len(plano), 2):
        nx, ny = plano[i], plano[i + 1]
        dx, dy = nx - x, ny - y
        if dx == 0 and dy == 0:
            continue
        partes.append(_num(dx, primeiro) + _num(dy, False))
        primeiro = False
        x, y = nx, ny
    if primeiro:
        return ""
    return "".join(partes) + ("z" if fechar else "")


def _comprimento(plano: list[int]) -> float:
    return sum(math.hypot(plano[i + 2] - plano[i], plano[i + 3] - plano[i + 1]) for i in range(0, len(plano) - 2, 2))


def _meio(plano: list[int]) -> tuple[float, float]:
    alvo, feito = _comprimento(plano) / 2, 0.0
    for i in range(0, len(plano) - 2, 2):
        seg = math.hypot(plano[i + 2] - plano[i], plano[i + 3] - plano[i + 1])
        if feito + seg >= alvo and seg:
            t = (alvo - feito) / seg
            return plano[i] + t * (plano[i + 2] - plano[i]), plano[i + 1] + t * (plano[i + 3] - plano[i + 1])
        feito += seg
    return plano[0], plano[1]


# ───────────────────────── o desenho ─────────────────────────

# Os marcos do chão (do OpenStreetMap) — não são fichas: são convites a uma.
CATEGORIAS = {
    "praca": "praça", "transporte": "rodoviária e ônibus", "festa": "exposição e festa", "fe": "igreja",
    "saude": "saúde", "ensino": "escola e faculdade", "esporte": "esporte", "cultura": "cultura",
    "mercado": "mercado", "publico": "serviço público",
}
# pictogramas brancos desenhados numa caixa de ~10 px à volta de (0, 0)
ICONES = {
    "praca": '<circle cy="-1.6" r="3.2"/><rect x="-.8" y="0" width="1.6" height="4.6" rx=".5"/>',
    "transporte": '<rect x="-4" y="-4" width="8" height="7" rx="1.6"/><rect x="-3" y="3" width="1.6" height="1.6" rx=".5"/><rect x="1.4" y="3" width="1.6" height="1.6" rx=".5"/>',
    "festa": '<rect x="-3.4" y="-4.6" width="1.2" height="9.2" rx=".5"/><path d="M-2.2-4.6h6l-1.6 2.4 1.6 2.4h-6z"/>',
    "fe": '<rect x="-.9" y="-4.8" width="1.8" height="9.6" rx=".5"/><rect x="-3.4" y="-2.4" width="6.8" height="1.8" rx=".5"/>',
    "saude": '<rect x="-1.3" y="-4" width="2.6" height="8" rx=".6"/><rect x="-4" y="-1.3" width="8" height="2.6" rx=".6"/>',
    "ensino": '<path d="M0-4.2 5-1.6 0 1-5-1.6z"/><path d="M-3 0v2.4c1.6 1.4 4.4 1.4 6 0V0L0 1.6z"/>',
    "esporte": '<circle r="4.2" fill="none" stroke="#fff" stroke-width="1.4"/><path d="M-4 0h8M0-4c-2 2.6-2 5.4 0 8" fill="none" stroke="#fff" stroke-width="1.1"/>',
    "cultura": '<path d="M0-4.6 1.4-1.5 4.6-1.2 2.2 1 2.9 4.3 0 2.6-2.9 4.3-2.2 1-4.6-1.2-1.4-1.5z"/>',
    "mercado": '<path d="M-4.4-1.2h8.8l-1 5.4h-6.8z"/><path d="M-2.2-1.2 0-4.4 2.2-1.2" fill="none" stroke="#fff" stroke-width="1.2"/>',
    "publico": '<path d="M0-4.8 4.6-2.2h-9.2z"/><rect x="-3.6" y="-1.4" width="1.4" height="4.4"/><rect x="-.7" y="-1.4" width="1.4" height="4.4"/><rect x="2.2" y="-1.4" width="1.4" height="4.4"/><rect x="-4.4" y="3.2" width="8.8" height="1.4"/>',
}

ROTULO_LUGAR = {"city": "r-cidade", "town": "r-cidade", "village": "r-vila", "hamlet": "r-povoado",
                "suburb": "r-bairro", "neighbourhood": "r-bairro"}


def _ponto_mais_dentro(candidatos: list[tuple[float, float]], anel: list[int]) -> tuple[float, float] | None:
    """De entre os candidatos, o mais longe da margem — bom sítio para o nome de um lago."""
    if not candidatos or len(anel) < 6:
        return None
    margem = []
    for i in range(0, len(anel) - 2, 2):  # a margem, com um ponto a cada ~150 m
        x0, y0, x1, y1 = anel[i:i + 4]
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) // 150))
        margem += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n)]
    melhor, dist = None, -1.0
    for cx, cy in candidatos:
        d = min((cx - x) ** 2 + (cy - y) ** 2 for x, y in margem)
        if d > dist:
            melhor, dist = (cx, cy), d
    return melhor


def _linhas(c: dict, k: str) -> list[list[int]]:
    return [it["p"] if isinstance(it, dict) else it for it in c.get(k, [])]


# ───────────────────────── o chão em pixel ─────────────────────────
# Menos realista de propósito: a cidade em quadradinhos de 10 m, cada um de uma
# classe só. O navegador pinta cada classe com a cor do tema (claro, escuro,
# contraste) — por isso o chão vai como classes, não como cores.

CEL = 10  # metros por quadradinho
CLASSES = ("terra", "cidade", "campo", "parque", "mata", "praca", "agua", "rua", "via", "grande",
           "ponte", "predio", "rio", "riacho")
C = {k: i for i, k in enumerate(CLASSES)}
QUARTEIRAO = 4  # a mancha da cidade conta-se em blocos de 4×4 quadradinhos (40 m)


def chao(regiao: dict, cel: int = CEL) -> dict:
    """O chão rasterizado: {colunas, linhas, cel, dados} — um byte (a classe) por quadradinho."""
    m, c = regiao["moldura"], regiao["camadas"]
    W, H = math.ceil(m["largura"] / cel), math.ceil(m["altura"] / cel)
    g = bytearray(W * H)

    def poly(listas, v):
        """Preenchimento por linhas de varrimento, par-ímpar (os buracos ficam buracos)."""
        cortes: dict[int, list[float]] = {}
        for p in listas:
            n = len(p) // 2
            if n < 3:
                continue
            for i in range(n):
                j = (i + 1) % n
                x0, y0, x1, y1 = p[2 * i] / cel, p[2 * i + 1] / cel, p[2 * j] / cel, p[2 * j + 1] / cel
                if y0 == y1:
                    continue
                if y0 > y1:
                    x0, y0, x1, y1 = x1, y1, x0, y0
                k = (x1 - x0) / (y1 - y0)
                for lin in range(max(0, math.ceil(y0 - .5)), min(H - 1, math.ceil(y1 - .5) - 1) + 1):
                    cortes.setdefault(lin, []).append(x0 + (lin + .5 - y0) * k)
        b = bytes([v])
        for lin, xs in cortes.items():
            xs.sort()
            base = lin * W
            for a, z in zip(xs[::2], xs[1::2]):
                ia, iz = max(0, math.ceil(a - .5)), min(W - 1, math.ceil(z - .5) - 1)
                if iz >= ia:
                    g[base + ia: base + iz + 1] = b * (iz - ia + 1)

    def linha(p, v, grosso=1):
        for i in range(0, len(p) - 2, 2):
            x0, y0, x1, y1 = p[i] / cel, p[i + 1] / cel, p[i + 2] / cel, p[i + 3] / cel
            n = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
            for s in range(n + 1):
                x, y = int(x0 + (x1 - x0) * s / n), int(y0 + (y1 - y0) * s / n)
                for dx in range(grosso):
                    for dy in range(grosso):
                        xx, yy = x + dx - grosso // 2, y + dy - grosso // 2
                        if 0 <= xx < W and 0 <= yy < H:
                            g[yy * W + xx] = v

    poly(_linhas(c, "urbano"), C["cidade"])
    poly(_linhas(c, "campos"), C["campo"])
    poly(_linhas(c, "parques"), C["parque"])
    poly(_linhas(c, "matas"), C["mata"])
    poly(_linhas(c, "pracas"), C["praca"])
    poly(_linhas(c, "agua"), C["agua"])
    for p in _linhas(c, "riachos"):
        linha(p, C["riacho"])
    for p in _linhas(c, "rios"):
        linha(p, C["rio"], 2)
    poly(_linhas(c, "predios"), C["predio"])
    for k, v, gr in (("ruas", "rua", 1), ("vias", "via", 1), ("vias_grandes", "grande", 2), ("pontes", "ponte", 2)):
        for p in _linhas(c, k):
            linha(p, C[v], gr)

    # a mancha da cidade: onde há muita rua à volta, a terra vira cidade — em blocos, como num jogo
    Q = QUARTEIRAO
    bw, bh = math.ceil(W / Q), math.ceil(H / Q)
    conta = [0] * (bw * bh)
    ruas = {C["rua"], C["via"], C["grande"]}
    for y in range(H):
        base, by = y * W, (y // Q) * bw
        for x in range(W):
            if g[base + x] in ruas:
                conta[by + x // Q] += 1
    for by in range(bh):
        for bx in range(bw):
            soma = sum(conta[yy * bw + xx] for yy in range(max(0, by - 1), min(bh, by + 2))
                       for xx in range(max(0, bx - 1), min(bw, bx + 2)))
            if soma < 22:
                continue
            for y in range(by * Q, min(H, by * Q + Q)):
                for x in range(bx * Q, min(W, bx * Q + Q)):
                    if g[y * W + x] == C["terra"]:
                        g[y * W + x] = C["cidade"]
    return {"colunas": W, "linhas": H, "cel": cel, "dados": bytes(g)}


# ───────────────────────── o chão em quadrinhos ─────────────────────────
# O navegador desenha o chão como numa HQ: cada coisa com contorno de tinta e cor
# chapada. Para isso vai o traço (em metros, inteiros) e não o quadradinho; a
# mancha da cidade, que no pixel nascia das ruas, vira uma forma de bordas
# arredondadas, tirada dos mesmos quadradinhos.

MANCHA = 4  # a mancha da cidade conta-se em blocos de 4×4 quadradinhos (40 m)


def _aneis_da_grade(cheio: list[bool], bw: int, bh: int, lado: float) -> list[list[float]]:
    """As bordas de uma grade de blocos cheios, como anéis fechados (buracos incluídos)."""
    def ok(x, y):
        return 0 <= x < bw and 0 <= y < bh and cheio[y * bw + x]
    prox: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for y in range(bh):
        for x in range(bw):
            if not ok(x, y):
                continue
            # aresta com o cheio à direita de quem anda (sentido horário no ecrã)
            if not ok(x, y - 1):
                prox.setdefault((x, y), []).append((x + 1, y))
            if not ok(x + 1, y):
                prox.setdefault((x + 1, y), []).append((x + 1, y + 1))
            if not ok(x, y + 1):
                prox.setdefault((x + 1, y + 1), []).append((x, y + 1))
            if not ok(x - 1, y):
                prox.setdefault((x, y + 1), []).append((x, y))
    aneis = []
    while prox:
        ini = next(iter(prox))
        anel, a = [ini], ini
        while True:
            saidas = prox.get(a)
            if not saidas:
                break
            b = saidas.pop()
            if not saidas:
                del prox[a]
            if b == ini:
                break
            anel.append(b)
            a = b
        # tira os pontos do meio das retas
        lim = []
        n = len(anel)
        for i in range(n):
            (x0, y0), (x1, y1), (x2, y2) = anel[i - 1], anel[i], anel[(i + 1) % n]
            if (x1 - x0) * (y2 - y1) != (y1 - y0) * (x2 - x1):
                lim.append((x1 * lado, y1 * lado))
        if len(lim) >= 4:
            aneis.append(lim)
    return aneis


def _arredondar(anel: list[tuple[float, float]], vezes: int = 3) -> list[tuple[float, float]]:
    """Chaikin: corta os cantos até a borda ficar de lápis, não de régua."""
    for _ in range(vezes):
        novo = []
        n = len(anel)
        for i in range(n):
            (x0, y0), (x1, y1) = anel[i], anel[(i + 1) % n]
            novo += [(.75 * x0 + .25 * x1, .75 * y0 + .25 * y1), (.25 * x0 + .75 * x1, .25 * y0 + .75 * y1)]
        anel = novo
    return anel


def _area(anel) -> float:
    return abs(sum(anel[i - 1][0] * anel[i][1] - anel[i][0] * anel[i - 1][1] for i in range(len(anel)))) / 2


def tracos(regiao: dict, chao_: dict) -> dict:
    """O chão em traço, para a HQ: as camadas que se desenham, em [x, y, …] inteiros (metros)."""
    c = regiao["camadas"]
    W, H, cel, dados = chao_["colunas"], chao_["linhas"], chao_["cel"], chao_["dados"]
    cidade = {C[k] for k in ("cidade", "rua", "via", "grande", "predio", "praca")}
    Q = MANCHA
    bw, bh = math.ceil(W / Q), math.ceil(H / Q)
    conta = [0] * (bw * bh)
    for y in range(H):
        base, by = y * W, (y // Q) * bw
        for x in range(W):
            if dados[base + x] in cidade:
                conta[by + x // Q] += 1
    cheio = [n >= 6 for n in conta]
    # fecha os buraquinhos e apara as pontas soltas (um passo de dilatar e outro de encolher)
    def vizinhos(g, x, y):
        return [g[yy * bw + xx] for yy in range(max(0, y - 1), min(bh, y + 2)) for xx in range(max(0, x - 1), min(bw, x + 2))]
    cheio = [any(vizinhos(cheio, i % bw, i // bw)) for i in range(bw * bh)]
    cheio = [all(vizinhos(cheio, i % bw, i // bw)) for i in range(bw * bh)]
    manchas = []
    for anel in _aneis_da_grade(cheio, bw, bh, Q * cel):
        if _area(anel) < (Q * cel) ** 2 * 6:
            continue
        plano = []
        for x, y in _arredondar(anel):
            plano += [round(x), round(y)]
        manchas.append(plano)

    def lista(k):
        return [p for p in _linhas(c, k) if len(p) >= 4]
    return {
        "cidade": manchas,
        "campos": lista("campos"), "parques": lista("parques"), "matas": lista("matas"),
        "agua": lista("agua"), "pracas": lista("pracas"), "quadras": lista("quadras"),
        "piscinas": lista("piscinas"), "predios": lista("predios"),
        "riachos": lista("riachos"), "rios": lista("rios"),
        "ruas": lista("ruas"), "vias": lista("vias"), "grandes": lista("vias_grandes"), "pontes": lista("pontes"),
    }


# ───────────────────────── a rede: por onde se anda ─────────────────────────

GRUDE = 25  # metros: uma ponta de rua solta liga-se à rua mais perto (o mapa simplificado perde cruzamentos)


def _cruzam(p, q, r, s_):
    """Onde o segmento p–q corta o segmento r–s (t em p–q, u em r–s), ou None."""
    dx1, dy1, dx2, dy2 = q[0] - p[0], q[1] - p[1], s_[0] - r[0], s_[1] - r[1]
    den = dx1 * dy2 - dy1 * dx2
    if not den:
        return None
    t = ((r[0] - p[0]) * dy2 - (r[1] - p[1]) * dx2) / den
    u = ((r[0] - p[0]) * dy1 - (r[1] - p[1]) * dx1) / den
    return (t, u) if 0 <= t <= 1 and 0 <= u <= 1 else None


def rede(regiao: dict) -> dict[tuple[int, int], dict[tuple[int, int], float]]:
    """As ruas como grafo, só a maior parte ligada (o resto são pedaços soltos do mapa).

    O mapa guardado é simplificado: perde os nós dos cruzamentos. Por isso as ruas
    cortam-se onde se cruzam, e uma ponta solta gruda na rua mais perto (até GRUDE m)."""
    c = regiao["camadas"]
    segs, pontas = [], []
    for k in ("ruas", "vias", "vias_grandes", "pontes"):
        for p in _linhas(c, k):
            pts = [(p[i], p[i + 1]) for i in range(0, len(p) - 1, 2)]
            segs += [(a, b) for a, b in zip(pts, pts[1:]) if a != b]
            if len(pts) > 1:
                pontas += [pts[0], pts[-1]]
    L = 60  # a grade de procura, em metros
    grade: dict[tuple[int, int], list[int]] = {}
    for i, (a, b) in enumerate(segs):
        for gx in range(min(a[0], b[0]) // L, max(a[0], b[0]) // L + 1):
            for gy in range(min(a[1], b[1]) // L, max(a[1], b[1]) // L + 1):
                grade.setdefault((gx, gy), []).append(i)
    cortes: dict[int, set] = {i: set() for i in range(len(segs))}
    for lista in grade.values():
        for n, i in enumerate(lista):
            for j in lista[n + 1:]:
                tu = _cruzam(*segs[i], *segs[j])
                if tu:
                    (ax, ay), (bx, by) = segs[i]
                    ponto = (round(ax + (bx - ax) * tu[0]), round(ay + (by - ay) * tu[0]))
                    cortes[i].add(ponto)
                    cortes[j].add(ponto)
    # pontas soltas: o ponto mais perto numa rua vizinha
    ligacoes = []
    contagem: dict[tuple, int] = {}
    for a, b in segs:
        contagem[a] = contagem.get(a, 0) + 1
        contagem[b] = contagem.get(b, 0) + 1
    for v in pontas:
        if contagem.get(v, 0) > 1:
            continue
        melhor = None
        gx, gy = v[0] // L, v[1] // L
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in grade.get((gx + dx, gy + dy), ()):
                    (ax, ay), (bx, by) = segs[i]
                    if v in segs[i]:
                        continue
                    lx, ly = bx - ax, by - ay
                    t = max(0.0, min(1.0, ((v[0] - ax) * lx + (v[1] - ay) * ly) / ((lx * lx + ly * ly) or 1)))
                    ponto = (round(ax + lx * t), round(ay + ly * t))
                    d = math.dist(v, ponto)
                    if d <= GRUDE and (melhor is None or d < melhor[0]):
                        melhor = (d, i, ponto)
        if melhor:
            cortes[melhor[1]].add(melhor[2])
            ligacoes.append((v, melhor[2]))
    adj: dict[tuple[int, int], dict[tuple[int, int], float]] = {}

    def ligar(a, b):
        if a != b:
            d = math.dist(a, b)
            adj.setdefault(a, {})[b] = d
            adj.setdefault(b, {})[a] = d
    for i, (a, b) in enumerate(segs):
        meio = sorted(cortes[i], key=lambda p: math.dist(a, p))
        pts = [a, *meio, b]
        for p, q in zip(pts, pts[1:]):
            ligar(p, q)
    for v, p in ligacoes:
        ligar(v, p)
    # fica a maior parte ligada
    vistos: set = set()
    maior: set = set()
    for v in adj:
        if v in vistos:
            continue
        parte, pilha = {v}, [v]
        while pilha:
            for u in adj[pilha.pop()]:
                if u not in parte:
                    parte.add(u)
                    pilha.append(u)
        vistos |= parte
        if len(parte) > len(maior):
            maior = parte
    return {v: {u: d for u, d in viz.items() if u in maior} for v, viz in adj.items() if v in maior}


def no_mais_perto(adj: dict, x: float, y: float) -> tuple[tuple[int, int], float]:
    v = min(adj, key=lambda u: (u[0] - x) ** 2 + (u[1] - y) ** 2)
    return v, math.dist(v, (x, y))


def rota(adj: dict, a: tuple[int, int], b: tuple[int, int]) -> tuple[float, list[tuple[int, int]]]:
    """O caminho mais curto pelas ruas (Dijkstra). Sem caminho: (inf, [])."""
    dist, ant, fila = {a: 0.0}, {}, [(0.0, a)]
    while fila:
        d, v = heapq.heappop(fila)
        if v == b:
            break
        if d > dist[v]:
            continue
        for u, w in adj[v].items():
            nd = d + w
            if nd < dist.get(u, math.inf):
                dist[u], ant[u] = nd, v
                heapq.heappush(fila, (nd, u))
    if b not in dist:
        return math.inf, []
    cam = [b]
    while cam[-1] != a:
        cam.append(ant[cam[-1]])
    return dist[b], cam[::-1]


# ───────────────────────── jornadas ─────────────────────────
# Uma jornada é uma caminhada por lugares que existem (convites do mapa livre ou
# fichas da UAI), com procedência. O traço segue as ruas; na rua, vale o que os olhos virem.

JORNADAS = RAIZ / "mapa" / "jornadas.json"
LONGE_DA_RUA = 250  # metros: uma parada mais longe do que isto de qualquer rua não se liga
PASSO = 75  # metros por minuto, a pé, sem pressa


def carregar_jornadas(caminho_: Path = JORNADAS) -> dict:
    if not caminho_.exists():
        return {}
    dados = json.loads(caminho_.read_text(encoding="utf-8"))
    return {k: v for k, v in dados.items() if not k.startswith("_")}


def tracar_jornadas(jornadas: dict, regiao: dict, fichas_no_mapa: dict, adj: dict | None = None) -> tuple[list[dict], list[str]]:
    """`fichas_no_mapa`: {id: {nome, x, y}}. Devolve (jornadas traçadas, erros)."""
    marcos = {mc["nome"]: mc for mc in regiao["camadas"].get("marcos", [])}
    saida, erros = [], []
    if jornadas and adj is None:
        adj = rede(regiao)
    for id_, j in jornadas.items():
        onde = f"jornadas.json «{id_}»"
        if not j.get("nome"):
            erros.append(f"{onde}: sem nome")
        if not (j.get("fonte") or {}).get("descricao"):
            erros.append(f"{onde}: sem fonte — uma jornada também diz de onde veio")
        paradas = []
        for n, p in enumerate(j.get("paradas", []), 1):
            if "marco" in p:
                mc = marcos.get(p["marco"])
                if not mc:
                    erros.append(f"{onde}: a parada {n} («{p['marco']}») não está entre os convites do mapa")
                    continue
                paradas.append({"nome": mc["nome"], "x": mc["x"], "y": mc["y"], "tipo": CATEGORIAS[mc["cat"]], "nota": p.get("nota", "")})
            elif "ficha" in p:
                f = fichas_no_mapa.get(p["ficha"])
                if not f:
                    erros.append(f"{onde}: a parada {n} («{p['ficha']}») não é uma ficha com lugar no mapa")
                    continue
                paradas.append({"nome": f["nome"], "x": f["x"], "y": f["y"], "tipo": "lugar da UAI", "ficha": p["ficha"], "nota": p.get("nota", "")})
            else:
                erros.append(f"{onde}: a parada {n} não diz se é «marco» ou «ficha»")
        if len(j.get("paradas", [])) < 2:
            erros.append(f"{onde}: uma jornada tem pelo menos duas paradas")
        if erros and any(e_.startswith(onde) for e_ in erros):
            continue
        nos = []
        for p in paradas:
            v, d = no_mais_perto(adj, p["x"], p["y"])
            if d > LONGE_DA_RUA:
                erros.append(f"{onde}: «{p['nome']}» fica a {d:.0f} m da rua mais perto do mapa")
            nos.append(v)
        pontos, total = [(paradas[0]["x"], paradas[0]["y"])], 0.0
        for i, (a, b) in enumerate(zip(nos, nos[1:])):
            d, cam = rota(adj, a, b)
            if not cam:
                erros.append(f"{onde}: não há caminho pelas ruas entre «{paradas[i]['nome']}» e «{paradas[i + 1]['nome']}»")
                break
            total += d
            pontos += cam + [(paradas[i + 1]["x"], paradas[i + 1]["y"])]
        else:
            saida.append({"id": id_, "nome": j.get("nome", id_), "convite": j.get("convite", ""), "fonte": j["fonte"],
                          "paradas": paradas, "pontos": _sem_repetidos(pontos), "metros": round(total),
                          "minutos": max(1, round(total / PASSO))})
    return saida, erros


def _sem_repetidos(pontos):
    saida = []
    for p in pontos:
        p = (round(p[0]), round(p[1]))
        if not saida or saida[-1] != p:
            saida.append(p)
    return saida


def distancia(m: float) -> str:
    return f"{round(m / 10) * 10} m" if m < 1000 else f"{m / 1000:.1f} km".replace(".", ",")


def a_pe(minutos: int) -> str:
    if minutos < 60:
        return f"uns {minutos} min a pé"
    h, mi = divmod(minutos, 60)
    horas = "uma hora" if h == 1 else f"{h} horas"
    return f"{horas}{f' e {mi} min' if mi >= 5 else ''} a pé"


# ───────────────────────── o que fica por cima do chão ─────────────────────────
# Só o que se toca e se lê: jornadas, nomes, convites e os lugares da UAI. Tudo
# guarda a sua posição em metros (data-x, data-y); o mapa.js põe-no no ecrã.

GENTE_MAX = 12


def gente(n: int) -> str:
    """Pessoinhas de pixel: cada uma é uma história contada naquele lugar."""
    if n <= 0:
        return ""
    figuras = []
    for i in range(min(n, GENTE_MAX)):
        ang = math.radians(118 + i * 31)
        anel = 26 + (i // 6) * 12
        x, y = round(math.cos(ang) * anel), round(math.sin(ang) * anel + 4)
        figuras.append(f'<g class="pessoa p{i % 5}" transform="translate({x} {y})">'
                       '<rect class="p-sombra" x="-2" y="5" width="6" height="2"/>'
                       '<rect class="p-corpo" x="-3" y="-1" width="6" height="7"/>'
                       '<rect class="p-cabeca" x="-2" y="-6" width="4" height="4"/></g>')
    return f'<g class="gente" aria-hidden="true">{"".join(figuras)}</g>'


def svg(regiao: dict, lugares: list[dict], jornadas: list[dict] | tuple = (), chao_: dict | None = None) -> str:
    """`lugares`: [{id, nome, estado, x, y, raio, precisao, rotulo, historias}] já projetados."""
    m, c = regiao["moldura"], regiao["camadas"]
    W, H = m["largura"], m["altura"]
    rotulos = []

    # os rios: o nome no meio do troço mais comprido
    melhores: dict[str, tuple[float, list[int], str]] = {}
    for classe, itens in (("r-rio", c["rios"]), ("r-corrego", c["riachos"])):
        for it in itens:
            nome = it.get("nome")
            comp = _comprimento(it["p"]) if nome else 0
            if nome and comp > 1500 and comp > melhores.get(nome, (0,))[0]:
                melhores[nome] = (comp, it["p"], classe)
    for nome, (comp, plano, classe) in sorted(melhores.items()):
        x, y = _meio(plano)
        rotulos.append((classe, nome, x, y))
    if c.get("nomes_agua") and c["agua"]:
        maior = max(c["agua"], key=len)
        leito = [(it["p"][i], it["p"][i + 1]) for it in c["rios"] for i in range(0, len(it["p"]), 2)
                 if 2500 < it["p"][i] < W - 2500 and 2500 < it["p"][i + 1] < H - 2500]
        p = _ponto_mais_dentro(leito, maior)
        if p:
            rotulos.append(("r-agua", c["nomes_agua"][0], p[0], p[1]))
    for lg in c["lugares"]:
        classe = ROTULO_LUGAR.get(lg["tipo"], "r-povoado")
        if classe != "r-cidade":  # a cidade inteira é o mapa: o nome dela vai no título
            rotulos.append((classe, lg["nome"], lg["x"], lg["y"]))
    vistos = set()
    for pt in c["pontes"]:
        nome = pt.get("nome")
        if nome and nome not in vistos:
            vistos.add(nome)
            x, y = _meio(pt["p"])
            rotulos.append(("r-ponte", nome, x, y))
    textos = "".join(f'<text class="{k}" data-x="{x:.0f}" data-y="{y:.0f}" text-anchor="middle">{e(n)}</text>'
                     for k, n, x, y in rotulos)

    trilhas, paradas = [], []
    for j in jornadas:
        pts = " ".join(f"{x},{y}" for x, y in j["pontos"])
        resumo = f'{len(j["paradas"])} paradas · {distancia(j["metros"])} · {a_pe(j["minutos"])}'
        trilhas.append(f'<g class="jornada" data-id="{e(j["id"])}" data-nome="{e(j["nome"])}" data-resumo="{e(resumo)}" data-pontos="{pts}">'
                       f'<path class="j-borda"/><path class="j-traco"/></g>')
        for n, p in enumerate(j["paradas"], 1):
            paradas.append(f'<g class="parada" data-jornada="{e(j["id"])}" data-n="{n}" data-nome="{e(p["nome"])}" '
                           f'data-tipo="{e(p["tipo"])}" data-x="{p["x"]:.0f}" data-y="{p["y"]:.0f}">'
                           f'<rect class="sombra" x="-7" y="-7" width="16" height="16"/><rect class="caixa" x="-9" y="-9" width="16" height="16"/>'
                           f'<text x="-1" y="3.5" text-anchor="middle">{n}</text></g>')

    marcos = []
    for mc in c.get("marcos", []):
        nome, cat = mc["nome"], mc["cat"]
        alvo = "deixar.html?" + urllib.parse.urlencode({"nome": nome})
        rot = f"{nome} — {CATEGORIAS[cat]} · contar uma história deste lugar"
        marcos.append(
            f'<a class="marco c-{cat}" href="{e(alvo)}" data-cat="{cat}" data-nome="{e(nome)}" aria-label="{e(rot)}"><title>{e(rot)}</title>'
            f'<g class="icone" data-x="{mc["x"]}" data-y="{mc["y"]}" data-largura="{len(nome) * 6.6 + 16:.0f}">'
            f'<rect class="sombra" x="-7" y="-7" width="18" height="18"/><rect class="fundo" x="-9" y="-9" width="18" height="18"/>'
            f'<use href="#ic-{cat}"/><text class="nome-marco" x="14" y="4">{e(nome)}</text></g></a>')

    pinos = []
    for lg in lugares:
        estado = (lg.get("estado") or "nenhum").replace(" ", "-")
        area = '<ellipse class="area"/>' if lg["precisao"] == "aproximado" else ""
        marca = '<text class="marca" y="4" text-anchor="middle">?</text>' if lg["precisao"] == "aproximado" else '<rect class="brilho" x="-4" y="-4" width="3" height="3"/>'
        largura = len(lg["nome"]) * 7.4 + 20
        pinos.append(
            f'<a class="lugar e-{e(estado)}" href="{e(lg["id"])}.html" data-id="{e(lg["id"])}" data-nome="{e(lg["nome"])}" data-estado="{e(estado)}" '
            f'data-raio="{lg.get("raio") or 0:.0f}" aria-label="{e(lg["rotulo"])}">'
            f'<title>{e(lg["rotulo"])}</title>{area}'
            f'<g class="pino" data-x="{lg["x"]:.0f}" data-y="{lg["y"]:.0f}">'
            f'<rect class="halo" x="-15" y="-15" width="30" height="30"/>'
            f'<rect class="sombra" x="-6" y="-6" width="16" height="16"/><rect class="miolo" x="-8" y="-8" width="16" height="16"/>{marca}'
            f'<g class="etiqueta" data-largura="{largura:.0f}"><rect class="sombra" x="2" y="-10" width="{largura:.0f}" height="22"/>'
            f'<rect class="placa" x="0" y="-12" width="{largura:.0f}" height="22"/><text class="nome" x="10" y="4">{e(lg["nome"])}</text></g>'
            f'{gente(lg.get("historias", 0))}</g></a>')

    cidade = next((lg for lg in c["lugares"] if lg["tipo"] in ("city", "town")), {"x": W / 2, "y": H / 2})
    geo = "".join(f' data-{k}="{m[k]}"' for k in ("oeste", "norte", "kx", "ky") if k in m)
    grade = f' data-cel="{chao_["cel"]}" data-colunas="{chao_["colunas"]}" data-linhas="{chao_["linhas"]}"' if chao_ else ""
    icones = "".join(f'<g id="ic-{k}" fill="#fff">{v}</g>' for k, v in ICONES.items())
    return f"""<svg xmlns="http://www.w3.org/2000/svg" id="mapa" data-largura="{W}" data-altura="{H}" data-centro-x="{cidade["x"]:.0f}" data-centro-y="{cidade["y"]:.0f}"{geo}{grade} aria-labelledby="mapa-t" tabindex="0">
<title id="mapa-t">Mapa de Passos — bairros, córregos, matas, ruas e os lugares da UAI</title>
<defs>{icones}</defs>
<g class="m-jornadas" aria-hidden="true">{"".join(trilhas)}</g>
<g class="m-rotulos" aria-hidden="true">{textos}</g>
<g class="m-marcos">{"".join(marcos)}</g>
<g class="m-paradas" aria-hidden="true">{"".join(paradas)}</g>
<g class="m-lugares">{"".join(pinos)}</g>
</svg>
"""
