#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
folha.py — a UAI numa folha só (23/11/2026).

PORQUE EXISTE: o sítio da UAI **não abre a partir de um ficheiro**. O navegador proíbe as
leituras locais (CORS): sem servidor, o mapa não carrega e metade das páginas fica vazia. E a
casa não tem onde hospedar (os repositórios são privados, e o Pages em privado é pago).

A saída é uma folha só: **um ficheiro HTML com tudo dentro** — o mapa, o chão, a lista de
lugares, as fichas e as leis. Manda-se por mensagem, abre em qualquer telemóvel, sem internet,
sem conta, sem servidor.

USO:
    python3 folha.py uai.html
"""
from __future__ import annotations

import base64
import html.parser
import re
import shutil
import sys
import tempfile
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
import uai  # noqa: E402


class _Recorte(html.parser.HTMLParser):
    """Recorta um elemento pelo id/classe, com os filhos todos. Sem regex — regex não conta degraus."""

    def __init__(self, classe: str = "painel"):
        super().__init__(convert_charrefs=False)
        self.classe = classe
        self.dentro = False
        self.degrau = 0
        self.pedacos: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if not self.dentro and self.classe in (d.get("class") or "").split():
            self.dentro, self.degrau = True, 1
            self.pedacos.append(self.get_starttag_text() or "")
            return
        if self.dentro:
            if tag not in ("meta", "link", "br", "img", "input", "hr"):
                self.degrau += 1
            self.pedacos.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        if self.dentro:
            self.pedacos.append(f"</{tag}>")
            self.degrau -= 1
            if self.degrau <= 0:
                self.dentro = False

    def handle_data(self, data):
        if self.dentro:
            self.pedacos.append(data)


def recortar(caminho: Path, classe: str = "painel") -> str:
    r = _Recorte(classe)
    r.feed(caminho.read_text(encoding="utf-8"))
    return "".join(r.pedacos)


def bytes_crus(caminho: Path) -> bytes:
    """O deflate do construir (zlib) — o mesmo que o DecompressionStream lê no browser."""
    return zlib.decompress(caminho.read_bytes())


def juntar(site: Path, destino: Path) -> tuple[Path, int]:
    """Junta o sítio inteiro num ficheiro só. Devolve (caminho, tamanho em bytes)."""
    index = (site / "index.html").read_text(encoding="utf-8")

    # 1 · o que o mapa precisa vai dentro do ficheiro, em vez de ser pedido ao servidor
    dentro = {
        "mapa.svg": (site / "mapa.svg").read_text(encoding="utf-8"),
        "chao.bin": base64.b64encode(bytes_crus(site / "chao.bin")).decode(),
        "hq.bin": base64.b64encode(bytes_crus(site / "hq.bin")).decode(),
        "relevo.jpg": "data:image/jpeg;base64," + base64.b64encode((site / "relevo.jpg").read_bytes()).decode(),
    }

    # 2 · as fichas entram como secções escondidas (a mesma folha, sem páginas soltas)
    seccoes, ids = [], []
    for f in sorted(site.glob("*.html")):
        if f.name in ("index.html", "acervo.html", "deixar.html", "curador.html", "cartao.html"):
            continue
        id_ = f.stem
        corpo = recortar(f)
        if not corpo:
            continue
        ids.append(id_)
        seccoes.append(
            f'<section class="folha-ficha" id="f-{uai.e(id_)}" hidden>\n'
            f'<p class="ref"><a href="#inicio" class="voltar">← voltar ao mapa</a></p>\n{corpo}\n</section>')

    # 3 · o CSS e os scripts entram no corpo do ficheiro.
    #     Os scripts vão para o FIM do <body>: na folha não há «defer» que valha (num script inline é
    #     ignorado), e no <head> correriam antes de existir a cena — foi o que deixou o mapa preto.
    css = (site / "uai.css").read_text(encoding="utf-8")
    index = re.sub(r'<link rel="stylesheet" href="fontes/fontes\.css[^"]*">', "", index)
    index = re.sub(r'<link rel="stylesheet" href="uai\.css[^"]*">', "<style>\n" + css + "\n</style>", index)
    index = re.sub(r'<link rel="preload"[^>]*fontes/[^>]*>', "", index)

    pedacos: list[str] = []

    def inlina(m: re.Match) -> str:
        ficheiro = site / m.group(1).split("?")[0]
        if not ficheiro.exists():
            return ""
        extras = " " + m.group(2).replace("defer", "").strip() if m.group(2).strip().replace("defer", "").strip() else ""
        pedacos.append(f"<script{extras}>\n{ficheiro.read_text(encoding='utf-8')}\n</script>")
        return ""

    index = re.sub(r'<script src="([^"]+)"([^>]*)></script>', inlina, index)

    # 4 · o aviso ao mapa de que o chão já está dentro, e os scripts, no fim do corpo
    aviso = f'<script>window.UAI_INLINE = {uai.json.dumps(dentro, ensure_ascii=False)};</script>'
    scripts = "\n".join([aviso] + pedacos)

    # 5 · os links para as fichas passam a ser dentro da folha
    for id_ in ids:
        index = index.replace(f'href="{id_}.html"', f'href="#f-{uai.e(id_)}"')
    index = index.replace('href="acervo.html"', 'href="#acervo-inline"')
    index = index.replace('href="deixar.html"', 'href="#deixar-inline"')

    # 6 · a navegação da folha (mostrar/esconder secções) e o aviso de que é uma folha
    seccoes_html = "\n".join(seccoes)
    router = """
<script>
// a folha: uma página só, secções que se escondem e mostram (sem servidor, sem internet)
document.addEventListener("click", (e) => {
  const a = e.target.closest('a[href^="#f-"]');
  if (!a) return;
  e.preventDefault();
  document.querySelectorAll(".folha-ficha").forEach((s) => (s.hidden = true));
  const alvo = document.getElementById(a.getAttribute("href").slice(1));
  if (alvo) { alvo.hidden = false; window.scrollTo(0, 0); }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest('a[href="#inicio"]')) return;
  e.preventDefault();
  document.querySelectorAll(".folha-ficha").forEach((s) => (s.hidden = true));
  window.scrollTo(0, 0);
});
</script>
"""
    index = index.replace("</body>", seccoes_html + scripts + router + "\n</body>")
    destino.write_text(index, encoding="utf-8")
    return destino, destino.stat().st_size


def construir_folha(destino: Path) -> tuple[Path, int]:
    tmp = Path(tempfile.mkdtemp(prefix="uai-folha-"))
    try:
        uai.construir(tmp)
        return juntar(tmp, destino)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    destino = Path(argv[1]) if len(argv) > 1 else RAIZ / "uai.html"
    caminho, tamanho = construir_folha(destino)
    print(f"a UAI numa folha só: {caminho} — {tamanho / 1024:.0f} KB")
    print("manda-se por mensagem e abre em qualquer telemóvel, sem internet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
