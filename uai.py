#!/usr/bin/env python3
"""UAI — o motor das fichas. Python puro (stdlib), sem dependências.

    python3 uai.py validar             # as leis da casa, ficha a ficha
    python3 uai.py construir [saida]   # gera o site estático (padrão: site/)
    python3 uai.py receber entrega.json  # o que veio do «deixar uma ficha»

Uma ficha é um ficheiro em fichas/<id>.json: um lugar e uma lista de
registos que só cresce. O estado de hoje é o do último registo que trouxe
estado; «desde quando» é a data desse registo. Nada disto se escreve à mão —
calcula-se, para que não possa mentir.

As leis que aqui viram código:
  - com procedência: todo registo diz de onde veio (fonte.descricao);
  - mover é ligar, nunca apagar: os registos já guardados têm de continuar lá,
    iguais e pela mesma ordem — e a ficha traz o seu próprio carimbo (a corrente
    de selos), para a lei não depender do `git show` (24/11/2026);
  - nunca quem contou: campos de identificação pessoal não entram;
  - cada ficha tem data e estado: calculados, e com «há quanto tempo».
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import shutil
import zlib
import subprocess
import sys
from pathlib import Path

import mapa
import regua

RAIZ = Path(__file__).resolve().parent
FICHAS = RAIZ / "fichas"
# A segunda metade da UAI (23/11/2026): as pessoas. Ficam à parte das fichas de lugar — uma
# pessoa não é um sítio, e obriga a regras que um sítio não obriga (autorização, e o direito de sair).
GENTE = RAIZ / "gente"
ACERVO = RAIZ / "acervo" / "fotos"
CONTATO = RAIZ / "contato.json"


def carregar_gente(pasta: Path | None = None) -> dict[str, dict]:
    """As fichas de pessoa — só as que estão de pé (as retiradas ficam guardadas, mas não se mostram)."""
    pasta = pasta or GENTE
    gente: dict[str, dict] = {}
    if not Path(pasta).is_dir():
        return gente
    for f in sorted(Path(pasta).glob("*.json")):
        gente[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return gente


def de_pe(ficha: dict) -> bool:
    """Está no sítio? Uma ficha retirada não aparece — mas não se apaga (23/11/2026)."""
    return not ficha.get("retirada")


def carregar_contato() -> dict:
    """Para onde vão as histórias. Um sítio só, declarado (23/11/2026).

    Nasceu de um defeito medido: o botão do «deixar» apontava para `wa.me` **sem destinatário** —
    o visitante contava a história e ela não chegava a ninguém. A lei da UAI é «com procedência»;
    o destinatário também tem de estar dito.
    """
    try:
        d = json.loads(CONTATO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    return {
        "nome": str(d.get("nome") or "UAI · Passos"),
        "whatsapp": re.sub(r"\D", "", str(d.get("whatsapp") or "")),
        "email": str(d.get("email") or "").strip(),
    }


def telefone_bonito(so_digitos: str) -> str:
    """(35) 99100-2375 a partir de 5535991002375 — como se diz em voz alta."""
    d = re.sub(r"\D", "", so_digitos or "")
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return so_digitos or ""


def _zap(quem: dict | None = None, texto: str = "") -> str:
    """O link do WhatsApp — com o destino declarado (23/11/2026: antes ia para o vazio)."""
    import urllib.parse

    quem = quem or carregar_contato()
    alvo = quem["whatsapp"]
    if not alvo:
        return "https://wa.me/"
    return f"https://wa.me/{alvo}" + (f"?text={urllib.parse.quote(texto)}" if texto else "")



ESTADOS = ("floresce", "pede cuidado", "por fazer", "em obra")

TIPOS = {
    "verificado": "visto com os olhos, em foto ou documento",
    "contado": "dito por quem viveu ou ouviu de quem viveu",
    "leitura": "o que parece — interpretação, não facto",
    "falta saber": "pergunta aberta",
    "contesta": "alguém diz «não é assim»",
    "pedido": "bati à porta — o pedido em si, sem a resposta ainda",
}
# Os estados que o mapa pode mostrar: os quatro de um registo escrito à mão mais
# os dois que só o tempo sabe (`regua.tempo_da_ficha`). `ESTADOS` não os leva:
# adormecer e criar raiz não se escrevem num registo — calculam-se.
ESTADOS_NO_MAPA = (*ESTADOS, "adormeceu", "tem raiz")

CAMPOS_FICHA = {"lugar", "pessoa", "autorizou", "registos", "retirada", "carimbos", "selo_retirada"}   # as duas metades: lugar e pessoa
CAMPOS_LUGAR = {"nome", "referencia"}
# A ficha de PESSOA (23/11/2026). Campos a mais, e todos com razão de ser:
#   nome      — o nome dela (não o do registo civil: o que ela usa)
#   se_chama  — como se apresenta, se for diferente (opcional)
#   oficio    — o que faz, o que sabe fazer, o que a casa lhe deve
#   onde_vive — a terra, o bairro (nunca a rua nem o número — isso é a casa dela)
CAMPOS_PESSOA = {"nome", "se_chama", "oficio", "onde_vive", "referencia"}
# A autorização é obrigatória: sem ela, a ficha não entra. E as três palavras são estas — «por»
# (quem autorizou), «quando» e «como». Nada de campo «quem»: esse é o proibido dos que contam.
CAMPOS_AUTORIZOU = {"por", "quando", "como"}
CAMPOS_RETIRADA = {"quando", "pedido_por"}
COMOS_DE_AUTORIZAR = ("disse em voz", "escreveu", "a família autorizou", "publica ele mesmo")
CAMPOS_REGISTO = {"data", "epoca", "entrou", "tipo", "estado", "texto", "fonte", "pediu_em", "recusou", "toca"}
CAMPOS_FONTE = {"descricao", "url", "foto"}
# Lei 2 — nunca quem contou. Não se confia em quem preenche: recusa-se o campo.
CAMPOS_PROIBIDOS = {"autor", "nome_de_quem", "quem", "contato", "contacto", "email", "telefone", "cpf"}

DATA_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
DIA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ───────────────────────── leitura ─────────────────────────


def carregar(pasta: Path = FICHAS) -> dict[str, dict]:
    fichas = {}
    for f in sorted(pasta.glob("*.json")):
        fichas[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return fichas


def fotos_do_acervo(pasta: Path = ACERVO) -> dict[str, dict]:
    lista = pasta / "acervo.json"
    if not lista.exists():
        return {}
    return {item["ficheiro"]: item for item in json.loads(lista.read_text(encoding="utf-8"))}


# ───────────────────────── créditos (24/11/2026) ─────────────────────────
# A licença livre não dispensa o crédito — e o crédito, sem link, não se
# cumpre. Cada foto leva o autor, a licença (com o link que a CC pede) e a
# página de origem no Wikimedia Commons. O mapa leva a base (ODbL) e o relevo
# (Terrain Tiles/SRTM, cortesia do USGS).

LICENCAS_CC = {
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
}


def licenca_url(licenca: str) -> str:
    """O link canónico da licença Creative Commons — a CC exige-o ao lado do crédito."""
    return LICENCAS_CC.get(licenca, "")


def origem_url(it: dict) -> str:
    """A página do ficheiro no Wikimedia Commons — a fonte do crédito da foto."""
    import urllib.parse

    t = it.get("titulo", "")
    if t.startswith("File:"):
        return "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"), safe=":")
    return it.get("url", "")


def versao_anterior(id_: str, ref: str = "HEAD", pasta: str = "fichas") -> dict | None:
    """A ficha como estava no último commit (None se é nova ou não há git)."""
    try:
        r = subprocess.run(
            ["git", "show", f"{ref}:{pasta}/{id_}.json"],
            cwd=RAIZ, capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


# ───────────────────────── as leis ─────────────────────────


def _proibidos(obj: dict, onde: str) -> list[str]:
    return [f"{onde}: o campo «{k}» não entra — nunca quem contou" for k in obj if k in CAMPOS_PROIBIDOS]


def _validar_pessoa(ficha: dict) -> tuple[list[str], list[str]]:
    """As regras que só uma pessoa obriga (23/11/2026).

    A UAI não guarda quem CONTou — isso continua proibido. Mas guarda quem AUTORIZOU: uma pessoa
    só entra com a sua palavra, e a palavra fica escrita, com o dia e com o modo. É a diferença
    entre um arquivo e uma colecção: uma colega entra, uma collectânea não.

    E a autorização não é um campo de simpatia: sem ela, a ficha não entra — erro, não aviso.
    """
    erros: list[str] = []
    avisos: list[str] = []
    p = ficha.get("pessoa")
    if not isinstance(p, dict) or not str(p.get("nome", "")).strip():
        erros.append("falta pessoa.nome")
    else:
        erros += _proibidos(p, "pessoa")
        for k in set(p) - CAMPOS_PESSOA - CAMPOS_PROIBIDOS:
            erros.append(f"campo desconhecido em pessoa: «{k}»")
        if p.get("onde_vive") and re.search(r"\d", str(p["onde_vive"])):
            avisos.append("onde_vive parece ter número — a rua e o número não entram: a casa dela é dela")

    a = ficha.get("autorizou")
    if not isinstance(a, dict):
        erros.append("falta «autorizou» (por, quando, como) — uma pessoa só entra com a sua palavra")
    else:
        erros += _proibidos(a, "autorizou")
        for k in set(a) - CAMPOS_AUTORIZOU - CAMPOS_PROIBIDOS:
            erros.append(f"campo desconhecido em autorizou: «{k}»")
        if not str(a.get("por", "")).strip():
            erros.append("autorizou.por: falta o nome de quem autorizou")
        if not (isinstance(a.get("quando"), str) and DIA_RE.match(str(a["quando"]))):
            erros.append("autorizou.quando: falta o dia (AAAA-MM-DD)")
        if a.get("como") not in COMOS_DE_AUTORIZAR:
            erros.append("autorizou.como deve ser um de: " + " · ".join(COMOS_DE_AUTORIZAR))

    r = ficha.get("retirada")
    if r is not None:
        if not isinstance(r, dict):
            erros.append("«retirada» tem de ser um objeto com quando e pedido_por")
        else:
            erros += _proibidos(r, "retirada")
            for k in set(r) - CAMPOS_RETIRADA - CAMPOS_PROIBIDOS:
                erros.append(f"campo desconhecido em retirada: «{k}»")
            if not (isinstance(r.get("quando"), str) and DIA_RE.match(str(r["quando"]))):
                erros.append("retirada.quando: falta o dia (AAAA-MM-DD)")
            if not str(r.get("pedido_por", "")).strip():
                erros.append("retirada.pedido_por: falta quem pediu — ela própria, ou quem a representa")
    return erros, avisos


def validar_ficha(id_: str, ficha: dict, fotos: dict | None = None,
                   fichas: dict | None = None, gente: dict | None = None,
                   na_porta: bool = False) -> tuple[list[str], list[str]]:
    """Devolve (erros, avisos). Erro impede a ficha de entrar; aviso mostra-se na página.

    `na_porta=True` é o crivo da porta (24/11/2026, achado do Chagas): uma ficha NOVA que diga
    «verificado» sem prova (link ou foto do acervo) é **recusada** — não avisada. O que já está
    dentro da estante não cai: o selo é que não se mostra (ver `_registo_li` e `situacao`).
    """
    fotos = fotos_do_acervo() if fotos is None else fotos
    if fichas is None or gente is None:
        fichas_todas = carregar()
        gente_todas = carregar_gente()
        fichas = fichas_todas if fichas is None else fichas
        gente = gente_todas if gente is None else gente
    erros: list[str] = []
    avisos: list[str] = []

    if not ID_RE.match(id_):
        erros.append(f"o nome do ficheiro «{id_}» deve ser minúsculas-com-hifens")
    if not isinstance(ficha, dict):
        return ["a ficha não é um objeto JSON"], []
    erros += _proibidos(ficha, "ficha")
    genero = "pessoa" if "pessoa" in ficha else "lugar"
    if "pessoa" in ficha and "lugar" in ficha:
        erros.append("uma ficha é de um lugar OU de uma pessoa — não das duas coisas")
    permitidos = ({"pessoa", "autorizou", "registos", "retirada"} if genero == "pessoa"
                  else {"lugar", "registos"}) | {"carimbos", "selo_retirada"}
    for k in set(ficha) - permitidos - CAMPOS_PROIBIDOS:
        erros.append(f"campo desconhecido na ficha: «{k}»")

    if genero == "pessoa":
        e_pessoa, avisos = _validar_pessoa(ficha)
        erros += e_pessoa
    else:
        lugar = ficha.get("lugar")
        if not isinstance(lugar, dict) or not str(lugar.get("nome", "")).strip():
            erros.append("falta lugar.nome")
        else:
            erros += _proibidos(lugar, "lugar")
            for k in set(lugar) - CAMPOS_LUGAR - CAMPOS_PROIBIDOS:
                erros.append(f"campo desconhecido em lugar: «{k}»")

    registos = ficha.get("registos")
    if not isinstance(registos, list) or not registos:
        erros.append("a ficha precisa de pelo menos um registo")
        return erros, avisos

    entrou_antes = ""
    for i, r in enumerate(registos, 1):
        onde = f"registo {i}"
        if not isinstance(r, dict):
            erros.append(f"{onde}: não é um objeto")
            continue
        erros += _proibidos(r, onde)
        for k in set(r) - CAMPOS_REGISTO - CAMPOS_PROIBIDOS:
            erros.append(f"{onde}: campo desconhecido «{k}»")
        if r.get("tipo") not in TIPOS:
            erros.append(f"{onde}: tipo deve ser um de {', '.join(TIPOS)}")
        if not str(r.get("texto", "")).strip():
            erros.append(f"{onde}: falta o texto")
        if "estado" in r and r["estado"] not in ESTADOS:
            erros.append(f"{onde}: estado deve ser um de {', '.join(ESTADOS)}")

        data, epoca = r.get("data"), r.get("epoca")
        if data is None and not str(epoca or "").strip():
            erros.append(f"{onde}: precisa de data (AAAA, AAAA-MM ou AAAA-MM-DD) ou de época")
        if data is not None and not (isinstance(data, str) and DATA_RE.match(data)):
            erros.append(f"{onde}: data «{data}» não é AAAA, AAAA-MM nem AAAA-MM-DD")

        entrou = r.get("entrou")
        if not (isinstance(entrou, str) and DIA_RE.match(entrou)):
            erros.append(f"{onde}: falta «entrou» (AAAA-MM-DD — o dia em que chegou à UAI)")
        else:
            if entrou < entrou_antes:
                erros.append(f"{onde}: entrou antes do registo anterior — registos só se acrescentam no fim")
            entrou_antes = entrou
            if isinstance(data, str) and DIA_RE.match(data) and data > entrou:
                erros.append(f"{onde}: a data ({data}) é depois de ter entrado ({entrou})")

        # 23/11/2026 — a casa mede o que não media: o pedido, o não, e o laço
        pediu = r.get("pediu_em")
        if pediu is not None and not (isinstance(pediu, str) and DIA_RE.match(pediu)):
            erros.append(f"{onde}: pediu_em «{pediu}» não é AAAA-MM-DD")
        rec = r.get("recusou")
        if rec is not None:
            if not isinstance(rec, dict):
                erros.append(f"{onde}: recusou tem de ser um objeto com por e quando")
            else:
                erros += _proibidos(rec, f"{onde}, recusou")
                for k in set(rec) - {"por", "quando", "como"} - CAMPOS_PROIBIDOS:
                    erros.append(f"{onde}: campo desconhecido em recusou: «{k}»")
                if not str(rec.get("por", "")).strip():
                    erros.append(f"{onde}: recusou.por — falta quem recusou")
                if not (isinstance(rec.get("quando"), str) and DIA_RE.match(str(rec["quando"]))):
                    erros.append(f"{onde}: recusou.quando — falta o dia (AAAA-MM-DD)")
        toca = r.get("toca")
        if toca is not None:
            if not isinstance(toca, list):
                erros.append(f"{onde}: toca tem de ser uma lista de ids de fichas")
            else:
                for t in toca:
                    if not isinstance(t, str) or not t.strip():
                        erros.append(f"{onde}: toca tem ids vazios")

        fonte = r.get("fonte")
        if not isinstance(fonte, dict) or not str(fonte.get("descricao", "")).strip():
            erros.append(f"{onde}: falta fonte.descricao — um dado sem procedência não entra")
            continue
        erros += _proibidos(fonte, f"{onde}, fonte")
        for k in set(fonte) - CAMPOS_FONTE - CAMPOS_PROIBIDOS:
            erros.append(f"{onde}: campo desconhecido em fonte: «{k}»")
        url = fonte.get("url")
        if url is not None and not re.match(r"^https?://", str(url)):
            erros.append(f"{onde}: fonte.url tem de ser um link público (http/https), não «{url}»")
        foto = fonte.get("foto")
        if foto is not None and foto not in fotos:
            erros.append(f"{onde}: a foto «{foto}» não está no acervo (acervo/fotos/acervo.json)")
        if r.get("tipo") == "verificado" and regua.avaliar(r, fotos)["verificado_sem_prova"]:
            # 24/11/2026 (Chagas): o barbeiro da UAI é o selo emprestado. Na porta, recusa-se;
            # na estante, o selo não se mostra — a ficha fica marcada «prova por juntar».
            # Agora a decisão é UMA só: a régua (regua.avaliar). Uma foto-fantasma — um nome
            # que o acervo não tem — também não é prova: é promessa de prova.
            texto = f"{onde}: prova por juntar — «verificado» sem foto no acervo nem link"
            (erros if na_porta else avisos).append(texto)

    # 23/11/2026 — o laço: um registo que toca outra ficha, e essa ficha tem retirada
    for i, r in enumerate(registos, 1):
        toca = r.get("toca")
        if toca:
            for t in toca:
                outra = fichas.get(t) or gente.get(t)
                if outra and outra.get("retirada"):
                    avisos.append(f"registo {i}: toca a ficha «{t}», que tem retirada — avisa quem guarda")

    # 24/11/2026 — o carimbo próprio: a ficha traz a corrente de selos que tinha quando foi
    # gravada. Com selos, eles têm de fechar — e isso não depende do `git show`. Na porta
    # (um registo que chega), não se julga o carimbo da ficha inteira: julga-se o que entra.
    if not na_porta:
        erros += carimbo_quebrado(ficha)

    if not any("estado" in r for r in registos if isinstance(r, dict)):
        avisos.append("ainda sem estado: nenhum registo disse como a coisa está")
    return erros, avisos


def nunca_apagar(antiga: dict | None, nova: dict) -> list[str]:
    """Lei 3. Os registos já guardados continuam lá, iguais e pela mesma ordem.

    `antiga` pode vir do disco (a previsão de uma entrega) ou do último commit
    (`versao_anterior`). Desde 24/11/2026 a lei não depende do git: o carimbo próprio
    da ficha (`carimbo_quebrado`) denuncia a mudança sozinho. Esta comparação fica
    como segunda testemunha, quando há uma versão anterior para comparar.
    """
    if not antiga:
        return []
    erros = []
    # a excepção, e é a única (23/11/2026): quem pediu para sair não volta a entrar como se nada
    if antiga.get("retirada") and not nova.get("retirada"):
        erros.append("uma retirada não se apaga: quem saiu, saiu — a ficha pode voltar, mas com a retirada ao lado")
    velhos, novos = antiga.get("registos", []), nova.get("registos", [])
    if len(novos) < len(velhos):
        erros.append(f"tinha {len(velhos)} registos e agora tem {len(novos)} — nada se apaga")
    for i, (v, n) in enumerate(zip(velhos, novos), 1):
        if v != n:
            erros.append(f"o registo {i} foi mudado — corrige-se acrescentando um registo novo, com a data ao lado")
    if antiga.get("lugar", {}).get("nome") != nova.get("lugar", {}).get("nome"):
        erros.append("o nome do lugar mudou — um lugar com outro nome é outra ficha")
    return erros


def validar_onde(onde: dict, fichas: dict, moldura: dict) -> list[str]:
    """Lei 4 também no mapa: um ponto sem fonte não entra, e uma dúvida desenha-se como dúvida."""
    erros = []
    for id_, o in onde.items():
        onde_ = f"onde.json «{id_}»"
        if id_ not in fichas:
            erros.append(f"{onde_}: não há ficha com este nome")
        if not isinstance(o, dict):
            erros.append(f"{onde_}: devia ser um objeto")
            continue
        erros += _proibidos(o, onde_)
        lat, lon = o.get("lat"), o.get("lon")
        if not all(isinstance(v, (int, float)) for v in (lat, lon)):
            erros.append(f"{onde_}: faltam lat e lon (números)")
        elif not (moldura["sul"] - 0.5 <= lat <= moldura["norte"] + 0.5 and moldura["oeste"] - 0.5 <= lon <= moldura["leste"] + 0.5):
            erros.append(f"{onde_}: longe demais de Passos ({lat}, {lon}) — engano nas coordenadas?")
        if o.get("precisao") not in mapa.PRECISOES:
            erros.append(f"{onde_}: precisao deve ser {' ou '.join(mapa.PRECISOES)}")
        if o.get("precisao") == "aproximado" and not (isinstance(o.get("raio_m"), (int, float)) and o["raio_m"] > 0):
            erros.append(f"{onde_}: um lugar aproximado diz o tamanho da dúvida (raio_m)")
        fonte = o.get("fonte")
        if not isinstance(fonte, dict) or not str(fonte.get("descricao", "")).strip():
            erros.append(f"{onde_}: falta fonte.descricao — um ponto sem procedência não entra")
        elif fonte.get("url") and not re.match(r"^https?://", str(fonte["url"])):
            erros.append(f"{onde_}: fonte.url tem de ser um link público (http/https)")
    return erros


def no_mapa(o: dict, moldura: dict) -> bool:
    """O ponto cabe na moldura desenhada? (Uma ficha pode ser de fora — fica na lista, não no mapa.)"""
    return moldura["sul"] <= o["lat"] <= moldura["norte"] and moldura["oeste"] <= o["lon"] <= moldura["leste"]


def lugares_no_mapa(fichas: dict, onde: dict, moldura: dict, hoje: dt.date) -> list[dict]:
    saida = []
    for id_, o in onde.items():
        f = fichas.get(id_)
        if not f or not no_mapa(o, moldura):
            continue
        x, y = mapa.projetar(moldura, o["lat"], o["lon"])
        s = situacao(f, hoje)
        nome = f["lugar"]["nome"]
        n = len(f["registos"])
        rotulo = (f"{nome} — {s['estado_da_ficha'] or s['estado'] or 'sem estado'}" + (" (lugar aproximado)" if o["precisao"] == "aproximado" else "")
                  + f" · {n} {'história contada' if n == 1 else 'histórias contadas'}")
        saida.append({"id": id_, "nome": nome, "estado": s["estado_da_ficha"] or s["estado"], "tempo": s["tempo"], "x": x, "y": y,
                      "raio": o.get("raio_m", 0), "precisao": o["precisao"], "rotulo": rotulo, "historias": n})
    return saida


# ───────────────────────── o que se calcula ─────────────────────────


def _dia(s: str | None) -> dt.date | None:
    if isinstance(s, str) and DIA_RE.match(s):
        return dt.date.fromisoformat(s)
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}$", s):
        return dt.date.fromisoformat(s + "-01")
    if isinstance(s, str) and re.match(r"^\d{4}$", s):
        return dt.date(int(s), 1, 1)
    return None


def situacao(ficha: dict, hoje: dt.date, fotos: dict | None = None) -> dict:
    """Estado de hoje, desde quando, há quantos dias, e os sinais do zelo.

    `fotos` é o acervo — a régua de prova precisa dele para saber se a foto que um
    registo nomeia existe mesmo (uma foto-fantasma não é prova). Sem `fotos`, lê-se
    o acervo do disco.
    """
    fotos = fotos_do_acervo() if fotos is None else fotos
    regs = ficha["registos"]
    com_estado = [r for r in regs if "estado" in r]
    ultimo = com_estado[-1] if com_estado else None
    desde = (ultimo.get("data") if ultimo and ultimo.get("data") else ultimo["entrou"]) if ultimo else None
    d = _dia(desde)
    ultima_entrada = max(dt.date.fromisoformat(r["entrou"]) for r in regs)
    parada = (hoje - ultima_entrada).days
    cuidado = []
    if not any(r["tipo"] in ("verificado", "contado") for r in regs):
        if any(r["tipo"] == "pedido" for r in regs):
            cuidado.append("esperando_resposta")  # só tem pedidos — a porta bateu e ninguém abriu
        else:
            cuidado.append("broto")  # ainda ninguém viu nem contou: só leituras e perguntas
    # O tempo é lido na régua — não se conta outra vez aqui (uma régua, três leitores).
    tempo = regua.tempo_da_ficha(ficha, hoje)
    if tempo == "adormeceu":
        cuidado.append("adormecida")
    if regs[-1]["tipo"] == "contesta":
        cuidado.append("contestada")
    # 24/11/2026: um selo emprestado é um cuidado — a ficha pede a prova, e não a tem.
    # A decisão é UMA só: a régua (regua.avaliar). Uma foto-fantasma também cai aqui.
    if any(regua.avaliar(x, fotos)["verificado_sem_prova"] for x in regs):
        cuidado.append("prova por juntar")
    return {
        "estado": ultimo["estado"] if ultimo else None,
        "desde": desde,
        "dias": (hoje - d).days if d else None,
        "perguntas": sum(1 for r in regs if r["tipo"] == "falta saber"),
        "ultima_entrada": ultima_entrada.isoformat(),
        "parada_ha": parada,
        "cuidado": cuidado,
        "estado_da_ficha": regua.estado_da_ficha(ficha, hoje, fotos),
        "tempo": tempo,
    }


def _canonico(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _cabeca(ficha: dict) -> dict:
    """O que identifica a ficha e não se acrescenta: o lugar, ou a pessoa com a sua palavra."""
    if "pessoa" in ficha:
        return {"pessoa": ficha.get("pessoa", {}), "autorizou": ficha.get("autorizou", {})}
    return {"lugar": ficha.get("lugar", {})}


def carimbos(ficha: dict) -> list[str]:
    """Corrente de SHA-256: cada registo sela o anterior. Mudar um registo
    antigo muda todos os carimbos dali para a frente — vê-se a olho.
    O primeiro selo sela a cabeça: o lugar, ou a pessoa e a sua autorização."""
    h = hashlib.sha256(_canonico(_cabeca(ficha))).hexdigest()
    saida = []
    for r in ficha.get("registos") or []:
        h = hashlib.sha256(h.encode() + _canonico(r)).hexdigest()
        saida.append(h)
    return saida


def selo_retirada(ficha: dict) -> str | None:
    """O selo da retirada — a única excepção à lei, e também ela não se apaga (23/11/2026)."""
    r = ficha.get("retirada")
    if r is None:
        return None
    return hashlib.sha256(_canonico(r)).hexdigest()


def carimbo_quebrado(ficha: dict) -> list[str]:
    """A lei «nada se apaga» sem depender do git (24/11/2026).

    A ficha traz o seu próprio carimbo: a corrente de selos que ela tinha quando foi
    gravada. Se um registo antigo foi mudado ou tirado, os selos guardados já não fecham
    com os registos que lá estão — e vê-se sem `git show`, sem repositório, sem nada.
    Ficha sem carimbo (antiga) não é erro: o `selar` põe-lhe o carimbo.
    """
    guardados = ficha.get("carimbos")
    if guardados is not None:
        if not isinstance(guardados, list) or not all(isinstance(c, str) for c in guardados):
            return ["«carimbos» tem de ser uma lista de selos (SHA-256 em hexadecimal)"]
        registos = ficha.get("registos") or []
        if len(guardados) != len(registos):
            return [f"«carimbos» tem {len(guardados)} selo(s) e a ficha tem {len(registos)} "
                    f"registo(s) — um registo antigo foi tirado (nada se apaga)"]
        for i, (guardado, esperado) in enumerate(zip(guardados, carimbos(ficha)), 1):
            if guardado != esperado:
                return [f"o carimbo {i} não fecha — o registo {i} foi mudado depois de selado "
                        f"(nada se apaga: corrige-se acrescentando, com a data ao lado)"]
    # a retirada também não se apaga — o selo dela fica na ficha
    selo = ficha.get("selo_retirada")
    if selo is not None:
        if ficha.get("retirada") is None:
            return ["há um selo de retirada sem retirada — a retirada não se apaga: quem saiu, saiu"]
        if selo != selo_retirada(ficha):
            return ["o selo da retirada não fecha — a retirada foi mudada (quem saiu, saiu)"]
    return []


def selar(ficha: dict) -> None:
    """Põe o carimbo próprio dentro da ficha (24/11/2026).

    Só calcula e guarda — quem chama verifica primeiro com `carimbo_quebrado`, para
    não selar por cima de uma ficha que já não fecha.
    """
    ficha["carimbos"] = carimbos(ficha)
    selo = selo_retirada(ficha)
    if selo is not None:
        ficha["selo_retirada"] = selo


# ───────────────────────── o site ─────────────────────────

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
e = html.escape


def data_curta(s: str | None) -> str:
    if not s:
        return ""
    p = s.split("-")
    if len(p) == 3:
        return f"{int(p[2])} {MESES[int(p[1]) - 1]} {p[0]}"
    if len(p) == 2:
        return f"{MESES[int(p[1]) - 1]} {p[0]}"
    return p[0]


def ha_quanto(dias: int | None) -> str:
    if dias is None:
        return ""
    if dias <= 0:
        return "hoje"
    if dias == 1:
        return "há 1 dia"
    if dias < 60:
        return f"há {dias} dias"
    if dias < 730:
        return f"há {dias // 30} meses"
    return f"há {dias // 365} anos"


ESTATICO = RAIZ / "estatico"
JORNADAS_TRACADAS: list[dict] = []  # preenchidas em construir(): o cartão e a página de início leem-nas
VERSAO = "0"  # trocada em construir(): um hash do que se publica, para o navegador não servir o velho
ATRIBUICAO = ('mapa: © <a href="https://www.openstreetmap.org/copyright" rel="noopener">colaboradores do OpenStreetMap</a> · base sob ODbL · '
              'relevo: Terrain Tiles · SRTM/GMTED2010, cortesia do U.S. Geological Survey')


# Os jeitos de ver: três modos (que são só pontos de partida), cinco camadas e dois filtros.
# Pouco de propósito — o mapa aponta para a cidade; não é para prender ninguém à tela.
MODOS = (
    ("sossego", "sossego", "Só o chão e os lugares da UAI. Leve e quieto, bom para ler."),
    ("passeio", "passeio", "O mapa como ele é: os convites aparecem quando se aproxima."),
    ("explorador", "explorador", "Para sair de casa: tudo à vista, o que fica perto e quanto se anda a pé."),
)
CAMADAS = (
    ("relevo", "relevo e curvas de nível"),
    ("nomes", "nomes de bairros, rios e pontes"),
    ("convites", "convites — praças, igrejas, escolas…"),
    ("gente", "gente — uma pessoinha por história"),
    ("jornadas", "jornadas — caminhadas pelas ruas"),
)
ICONE_VER = ('<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" '
             'stroke-width="1.8" stroke-linejoin="round"><path d="M12 3 3 8l9 5 9-5z"/><path d="m3 12 9 5 9-5"/>'
             '<path d="m3 16 9 5 9-5"/></svg>')
ICONE_AQUI = ('<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" '
              'stroke-width="1.8" stroke-linejoin="round"><path d="M12 3 19 20l-7-4-7 4z"/></svg>')


def cartao_ver() -> str:
    """O cartão «jeitos de ver», por cima do mapa. Fechado até alguém o pedir."""
    modos = "".join(
        f'<button type="button" role="radio" aria-checked="false" data-modo="{k}" data-dica="{e(d)}">{e(r)}</button>'
        for k, r, d in MODOS)
    camadas = "".join(
        f'<label class="ver-camada"><input type="checkbox" data-camada="{k}" checked> {e(r)}</label>'
        for k, r in CAMADAS)
    estados = "".join(
        f'<button type="button" class="ver-chip e-{_classe(x)}" aria-pressed="true" data-estado="{_classe(x)}">'
        f'<i aria-hidden="true"></i>{e(x or "sem estado")}</button>' for x in (*ESTADOS_NO_MAPA, None))
    cats = "".join(
        f'<button type="button" class="ver-chip c-{k}" aria-pressed="true" data-cat="{k}">'
        f'<svg viewBox="-10 -10 20 20" width="16" height="16" aria-hidden="true"><circle r="9" fill="var(--c)"/>'
        f'<g fill="#fff">{mapa.ICONES[k]}</g></svg>{e(v)}</button>' for k, v in mapa.CATEGORIAS.items())
    jornadas = ""
    if JORNADAS_TRACADAS:
        itens = "".join(
            f'<li><button type="button" data-jornada="{e(j["id"])}" aria-pressed="false"><b>{e(j["nome"])}</b>'
            f'<span>{len(j["paradas"])} paradas · {e(mapa.distancia(j["metros"]))} · {e(mapa.a_pe(j["minutos"]))}</span></button></li>'
            for j in JORNADAS_TRACADAS)
        convites = "".join(f'<p class="ver-convite" data-convite="{e(j["id"])}" hidden>{e(j["convite"])}</p>' for j in JORNADAS_TRACADAS)
        jornadas = (f'<div class="ver-jornadas"><h3>Jornadas</h3><ol class="ver-lista">{itens}</ol>{convites}'
                    '<ol class="ver-paradas" hidden></ol></div>')
    return f"""<section class="ver" id="ver" hidden aria-labelledby="ver-t">
<div class="ver-topo"><h2 id="ver-t">Jeitos de ver</h2><button type="button" class="ver-fechar" data-ver="fechar" aria-label="fechar">×</button></div>
<div class="ver-modos" role="radiogroup" aria-label="modo">{modos}</div>
<p class="ver-dica" aria-live="polite"></p>
<div class="ver-vista" role="radiogroup" aria-label="vista"><span>vista</span>
<button type="button" role="radio" aria-checked="true" data-vista="cima">de cima</button>
<button type="button" role="radio" aria-checked="false" data-vista="inclinada">inclinada</button></div>
{jornadas}
<div class="ver-perto" hidden>
<div class="ver-perto-topo"><h3>Perto daqui</h3><button type="button" class="ver-link" data-ver="aqui">estou aqui</button></div>
<p class="ver-nota ver-onde"></p>
<ol class="ver-lista"></ol>
</div>
<details class="ver-mais">
<summary>camadas e filtros</summary>
<h3>Camadas</h3>
<div class="ver-camadas">{camadas}</div>
<h3>Lugares da UAI, pelo estado</h3>
<div class="ver-chips" data-filtro="estado">{estados}</div>
<h3>Convites, pelo tipo</h3>
<div class="ver-chips" data-filtro="cat">{cats}</div>
</details>
<p class="ver-nota">O mapa aponta; o lugar é que conta. As escolhas ficam só neste aparelho. <button type="button" class="ver-link" data-ver="repor">repor</button></p>
</section>"""


def pagina(titulo: str, corpo: str, descricao: str = "", foco: str = "", scripts: tuple = ()) -> str:
    """Uma tela só: o mapa por baixo (#cena), a folha de leitura por cima (.painel)."""
    foco_attr = f' data-foco="{e(foco)}"' if foco else ""
    voltar = '<button type="button" data-acao="voltar" title="voltar a este lugar" aria-label="voltar a este lugar">⌖</button>' if foco else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%232b7a47' opacity='.25'/%3E%3Ccircle cx='16' cy='16' r='7' fill='%232b7a47'/%3E%3C/svg%3E">
<meta name="theme-color" content="#0F2A22" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0F2A22" media="(prefers-color-scheme: dark)">
<link rel="preload" href="fontes/Fraunces-normal-300-700.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="fontes/fontes.css?v={VERSAO}">
<link rel="stylesheet" href="uai.css?v={VERSAO}">
<script>try{{for(const k of["letra-grande","contraste","so-texto"])if(localStorage.getItem("uai:"+k)==="1")document.documentElement.classList.add(k);const f=localStorage.getItem("uai:fundo");if(f==="azul"||f==="terra")document.documentElement.dataset.fundo=f}}catch(e){{}}</script>
<script src="acesso.js?v={VERSAO}" defer></script>
<script src="mapa.js?v={VERSAO}" data-versao="{VERSAO}" defer></script>
{"".join(f'<script src="{s}?v={VERSAO}" defer></script>' for s in scripts)}
</head>
<body{foco_attr}>
<a class="pular" href="#conteudo">pular o mapa e ir para o texto</a>
<div id="cena" role="region" aria-label="Mapa — arraste para andar, roda ou beliscão para aproximar">
<div class="norte" aria-hidden="true">N</div>
<div class="controles" hidden>
<button type="button" data-acao="mais" aria-label="aproximar">+</button>
<button type="button" data-acao="menos" aria-label="afastar">−</button>
{voltar}<button type="button" data-acao="tudo" title="ver a região toda" aria-label="ver a região toda">◎</button>
<button type="button" data-acao="aqui" class="so-explorador" title="estou aqui — a posição fica só no seu aparelho" aria-label="estou aqui">{ICONE_AQUI}</button>
<button type="button" data-acao="ver" title="jeitos de ver: modos, camadas e filtros" aria-label="jeitos de ver: modos, camadas e filtros" aria-expanded="false" aria-controls="ver">{ICONE_VER}</button>
</div>
{cartao_ver()}
<div class="jornada-barra" role="group" aria-label="jornada, parada a parada" hidden>
<button type="button" data-j="fechar" aria-label="fechar a jornada">×</button>
<p aria-live="polite"><b></b><span></span></p>
<button type="button" data-j="antes" aria-label="parada anterior">‹</button>
<button type="button" data-j="depois" aria-label="próxima parada">›</button>
</div>
<div class="la-fora" role="status" hidden><p>Já faz um tempinho de mapa. O melhor de Passos está lá fora — escolha um lugar daqui e vá ver de perto.</p><button type="button">combinado</button></div>
<div class="rodape-mapa"><span id="escala" aria-hidden="true"><i></i><b></b></span><span class="atrib">{ATRIBUICAO}</span></div>
</div>
<main class="painel" id="conteudo" tabindex="-1">
<button type="button" class="pega" id="pega" aria-label="estender a folha" aria-expanded="false" aria-controls="conteudo"></button>
{corpo}
<footer class="rodape"><p>UAI · Unidade de Acompanhamento e Informação · Passos, MG</p>
<p>fonte · data · estado — ao lado de cada coisa.</p>
<p><a href="index.html">início</a> · <a href="acervo.html">acervo</a> · <a href="deixar.html">contar uma história</a> · <a href="creditos.html">créditos</a></p></footer>
</main>
</body>
</html>
"""


def _classe(estado: str | None) -> str:
    return (estado or "nenhum").replace(" ", "-")


def _chip_estado(s: dict) -> str:
    if not s["estado"]:
        return '<span class="estado e-nenhum">sem estado</span>'
    desde = f' <span>desde {e(data_curta(s["desde"]))} · {e(ha_quanto(s["dias"]))}</span>' if s["desde"] else ""
    return f'<span class="estado e-{_classe(s["estado"])}">{e(s["estado"])}</span>{desde}'


def _chips_cuidado(s: dict) -> str:
    # 24/11/2026: faltava aqui o «esperando_resposta» (entrou a 23/11) — uma ficha só com pedidos
    # rebentava a página. E um sinal novo nunca deve derrubar a folha: usa-se `get`.
    rotulo = {
        "broto": "broto — ninguém viu nem contou ainda",
        "adormecida": "adormecida — quem a acorda?",
        "contestada": "contestada",
        "esperando_resposta": "esperando resposta — bateu à porta e ninguém abriu",
        "prova por juntar": "diz «verificado» e não traz prova — o selo por juntar",
    }
    return "".join(f'<span class="cuidado">{e(rotulo.get(c, c))}</span>' for c in s["cuidado"])


def _onde_texto(id_: str, onde: dict, fora: set | frozenset = frozenset()) -> str:
    o = onde.get(id_)
    if id_ in fora:
        return '<p class="onde">fica fora do mapa — por agora o mapa é só de Passos</p>'
    if not o:
        return '<p class="onde">no mapa: ainda falta saber onde fica</p>'
    if o["precisao"] == "aproximado":
        raio = o["raio_m"]
        tam = f"{raio / 1000:g} km".replace(".", ",") if raio >= 1000 else f"{raio} m"
        return f'<p class="onde">no mapa: por aqui, a uns {e(tam)} — o ponto exato ainda falta saber</p>'
    return '<p class="onde">no mapa: no ponto</p>'


LEIS = [
    ("Nunca quem falhou — só a coisa.", "Guarda-se o que falta e onde falta, não quem tem culpa."),
    ("Nunca quem contou.", "Sem nome, sem rosto, sem rasto. Quem contou, contou."),
    ("Mover é ligar, nunca apagar.", "Corrige-se acrescentando, com a data do lado. Nada se joga fora."),
    ("Com procedência.", "Todo dado diz de onde veio. Sem procedência não entra — nem um ponto no mapa."),
    ("Museu não é álbum.", "O difícil fica do lado do bonito. Num se escolhe só o que é de gosto."),
    ("Sem dono.", "A UAI é do povo de Passos, não de quem guarda."),
    ("Cada ficha tem data e estado.", "E sempre desde quando — porque o tempo também conta."),
]


def pagina_inicio(fichas: dict, hoje: dt.date, onde: dict | None = None, fora: set | frozenset = frozenset()) -> str:
    onde = onde or {}
    itens = []
    for id_, f in sorted(fichas.items(), key=lambda kv: kv[1]["lugar"]["nome"]):
        s = situacao(f, hoje)
        perg = f' · {s["perguntas"]} {"pergunta aberta" if s["perguntas"] == 1 else "perguntas abertas"}' if s["perguntas"] else ""
        itens.append(f"""<li><a class="cartao cor-{_classe(s["estado"])}" href="{e(id_)}.html" data-lugar="{e(id_)}">
<span class="ponto" aria-hidden="true"></span><div>
<h3>{e(f["lugar"]["nome"])}</h3><p class="ref">{e(f["lugar"].get("referencia", ""))}</p>
<div class="linha-estado">{_chip_estado(s)}{_chips_cuidado(s)}</div>
<p class="ref" style="margin-top:8px">{len(f["registos"])} registos{perg}{" · fora do mapa de Passos" if id_ in fora else "" if id_ in onde else " · ainda sem lugar no mapa"}</p></div></a></li>""")
    itens.append("""<li><a class="cartao vazio" href="deixar.html">
<span class="ponto" aria-hidden="true"></span><div>
<h3>A primeira história</h3><p class="ref">rua, praça, ponte, beira de rio — quem viveu é que conta</p>
<div class="linha-estado"><span class="estado">em branco</span> <span>é do povo — e ninguém escreve por ele</span></div></div></a></li>""")
    leis = "".join(f"<li><b>{e(a)}</b> {e(b)}</li>" for a, b in LEIS)
    jornadas = ""
    if JORNADAS_TRACADAS:
        js = "".join(
            f'<li class="jornada-texto"><h3>{e(j["nome"])}</h3><p class="ref">{len(j["paradas"])} paradas · {e(mapa.distancia(j["metros"]))} · {e(mapa.a_pe(j["minutos"]))}'
            f' · <a href="#" data-ver-jornada="{e(j["id"])}">ver no mapa</a></p><p>{e(j["convite"])}</p>'
            f'<p class="ref">{" → ".join(e(p["nome"]) for p in j["paradas"])}</p>'
            f'<p class="fonte">fonte: {e(j["fonte"]["descricao"])}</p></li>' for j in JORNADAS_TRACADAS)
        jornadas = (f'<h2>Jornadas</h2><p class="ref" style="margin-bottom:12px">Caminhadas por lugares que existem. O traço segue as ruas do mapa; '
                    f'na rua, vale o que os olhos virem.</p><ul class="jornadas">{js}</ul>')
    legenda = "".join(
        f'<li class="c-{k}"><svg viewBox="-10 -10 20 20" width="18" height="18" aria-hidden="true">'
        f'<circle r="9" fill="var(--c)"/><g fill="#fff">{mapa.ICONES[k]}</g></svg>{e(v)}</li>'
        for k, v in mapa.CATEGORIAS.items())
    corpo = f"""<p class="selo">UAI · Passos · {e(data_curta(hoje.isoformat()))}</p>
<h1>O que o povo <b>guardou</b>, e o que ainda <b>falta</b></h1>
<p class="sub">Cada canto com a sua data e o seu estado — e há quanto tempo tá assim. Sem senha, sem nome, sem cadastro: só o lugar e o dia.</p>
<nav class="nav"><a href="deixar.html">conta o que cê sabe</a><a href="acervo.html">as fotos guardadas</a></nav>
<h2>O que o povo guardou</h2>
<ul class="lugares">{"".join(itens)}</ul>
{jornadas}
<h2>O mapa</h2>
<p class="ref">O mapa é de Passos — a cidade é a missão de agora. O chão é o de toda a gente: bairros, córregos, matas, ruas e pontes do OpenStreetMap, o relevo do SRTM.
Um lugar da UAI só ganha um ponto quando há fonte para ele — se a fonte só diz «por ali», desenha-se uma mancha do tamanho da dúvida.</p>
<ul class="legenda">{legenda}</ul>
<p class="ref">Praças, rodoviária, exposição, igrejas… aparecem quando se aproxima. Ainda não são fichas: tocar num deles abre «contar uma história» já com o nome do lugar.</p>
<p class="ref">O chão é feito de <strong>quadradinhos de 10 metros</strong> — menos realista de propósito: o mapa é para achar o caminho, a cidade de verdade está lá fora. Cada <strong>pessoinha</strong> ao lado de um lugar da UAI é uma história contada ali. No botão das camadas há jeitos de ver: de cima ou inclinado, com mais ou menos coisa.</p>
<h2>As leis da casa</h2>
<details class="leis" open>
<summary>o que a casa guarda — e o que a casa não guarda</summary>
<ol>{leis}</ol>
</details>"""
    return pagina("UAI — Passos", corpo, "Uma biblioteca viva de Passos (MG): o que floresce, o que pede cuidado, o que ainda falta.")


def _regua(regs: list[dict], hoje: dt.date) -> str:
    datas = sorted({r["data"] for r in regs if r.get("data")}, key=lambda d: _dia(d))
    if not datas:
        return ""
    pontos = [(_dia(d), data_curta(d), False) for d in datas if _dia(d) != hoje]
    pontos.append((hoje, "hoje", True))
    a, b = pontos[0][0], pontos[-1][0]
    span = max(1, (b - a).days)
    marcos = []
    for d, rot, h in pontos:
        x = 4 + 92 * (d - a).days / span
        marcos.append(f'<span class="marco{" hoje" if h else ""}" style="left:{x:.1f}%"><span>{e(rot)}</span></span>')
    return f'<div class="regua" aria-hidden="true">{"".join(marcos)}</div>'


def pagina_lugar(id_: str, f: dict, hoje: dt.date, avisos: list[str], onde: dict | None = None,
                 fora: set | frozenset = frozenset()) -> str:
    onde = onde or {}
    s = situacao(f, hoje)
    selos = carimbos(f)
    # 24/11/2026: uma régua só. A ficha do lugar tinha a sua PRÓPRIA cópia deste desenho —
    # e foi por uma função gémea que o selo «verificado» escapou à regra da prova.
    # O desenho dos registos vive num sítio só: `_registo_li`.
    regs = [_registo_li(r, i + 1) for i, r in enumerate(f["registos"])]
    av = ""
    if avisos:
        av = '<div class="avisos">O que esta ficha ainda pede:<ul>' + "".join(f"<li>{e(a)}</li>" for a in avisos) + "</ul></div>"
    o = onde.get(id_)
    fonte_onde = ""
    if o:
        link = f' · <a href="{e(o["fonte"]["url"])}" rel="noopener">ver</a>' if o["fonte"].get("url") else ""
        fonte_onde = f'<p class="fonte">o ponto no mapa: {e(o["fonte"]["descricao"])}{link}</p>'
    ver = f' · <a href="#" data-ver-no-mapa="{e(id_)}">ver no mapa</a>' if o and id_ not in fora else ""
    corpo = f"""<p class="selo"><a href="index.html">UAI · Passos</a></p>
<h1>{e(f["lugar"]["nome"])}</h1>
<p class="ref">{e(f["lugar"].get("referencia", ""))}{ver}</p>
<div class="linha-estado">{_chip_estado(s)}{_chips_cuidado(s)}</div>
{_regua(f["registos"], hoje)}
<h2>O que já contaram</h2>
<p class="ref" style="margin:-4px 0 14px">na ordem em que chegaram — nada se apaga</p>
<ol class="registos">{"".join(regs)}</ol>
{av}
<nav class="nav"><a href="deixar.html?lugar={e(id_)}">acrescentar a esta ficha</a></nav>
<h2>Onde fica, no mapa</h2>
{_onde_texto(id_, onde, fora)}{fonte_onde}
<h2>Carimbo</h2>
<p class="ref">Cada registo sela o anterior (SHA-256). Se alguém mudar um registo antigo, este número muda.</p>
<p class="carimbo">{e(selos[-1])}</p>"""
    return pagina(f'{f["lugar"]["nome"]} — UAI', corpo, f'{f["lugar"]["nome"]}: estado, data e procedência.', foco=id_ if o and id_ not in fora else "")


def pagina_acervo(fotos: dict) -> str:
    figs = []
    for nome, it in fotos.items():
        titulo = re.sub(r"^File:", "", it.get("titulo", nome))
        titulo = re.sub(r"\.(jpe?g|png)$", "", titulo, flags=re.I)
        lic = it.get("licenca", "licença a verificar")
        link_lic = licenca_url(lic)
        lic_txt = f'<a href="{e(link_lic)}" rel="noopener">{e(lic)}</a>' if link_lic else e(lic)
        origem = origem_url(it)
        figs.append(f"""<figure><a href="{e(it.get("url", origem))}" rel="noopener"><img src="acervo/{e(nome)}" alt="{e(titulo)}" loading="lazy"></a>
<figcaption><b>{e(titulo)}</b> · {e(it.get("autor", "autor desconhecido"))} · {lic_txt} · {e((it.get("data") or "")[:10])} · <a href="{e(origem)}" rel="noopener">fonte</a></figcaption></figure>""")
    corpo = f"""<p class="selo"><a href="index.html">UAI · Passos</a></p>
<h1>As fotos <b>guardadas</b></h1>
<p class="sub">{len(fotos)} fotografias de licença livre. Cada uma leva o autor, a licença (com link) e a fonte — licença livre não dispensa o crédito.
As fotos antigas de família e do Centro de Memória não se copiam: pedem-se.</p>
<div class="acervo">{"".join(figs)}</div>"""
    return pagina("As fotos guardadas — UAI", corpo, "Fotografias de Passos com autor, licença e origem.")


def pagina_creditos(fotos: dict) -> str:
    """A página de créditos — a UAI diz o que deve a quem (24/11/2026).

    O MIT cobre só o código. As fotos têm as suas licenças (CC), o mapa a sua
    (ODbL na base, Terrain Tiles no relevo) e as letras a delas (SIL OFL 1.1).
    Cada um com o seu autor e o seu link — a beleza da atribuição não substitui
    a atribuição.
    """
    itens = []
    for nome, it in fotos.items():
        titulo = re.sub(r"^File:", "", it.get("titulo", nome))
        lic = it.get("licenca", "licença a verificar")
        link_lic = licenca_url(lic)
        lic_txt = f'<a href="{e(link_lic)}" rel="noopener">{e(lic)}</a>' if link_lic else e(lic)
        origem = origem_url(it)
        itens.append(f"""<li><b>{e(titulo)}</b> — {e(it.get("autor", "autor desconhecido"))} · {lic_txt} · <a href="{e(origem)}" rel="noopener">fonte</a></li>""")
    corpo = f"""<p class="selo"><a href="index.html">UAI · Passos</a></p>
<h1>Créditos</h1>
<p class="sub">O que a UAI deve a quem — e a quem, exactamente. O código é MIT; o resto tem dono, e o dono tem nome.</p>
<h2>As fotografias</h2>
<p class="ref">As {len(fotos)} fotos do acervo são de licença livre (Wikimedia Commons). Cada uma leva o autor, a licença com link e a página de origem — a Creative Commons pede o crédito e o link, e a UAI não os dispensa.</p>
<ul class="creditos">{"".join(itens)}</ul>
<h2>O mapa</h2>
<p class="ref">A base geográfica é do OpenStreetMap: © <a href="https://www.openstreetmap.org/copyright" rel="noopener">colaboradores do OpenStreetMap</a>, distribuída sob a licença <a href="https://opendatacommons.org/licenses/odbl/" rel="noopener">ODbL</a> (o ficheiro <code>mapa/regiao.json</code> é uma base derivada, e viaja sob ODbL).</p>
<p class="ref">O relevo vem dos <a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" rel="noopener">Terrain Tiles</a> (Mapzen / AWS Open Data) — inclui dados de terreno GMTED2010 e SRTM, cortesia do <a href="https://www.usgs.gov/" rel="noopener">U.S. Geological Survey</a>.</p>
<h2>As letras</h2>
<p class="ref">Fraunces, Archivo e JetBrains Mono — <a href="https://openfontlicense.org/" rel="noopener">SIL Open Font License 1.1</a>. O texto da licença viaja junto das letras (no ficheiro <code>OFL.txt</code>).</p>
<h2>O código</h2>
<p class="ref">O motor da UAI é <a href="LICENSE">MIT</a> — «Copyright (c) 2026 Maestro Cuca · Passos, Minas Gerais». A ética, essa, não é MIT: está em <code>LEI-DA-CASA.md</code>.</p>"""
    return pagina("Créditos — UAI", corpo, "O que a UAI deve a quem: fotos (CC), mapa (ODbL), relevo (Terrain Tiles/USGS), letras (OFL) e código (MIT).")


def _registo_li(r: dict, i: int, fotos: dict | None = None) -> str:
    """Um registo, como aparece na folha — o mesmo desenho para lugares e para gente.

    24/11/2026 (achado do Chagas): **um selo «verificado» sem prova não se mostra.**
    Se o registo diz «verificado» e não traz prova, o selo é rebaixado a «prova por
    juntar» — a ficha conta o que sabe, e não empresta autoridade que não tem.

    A decisão é a MESMA dos outros leitores: a régua (`regua.avaliar`). Uma foto-
    fantasma (nome que o acervo não tem) não segura o selo.
    """
    fotos = fotos_do_acervo() if fotos is None else fotos
    quando = data_curta(r["data"]) if r.get("data") else r.get("epoca", "")
    fonte = r["fonte"]
    extra = ""
    if fonte.get("url"):
        extra += f' · <a href="{e(fonte["url"])}" rel="noopener">ver a fonte</a>'
    if fonte.get("foto"):
        extra += f' · <a href="acervo/{e(fonte["foto"])}">a foto</a>'
    estado = f' <span class="estado e-{_classe(r["estado"])}">{e(r["estado"])}</span>' if r.get("estado") else ""
    emprestado = regua.avaliar(r, fotos)["verificado_sem_prova"]
    rotulo = "prova por juntar" if emprestado else r["tipo"]
    titulo = ("diz «verificado», mas não traz prova: nem link, nem foto no acervo — o selo num se empresta"
              if emprestado else TIPOS[r["tipo"]])
    tipo = "falta" if emprestado else r["tipo"].replace(" ", "-")
    aviso = ' <b class="prova-por-juntar">prova por juntar</b>' if emprestado else ""
    return f"""<li class="registo t-{e(tipo)}" id="r{i}">
<div class="topo"><span class="tipo t-{e(tipo)}" title="{e(titulo)}">{e(rotulo)}</span>
<span class="quando">{e(quando)}</span>{estado}</div>
<p>{e(r["texto"])}</p>
<p class="fonte">fonte: {e(fonte["descricao"])}{extra}{aviso} · entrou na UAI a {e(data_curta(r["entrou"]))}</p></li>"""


def pagina_pessoa(id_: str, f: dict, hoje: dt.date, avisos: list[str]) -> str:
    """A ficha de uma pessoa (23/11/2026) — a segunda metade da UAI.

    O que a distingue de um lugar, e não é pouco:
      · **a autorização aparece à vista** — o nome de quem autorizou, o dia e o modo. Quem lê sabe
        porque é que esta pessoa está aqui: porque disse que sim;
      · **o nome é o que ela usa** — e se ela se apresentar de outra maneira, é essa que vem primeiro;
      · **quem sai, sai** — a ficha ganha «retirada» e deixa de aparecer. *Os lugares não têm esse
        direito; as pessoas têm, e é a única excepção à lei de não apagar.*
    """
    p = f["pessoa"]
    s = situacao(f, hoje)
    selos = carimbos(f)  # 24/11/2026 — a ficha de pessoa também traz o seu carimbo
    regs = "".join(_registo_li(r, i + 1) for i, r in enumerate(f["registos"]))
    av = ""
    if avisos:
        av = '<div class="avisos">O que esta ficha ainda pede:<ul>' + "".join(f"<li>{e(a)}</li>" for a in avisos) + "</ul></div>"
    a = f.get("autorizou", {})
    autorizou = (f'<p class="fonte">Está nesta casa porque <b>{e(a.get("por", ""))}</b> autorizou, '
                 f'{e(data_curta(str(a.get("quando", ""))))} — {e(a.get("como", ""))}.</p>') if a else ""
    como_se_chama = ""
    if p.get("se_chama") and p["se_chama"] != p.get("nome"):
        como_se_chama = f'<p class="ref">como se chama: <b>{e(p["se_chama"])}</b></p>'
    oficio = f'<p class="ref">{e(p["oficio"])}</p>' if p.get("oficio") else ""
    onde = f'<p class="ref">onde vive: {e(p["onde_vive"])}</p>' if p.get("onde_vive") else ""
    nota = f'<p class="ref">{e(p["referencia"])}</p>' if p.get("referencia") else ""

    if not de_pe(f):
        r = f.get("retirada", {})
        corpo = f"""<p class="selo"><a href="gente.html">UAI · gente</a></p>
<h1>{e(p.get("nome", ""))}</h1>
<div class="avisos"><b>Esta pessoa pediu para sair da UAI</b>
<ul><li>pedido em {e(data_curta(str(r.get("quando", ""))))} — por {e(r.get("pedido_por", ""))}</li>
<li>a ficha não se apagou: ficou guardada, e não aparece no sítio. <b>Quem sai, sai.</b></li></ul></div>
{autorizou}
<p class="ref">Se esta pessoa quiser voltar, volta — e a retirada fica ao lado, para a história não ser reescrita.</p>
<h2>Carimbo</h2>
<p class="ref">Cada registo sela o anterior (SHA-256). Se alguém mudar um registo antigo, este número muda.</p>
<p class="carimbo">{e(selos[-1])}</p>"""
        return pagina(f'{p.get("nome", "")} — UAI', corpo,
                      f'{p.get("nome", "")}: ficha retirada a pedido.')

    corpo = f"""<p class="selo"><a href="gente.html">UAI · gente</a></p>
<h1>{e(p.get("nome", ""))}</h1>
{como_se_chama}{oficio}{onde}
<div class="linha-estado">{_chip_estado(s)}{_chips_cuidado(s)}</div>
{_regua(f["registos"], hoje)}
<h2>O que já contaram</h2>
<p class="ref" style="margin:-4px 0 14px">na ordem em que chegaram — nada se apaga</p>
<ol class="registos">{regs}</ol>
{av}
{autorizou}{nota}
<p class="ref">Uma pessoa entra na UAI com a sua palavra — e sai com a sua palavra. Não é um lugar,
e por isso não é tratada como um lugar.</p>
<h2>Carimbo</h2>
<p class="ref">Cada registo sela o anterior (SHA-256). Se alguém mudar um registo antigo, este número muda.</p>
<p class="carimbo">{e(selos[-1])}</p>"""
    return pagina(f'{p.get("nome", "")} — UAI', corpo,
                  f'{p.get("nome", "")}: quem é, o que faz, e com que autorização entrou.')


def pagina_gente(gente: dict) -> str:
    """A lista das pessoas que estão de pé — quem entrou, e com a autorização dita ao lado."""
    vivas = {i: f for i, f in sorted(gente.items(), key=lambda kv: nome_de(kv[1])) if de_pe(f)}
    retiradas = [i for i, f in gente.items() if not de_pe(f)]
    if not vivas and not retiradas:
        corpo = """<p class="selo"><a href="index.html">UAI · Passos</a></p>
<h1>A <b>gente</b> da UAI</h1>
<p class="sub">Esta metade da UAI ainda tá vazia. A primeira pessoa a entrar entra pela própria palavra,
com o nome que usa — não com o que os papéis dizem.</p>
<p class="ref">A UAI guarda lugares sem dono. Guarda pessoas só com autorização, com o dia escrito,
e com o direito de sair. É a diferença entre um arquivo e uma colecção.</p>
<nav class="nav"><a href="index.html">voltar ao mapa</a></nav>"""
        return pagina("A gente da UAI — Passos", corpo, "As pessoas da UAI, com autorização à vista.")

    itens = "".join(
        f'<li><a href="{e(i)}.html">{e(nome_de(f))}</a>'
        f'{" — " + e(f["pessoa"].get("oficio", "")) if f["pessoa"].get("oficio") else ""}'
        f'<br><span class="ref">entrou com a palavra de {e(f.get("autorizou", {}).get("por", ""))}, '
        f'{e(data_curta(str(f.get("autorizou", {}).get("quando", ""))))}'
        f' — {e(f.get("autorizou", {}).get("como", ""))}</span></li>'
        for i, f in vivas.items())
    nota_retiradas = (f'<p class="ref">{len(retiradas)} ficha(s) retirada(s) a pedido — guardadas, '
                      f'e fora do sítio. Quem sai, sai.</p>') if retiradas else ""
    corpo = f"""<p class="selo"><a href="index.html">UAI · Passos</a></p>
<h1>A <b>gente</b> da UAI</h1>
<p class="sub">Num são verbetes: são gente. Cada uma tá aqui pruquê disse que sim — e cada uma
pode pedir pra sair, sem precisar explicar pruquê.</p>
<ul class="lista-gente">{itens}</ul>
{nota_retiradas}
<p class="ref">A UAI guarda os lugares sem dono; guarda as pessoas com autorização à vista.
O nome de quem contou uma história continua, esse, proibido de entrar.</p>
<nav class="nav"><a href="index.html">voltar ao mapa</a></nav>"""
    return pagina("A gente da UAI — Passos", corpo, "As pessoas da UAI, com autorização à vista.")


def pagina_deixar(fichas: dict) -> str:
    opcoes = "".join(f'<option value="{e(i)}">{e(f["lugar"]["nome"])}</option>' for i, f in sorted(fichas.items()))
    tipos = "".join(f'<option value="{e(t)}">{e(t)} — {e(d)}</option>' for t, d in TIPOS.items() if t != "contesta")
    estados = "".join(f'<option value="{e(s)}">{e(s)}</option>' for s in ESTADOS)
    dados = json.dumps({"lugares": [{"id": i, "nome": f["lugar"]["nome"]} for i, f in sorted(fichas.items())]},
                       ensure_ascii=False).replace("</", "<\\/")
    corpo = f"""<p class="selo"><a href="index.html">UAI · Passos</a></p>
<h1>Conta <b>o que cê sabe</b></h1>
<p class="sub">Uma lembrança, uma falta, uma correção — de uma praça, uma rua, uma ponte. Sem nome, sem conta, sem senha.
Nada sai daqui sem cê apertar «mandar».</p>
<section class="por-voz" aria-label="Contar por voz ou por telefone">
<h2>Num quer escrever? Pode <b>falar</b>, sô.</h2>
<p><button type="button" class="botao ouvir-tudo" id="ouvir-tudo">ouvir o que fazer</button></p>
<p class="grande">Mande um <b>áudio</b> para o WhatsApp da UAI:<br>
<a class="telefone" href="{_zap(quem=carregar_contato())}">{e(telefone_bonito(carregar_contato()['whatsapp']))}</a></p>
<p class="ref">Quem recebe ouve a sua voz, passa pro papel, e a história entra com a data — e sem o
nome de quem contou. Se precisar, peça a alguém pra ler esta página em voz alta:
o botão «ouvir o que fazer» faz isso, e o cartão de bolso (com o código de barras quadrado)
é pra levar impresso no bolso.</p>
</section>
<section class="conversa" id="conversa" hidden aria-label="Conversa com a UAI">
<div class="log" aria-live="polite"></div>
<div class="opcoes"></div>
<form class="responder" autocomplete="off">
<label class="sr" for="resposta">A sua resposta</label>
<textarea id="resposta" rows="2"></textarea>
<div class="botoes-resposta">
<button type="button" class="mic" hidden aria-pressed="false" title="falar em vez de escrever (o seu navegador transcreve a voz)"><span aria-hidden="true">🎙</span> falar</button>
<button type="submit">responder</button>
</div>
</form>
<div class="fim" hidden>
<p class="ref nota-destino" id="destino"></p>
<a class="zap botao" href="#" target="_blank" rel="noopener">mandar pelo WhatsApp</a>
<a class="email botao secundario" href="#" hidden>mandar por e-mail</a>
<button type="button" class="copiar secundario">copiar</button>
<button type="button" class="de-novo secundario">contar outra</button>
<details><summary>ver a ficha técnica</summary><pre class="tecnica"></pre></details>
</div>
<p class="ref nota-voz">O microfone usa o reconhecimento de voz do seu navegador — no Chrome, o áudio passa pelo serviço do Google.
Se preferir, escreva.</p>
</section>
<script type="application/json" id="conversa-dados">{dados}</script>
<details class="formulario" id="formulario" open><summary>prefiro escrever no formulário</summary>
<form id="f" autocomplete="off">
<label>Lugar
<select name="lugar"><option value="">um lugar novo…</option>{opcoes}</select></label>
<label id="novo">Nome do lugar novo (como o povo o conhece)
<input name="nome" placeholder="ex.: Ponte Tristão da Cunha"></label>
<label>O que é
<select name="tipo">{tipos}</select></label>
<label>O que aconteceu, o que falta, o que se vê
<textarea name="texto" required></textarea></label>
<label>Quando (uma data, um ano — ou a época, em palavras)
<input name="quando" placeholder="ex.: 1987, ou «quando eu era pequeno»"></label>
<label>De onde vem — a fonte (obrigatória)
<input name="fonte" required placeholder="ex.: vi no local hoje; minha avó contava; jornal de 1962, pág. 3"></label>
<label>Como está, se souber
<select name="estado"><option value="">não sei dizer</option>{estados}</select></label>
<button type="submit">montar a ficha</button>
</form>
<div id="saida" hidden>
<h2>A sua ficha</h2>
<p class="sub">Confira: não há nome de ninguém? Então copie e mande a quem guarda a UAI.</p>
<pre id="json"></pre>
<button type="button" class="secundario" id="copiar">copiar</button>
</div>
</details>
<script>
const f = document.getElementById("f"), novo = document.getElementById("novo");
const q = new URLSearchParams(location.search);
if (q.get("lugar")) f.lugar.value = q.get("lugar");
else if (q.get("nome")) f.nome.value = q.get("nome").slice(0, 120);
const mostrar = () => (novo.hidden = !!f.lugar.value);
f.lugar.addEventListener("change", mostrar); mostrar();
f.addEventListener("submit", (ev) => {{
  ev.preventDefault();
  const hoje = new Date().toISOString().slice(0, 10);
  const quando = f.quando.value.trim();
  const reg = {{ tipo: f.tipo.value, texto: f.texto.value.trim() }};
  if (/^\\d{{4}}(-\\d{{2}}(-\\d{{2}})?)?$/.test(quando)) reg.data = quando; else reg.epoca = quando || "sem data dita";
  reg.entrou = hoje;
  if (f.estado.value) reg.estado = f.estado.value;
  reg.fonte = {{ descricao: f.fonte.value.trim() }};
  const ficha = f.lugar.value ? {{ acrescentar_a: f.lugar.value, registo: reg }} : {{ lugar: {{ nome: f.nome.value.trim() }}, registos: [reg] }};
  document.getElementById("json").textContent = JSON.stringify(ficha, null, 2);
  document.getElementById("saida").hidden = false;
}});
document.getElementById("copiar").addEventListener("click", async (ev) => {{
  try {{ await navigator.clipboard.writeText(document.getElementById("json").textContent); ev.target.textContent = "copiado"; }}
  catch {{ ev.target.textContent = "selecione o texto e copie"; }}
}});
</script>"""
    return pagina("Conta o que cê sabe — UAI", corpo, "Conte o que cê sabe de um lugar de Passos: falando, escrevendo ou mandando um áudio.",
                  scripts=("contato.js", "conversa.js"))


def construir(saida: Path, hoje: dt.date | None = None) -> list[str]:
    hoje = hoje or dt.date.today()
    fichas, fotos = carregar(), fotos_do_acervo()
    gente = carregar_gente()  # a segunda metade: as pessoas (23/11/2026)
    regiao, onde = mapa.carregar_regiao(), mapa.carregar_onde()
    problemas, avisos_por = [], {}
    for id_, f in fichas.items():
        erros, avisos = validar_ficha(id_, f, fotos, fichas=fichas, gente=gente)
        erros += nunca_apagar(versao_anterior(id_), f)
        problemas += [f"{id_}: {x}" for x in erros]
        avisos_por[id_] = avisos
    problemas += validar_onde(onde, fichas, regiao["moldura"])
    # a segunda metade (23/11/2026): as pessoas. Uma ficha retirada continua guardada, mas
    # não bloqueia a construção do sítio — quem sai, sai.
    avisos_gente = {}
    for id_, f in gente.items():
        if not de_pe(f):
            # quem saiu, saiu — mas o carimbo da ficha retirada também tem de fechar (24/11/2026)
            problemas += [f"{id_}: {x}" for x in carimbo_quebrado(f)]
            continue
        erros, avisos = validar_ficha(id_, f, fotos, fichas=fichas, gente=gente)
        erros += nunca_apagar(versao_anterior(id_, pasta="gente"), f)
        problemas += [f"{id_}: {x}" for x in erros]
        avisos_gente[id_] = avisos
    lugares = lugares_no_mapa(fichas, onde, regiao["moldura"], hoje)
    jornadas, erros_j = mapa.tracar_jornadas(mapa.carregar_jornadas(), regiao, {l["id"]: l for l in lugares})
    problemas += erros_j
    if problemas:
        return problemas
    global VERSAO, JORNADAS_TRACADAS
    JORNADAS_TRACADAS = jornadas
    chao = mapa.chao(regiao)
    chao_bin = zlib.compress(chao["dados"], 9)
    hq_bin = zlib.compress(json.dumps(mapa.tracos(regiao, chao), separators=(",", ":")).encode(), 9)
    svg = mapa.svg(regiao, lugares, jornadas, chao)
    h = hashlib.sha256(svg.encode() + chao_bin + hq_bin)
    for f in sorted(ESTATICO.rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    VERSAO = h.hexdigest()[:10]
    if saida.exists():
        shutil.rmtree(saida)
    (saida / "acervo").mkdir(parents=True)
    fora = {id_ for id_, o in onde.items() if not no_mapa(o, regiao["moldura"])}
    (saida / "index.html").write_text(pagina_inicio(fichas, hoje, onde, fora), encoding="utf-8")
    for id_, f in fichas.items():
        (saida / f"{id_}.html").write_text(pagina_lugar(id_, f, hoje, avisos_por[id_], onde, fora), encoding="utf-8")
    (saida / "gente.html").write_text(pagina_gente(gente), encoding="utf-8")
    (saida / "gente").mkdir(parents=True, exist_ok=True)
    for id_, f in gente.items():
        (saida / "gente" / f"{id_}.html").write_text(
            pagina_pessoa(id_, f, hoje, avisos_gente.get(id_, [])), encoding="utf-8")
    (saida / "acervo.html").write_text(pagina_acervo(fotos), encoding="utf-8")
    (saida / "deixar.html").write_text(pagina_deixar(fichas), encoding="utf-8")
    (saida / "creditos.html").write_text(pagina_creditos(fotos), encoding="utf-8")
    mesa = pagina_curador(fichas, onde, avisos_por, hoje, regiao["moldura"], regiao, gente=gente).replace(
        "<head>", '<head>\n<meta name="robots" content="noindex">')
    (saida / "curador.html").write_text(mesa, encoding="utf-8")
    # o cartão de bolso: quem não vê precisa de um caminho que não seja um ecrã (23/11/2026)
    (saida / "cartao.html").write_text(pagina_cartao(), encoding="utf-8")
    (saida / "mapa.svg").write_text(svg, encoding="utf-8")
    (saida / "chao.bin").write_bytes(chao_bin)
    (saida / "hq.bin").write_bytes(hq_bin)
    shutil.copy2(RAIZ / "mapa" / "relevo.jpg", saida / "relevo.jpg")
    shutil.copytree(ESTATICO, saida, dirs_exist_ok=True)
    # O destinatário das histórias vai declarado no site (23/11/2026): um sítio só, e à vista.
    (saida / "contato.js").write_text(
        "window.UAI_CONTATO = " + json.dumps(carregar_contato(), ensure_ascii=False) + ";\n",
        encoding="utf-8")
    for nome in fotos:
        if (ACERVO / nome).exists():
            shutil.copy2(ACERVO / nome, saida / "acervo" / nome)
    return []


def slug(nome: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def ler_entrega(texto: str) -> dict:
    """Aceita a ficha em JSON — ou a mensagem inteira do WhatsApp, com a «(ficha: {…})» no fim."""
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        i = texto.find("(ficha: ")
        if i < 0:
            raise SystemExit("não encontrei a ficha nesta mensagem")
        return json.JSONDecoder().raw_decode(texto[i + len("(ficha: "):])[0]


def nome_de(ficha: dict) -> str:
    """O nome da coisa — do lugar ou da pessoa. Uma casa com duas metades precisa de um só chamado."""
    if "pessoa" in ficha:
        return str(ficha["pessoa"].get("nome", ""))
    return str(ficha.get("lugar", {}).get("nome", ""))


def pasta_de(ficha: dict) -> Path:
    """Onde é que esta ficha mora: `gente/` ou `fichas/` (23/11/2026)."""
    return GENTE if "pessoa" in ficha else FICHAS


def receber(entrega: dict, pasta: Path | None = None) -> tuple[str, list[str]]:
    """O que vem do «deixar uma ficha»: acrescenta no fim, nunca no meio.
    Devolve (id, erros); só grava se a ficha resultante passar nas leis."""
    if "acrescentar_a" in entrega:
        id_ = entrega["acrescentar_a"]
        # procura onde a ficha vive: na pasta que lhe disserem, ou nas duas metades da casa
        candidatos = ([pasta] if pasta else []) + [FICHAS, GENTE]
        caminho = next((p / f"{id_}.json" for p in candidatos if (p / f"{id_}.json").exists()), None)
        if caminho is None:
            return id_, [f"não há ficha «{id_}»"]
        ficha = json.loads(caminho.read_text(encoding="utf-8"))
        # 24/11/2026 — antes de acrescentar, o carimbo que a ficha já traz tem de fechar.
        # Se não fechar, um registo antigo foi mudado: não se sela por cima (isso lavaria a mudança).
        erros_carimbo = carimbo_quebrado(ficha)
        if erros_carimbo:
            return id_, erros_carimbo
        ficha["registos"].append(entrega.get("registo"))
    else:
        if "pessoa" in entrega:
            ficha = {"pessoa": entrega.get("pessoa", {}),
                     "autorizou": entrega.get("autorizou", {}),
                     "registos": entrega.get("registos", [])}
            if entrega.get("retirada"):
                ficha["retirada"] = entrega["retirada"]
        else:
            ficha = {"lugar": entrega.get("lugar", {}), "registos": entrega.get("registos", [])}
        id_ = slug(nome_de(ficha))
        pasta = pasta or pasta_de(ficha)
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{id_}.json"
        if caminho.exists():
            return id_, [f"já existe a ficha «{id_}» — acrescente a ela"]
    pasta = pasta or pasta_de(ficha)
    # 24/11/2026 — a ficha leva o seu próprio carimbo: sela-se já com os registos que vai gravar.
    # O `validar_ficha` abaixo volta a verificar o carimbo (agora com a corrente nova).
    selar(ficha)
    erros, _ = validar_ficha(id_, ficha)
    # 24/11/2026 — o crivo da porta julga só o que ENTRA. Um selo emprestado que já estava
    # na ficha não tem de travar a chegada de um registo novo dele: o passado trata-se
    # rebaixando o selo (ver `_registo_li`), não fechando a porta a quem vem depois.
    novos = [entrega["registo"]] if "acrescentar_a" in entrega else list(ficha.get("registos", []))
    if novos:
        # atenção à ordem: a régua devolve (erros, avisos) — os erros vêm PRIMEIRO
        erros_porta, _avisos_porta = validar_ficha(id_, {**ficha, "registos": novos}, na_porta=True)
        erros += [x for x in erros_porta if "prova por juntar" in x]
    if not erros:
        caminho.write_text(json.dumps(ficha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return id_, erros


# ───────────────────────── a mesa do curador (23/11/2026) ─────────────────────────
#
# Nasceu de um achado dos dezoito: a curadoria era feita «às cegas, por comando». Não havia fila,
# nem estado pendente, nem recusa registada — o `receber()` gravava directo se a ficha passasse.
# Aqui nasce o que faltava: as entregas esperam em `entregas/`, e a mesa mostra-as com ✓/✗ antes
# de qualquer decisão.

ENTREGAS = RAIZ / "entregas"


def _entregas_pendentes() -> list[Path]:
    """Os ficheiros à espera de decisão — por ordem de chegada (o mais antigo primeiro)."""
    if not ENTREGAS.is_dir():
        return []
    return sorted((f for f in ENTREGAS.iterdir() if f.is_file() and f.suffix in (".json", ".txt")),
                  key=lambda f: f.stat().st_mtime)


def prever_entrega(entrega: dict, pasta: Path | None = None,
                   fotos: dict | None = None) -> tuple[str, list[str], list[str]]:
    """Valida uma entrega SEM a gravar. Devolve (id, erros, avisos).

    É isto que a mesa mostra antes de o curador decidir: a mesma régua do `receber`, mas em seco.
    """
    pasta = pasta or FICHAS
    if fotos is None:
        fotos = fotos_do_acervo()
    if "acrescentar_a" in entrega:
        id_ = entrega["acrescentar_a"]
        caminho = pasta / f"{id_}.json"
        if not caminho.exists():
            return id_, [f"não há ficha «{id_}»"], []
        antiga = json.loads(caminho.read_text(encoding="utf-8"))
        nova = json.loads(caminho.read_text(encoding="utf-8"))
        nova["registos"] = antiga["registos"] + [entrega.get("registo")]
        # o carimbo antigo não se leva para a previsão: a corrente vai ser outra. Mas o carimbo
        # que a ficha já traz tem de fechar — é a lei «nada se apaga» a falar sozinha, sem git.
        nova.pop("carimbos", None)
        nova.pop("selo_retirada", None)
    else:
        nova = {"lugar": entrega.get("lugar", {}), "registos": entrega.get("registos", [])}
        antiga = None
        id_ = slug(str(nova["lugar"].get("nome", "")))
        if (pasta / f"{id_}.json").exists():
            return id_, [f"já existe a ficha «{id_}» — acrescente a ela"], []
    erros, avisos = validar_ficha(id_, nova, fotos)
    if antiga is not None:
        erros = list(erros) + carimbo_quebrado(antiga) + nunca_apagar(antiga, nova)
    return id_, list(erros), list(avisos)


def conta_do_acervo(fichas: dict, hoje: dt.date) -> dict:
    """Os números que o guardião deve ver — todos saem do que o motor já calcula."""
    sit = {id_: situacao(f, hoje) for id_, f in fichas.items()}
    return {
        "adormecidas": sorted([(i, s["parada_ha"]) for i, s in sit.items()
                              if s.get("estado_da_ficha") == "adormeceu"],
                              key=lambda x: -x[1]),
        "brotos": [i for i, s in sit.items() if "broto" in s["cuidado"]],
        "contestadas": [i for i, s in sit.items() if "contestada" in s["cuidado"]],
        "sem_estado": [i for i, s in sit.items() if not s["estado"]],
        "perguntas_abertas": sum(s["perguntas"] for s in sit.values()),
        "entradas": {i: s["ultima_entrada"] for i, s in sit.items()},
        "sit": sit,
    }


def pagina_curador(fichas: dict, onde: dict, avisos_por: dict, hoje: dt.date,
                   moldura: dict, regiao: dict, gente: dict | None = None) -> str:
    """A mesa do guardião: os números, o acervo, o silêncio e a fila de entregas.

    Página local, de trabalho — não é para o povo. Daí o `noindex` e a faixa no topo.
    """
    c = conta_do_acervo(fichas, hoje)
    fora = {id_ for id_, o in onde.items() if not no_mapa(o, moldura)}
    sem_ponto = sorted(set(fichas) - set(onde))
    gente = gente or {}
    de_pe_g = {i: f for i, f in gente.items() if de_pe(f)}
    retiradas = {i: f for i, f in gente.items() if not de_pe(f)}
    linhas_gente = "".join(
        f'<tr><td><a href="gente/{e(i)}.html">{e(nome_de(f))}</a></td>'
        f'<td>{e(f.get("autorizou", {}).get("por", ""))}</td>'
        f'<td>{e(str(f.get("autorizou", {}).get("quando", "")))}</td>'
        f'<td>{e(f.get("autorizou", {}).get("como", ""))}</td>'
        f'<td>{len(f.get("registos", []))}</td></tr>'
        for i, f in sorted(de_pe_g.items(), key=lambda kv: nome_de(kv[1])))
    bloco_gente = (f'<h2>A gente ({len(de_pe_g)})</h2>'
                   f'<table><thead><tr><th>pessoa</th><th>autorizou</th><th>quando</th><th>como</th>'
                   f'<th>registos</th></tr></thead><tbody>{linhas_gente}</tbody></table>'
                   + (f'<p class="ref">{len(retiradas)} retirada(s) a pedido — guardadas, fora do sítio.</p>'
                      if retiradas else "")) if (de_pe_g or retiradas) else ""
    cobertura = len(fichas) - len(fora) - len(sem_ponto)

    def num(n, t, serve):
        return (f'<div class="cartao-num"><b>{n}</b><span>{e(t)}</span>'
                f'<i>{e(serve)}</i></div>')

    numeros = "".join([
        num(len(c["adormecidas"]), "adormecidas", "sem registo novo há 90+ dias — acordar ou arquivar"),
        num(len(c["brotos"]), "brotos", "só leituras: mandem olhos e pés"),
        num(len(c["contestadas"]), "contestadas", "duas versões em conflito — mediar já"),
        num(c["perguntas_abertas"], "perguntas abertas", "o que o povo ainda não respondeu"),
        num(f"{cobertura}/{len(fichas)}", "no mapa", "cobertura: impede a UAI de virar lista"),
        num(len(_entregas_pendentes()), "na fila", "entregas à espera de decisão"),
    ])

    linhas = []
    for id_, f in sorted(fichas.items(), key=lambda kv: -c["sit"][kv[0]]["parada_ha"]):
        s = c["sit"][id_]
        estado = s["estado"] or "—"
        cuidado = " · ".join(s["cuidado"]) or "—"
        trav = "não" if id_ in sem_ponto else ("fora" if id_ in fora else "sim")
        avisos = len(avisos_por.get(id_, []))
        linhas.append(
            f'<tr><td><a href="{e(id_)}.html">{e(f["lugar"]["nome"])}</a></td>'
            f'<td>{e(estado)}</td><td class="n">{s["parada_ha"]}</td><td>{e(cuidado)}</td>'
            f'<td class="n">{len(f["registos"])}</td><td class="n">{s["perguntas"]}</td>'
            f'<td>{trav}</td><td class="n">{avisos or ""}</td></tr>')
    tabela = ("<table><thead><tr><th>ficha</th><th>estado</th><th>dias parada</th><th>cuidado</th>"
              "<th>registos</th><th>perguntas</th><th>no mapa</th><th>avisos</th></tr></thead>"
              f"<tbody>{''.join(linhas)}</tbody></table>")

    fila = []
    for ficheiro in _entregas_pendentes():
        try:
            entrega = ler_entrega(ficheiro.read_text(encoding="utf-8"))
            id_, erros, avisos = prever_entrega(entrega)
            alvo = "acrescentar a" if "acrescentar_a" in entrega else "ficha nova"
            selo = "ok" if not erros else "mau"
            detalhe = ("<br>".join("* " + e(x) for x in erros) or
                       ("<br>".join("~ " + e(x) for x in avisos) or "passa limpo"))
            fila.append(
                f'<div class="entrega {selo}"><b>{e(ficheiro.name)}</b>'
                f'<span>{alvo}: <code>{e(id_)}</code></span>'
                f'<div class="pormenor">{detalhe}</div></div>')
        except SystemExit as ex:
            fila.append(f'<div class="entrega mau"><b>{e(ficheiro.name)}</b>'
                        f'<div class="pormenor">{e(str(ex))}</div></div>')
    fila_html = ("".join(fila) if fila else
                 "<p class=\"ref\">Nada na fila — as histórias que o povo manda pelo WhatsApp entram "
                 "aqui quando o guardião as guarda na pasta <code>entregas/</code>.</p>"
                 "<p class=\"ref\">Depois: <code>python3 uai.py fila</code> para ver, "
                 "<code>python3 uai.py aceitar &lt;ficheiro&gt;</code> para aceitar, "
                 "<code>python3 uai.py devolver &lt;ficheiro&gt; \"motivo\"</code> para devolver "
                 "com o motivo registado.</p>")

    silencio = ""
    if c["adormecidas"]:
        itens = "".join(f'<li><a href="{e(i)}.html">{e(fichas[i]["lugar"]["nome"])}</a> — '
                        f'<b>{d} dias</b> sem registo novo</li>' for i, d in c["adormecidas"])
        silencio = f"<h3>O silêncio — quem ninguém acorda</h3><ul>{itens}</ul>"

    corpo = f"""<section class="mesa">
<p class="faixa">Mesa do guardião — página de trabalho. Não é para o povo, e não se publica.</p>
<h1>A mesa da UAI</h1>
<p class="sub">{len(fichas)} ficha(s) em {e(data_curta(hoje.isoformat()))} · os números saem todos do motor — nenhum é inventado aqui.</p>
<div class="numeros">{numeros}</div>
<h3>O acervo, por quem espera mais</h3>{tabela}
{bloco_gente}
{silencio}
<h3>A fila — o que chegou e espera decisão</h3>
{fila_html}
<p class="ref">Esta página é gerada por <code>uai.py construir</code> e fica no mesmo sítio que as
outras — mas com <code>noindex</code>: é a única que não é para mostrar.</p>
</section>"""
    return pagina("A mesa da UAI — curadoria", corpo,
                  "Mesa de trabalho do guardião da UAI.", scripts=())


def pagina_cartao(quem: dict | None = None) -> str:
    """O cartão de bolso — para quem não vê, ou não lê, ou não tem paciência para um ecrã.

    Página própria (não usa a folha do site): **branco e preto, letra enorme, pronto a imprimir**.
    Aqui a estética da casa cede o lugar — quem precisa deste cartão precisa de contraste, não de
    ambiente. *(23/11/2026: pedido do navegante, a pensar em quem não vê.)*
    """
    quem = quem or carregar_contato()
    tel = telefone_bonito(quem["whatsapp"])
    zap = _zap(quem, "Quero contar uma história para a UAI de Passos.")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conte uma história de Passos — cartão</title>
<style>
  @page {{ margin: 12mm; }}
  body {{ background:#fff; color:#000; font-family: system-ui, Arial, sans-serif;
    font-size: 20px; line-height: 1.45; margin: 0; padding: 22px 20px 30px; max-width: 700px; }}
  h1 {{ font-size: 40px; line-height: 1.1; margin: 0 0 6px; }}
  h1 small {{ display:block; font-size: 22px; font-weight: 400; margin-top: 6px; }}
  .passos {{ font-size: 22px; margin: 18px 0 10px; padding-left: 0; list-style: none; }}
  .passos li {{ margin-bottom: 12px; padding-left: 46px; position: relative; }}
  .passos li b {{ display:inline-block; position:absolute; left:0; top:0; width:34px; height:34px;
    border:3px solid #000; border-radius:50%; text-align:center; line-height:30px; font-size:20px; }}
  .numero {{ font-size: 46px; font-weight: 700; letter-spacing: 1px; margin: 6px 0 2px; }}
  .qr {{ display: flex; gap: 18px; align-items: center; margin: 18px 0 6px; }}
  .qr img {{ width: 190px; height: 190px; image-rendering: pixelated; border: 2px solid #000; }}
  .qr p {{ font-size: 19px; margin: 0; }}
  .rodape {{ border-top: 3px solid #000; margin-top: 20px; padding-top: 12px; font-size: 18px; }}
  .rodape b {{ font-weight: 700; }}
  @media print {{ body {{ padding: 0; }} .qr img {{ width: 170px; height: 170px; }} }}
</style>
</head>
<body>
<h1>Conte uma história de Passos
<small>Uma praça, uma rua, uma ponte, um coreto — o que cê lembra.</small></h1>

<ol class="passos">
<li><b>1</b> <b>Pode falar, sô.</b> Num precisa escrever nada.</li>
<li><b>2</b> Mande um <b>áudio</b> no WhatsApp da UAI:</li>
</ol>
<p class="numero"><a href="{zap}" style="color:#000">{e(tel)}</a></p>
<p style="font-size:19px;margin:2px 0 0">Abra o WhatsApp, aperte no microfone, e conte. Quem recebe ouve a sua voz e passa pro papel.</p>

<div class="qr">
  <img src="qr/contar-uai.png" alt="Código para abrir a conversa da UAI no WhatsApp">
  <p><b>Ou aponte a câmara</b> deste telemóvel pro quadrado preto: a conversa abre sozinha, com a mensagem já escrita. Pode pedir ajuda a alguém, sem vergonha nenhuma.</p>
</div>

<p class="rodape">
<b>A sua história entra na UAI</b> — a biblioteca viva da cidade.<br>
<b>Nunca com o nome de quem contou.</b> Sempre com a data.<br>
<b>Nada se apaga:</b> se um dia mudar, corrige-se com a data do lado.<br>
Página pra ouvir e pra ler alto: <b>uai/contar</b> — e tem um botão «ouvir o que fazer».
</p>
<p style="font-size:17px;margin-top:14px">{e(quem['nome'])} · a história é da cidade, não de quem guarda.</p>
</body>
</html>"""


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "receber":
        id_, erros = receber(ler_entrega(Path(argv[2]).read_text(encoding="utf-8")))
        for x in erros:
            print("erro:", x)
        print(("recusada: " if erros else "guardada em fichas/") + f"{id_}.json")
        return 1 if erros else 0
    cmd = argv[1] if len(argv) > 1 else "validar"
    if cmd == "gente":
        gente = carregar_gente()
        fotos = fotos_do_acervo()
        de_pe_n, retiradas = 0, 0
        for id_, f in gente.items():
            if not de_pe(f):
                retiradas += 1
                print(f"— {id_}: retirada a pedido ({f.get('retirada', {}).get('quando', '')})")
                continue
            de_pe_n += 1
            erros, avisos = validar_ficha(id_, f, fotos)
            erros += nunca_apagar(versao_anterior(id_, pasta="gente"), f)
            estado = "✗" if erros else "✓"
            print(f"{estado} {id_} — {nome_de(f)}")
            for x in erros:
                print(f"    erro: {x}")
            for x in avisos:
                print(f"    aviso: {x}")
        print(f"{de_pe_n} de pé · {retiradas} retirada(s) a pedido · {len(gente)} no total")
        return 0
    if cmd == "folha":
        # a UAI numa folha só (23/11/2026): um ficheiro que se manda por mensagem e abre sem servidor
        import folha

        return folha.main([argv[0]] + argv[2:])
    if cmd == "fila":
        pend = _entregas_pendentes()
        if not pend:
            print("a fila está vazia — nada à espera de decisão")
            return 0
        mau = 0
        for ficheiro in pend:
            try:
                entrega = ler_entrega(ficheiro.read_text(encoding="utf-8"))
                id_, erros, avisos = prever_entrega(entrega)
                alvo = "acrescentar a" if "acrescentar_a" in entrega else "ficha nova"
                print(("✗ " if erros else "✓ ") + f"{ficheiro.name} · {alvo} {id_}")
                for x in erros:
                    print("    erro:", x)
                for x in avisos:
                    print("    aviso:", x)
                mau += bool(erros)
            except SystemExit as ex:
                print("✗", ficheiro.name, "·", ex)
                mau += 1
        print(f"\n{len(pend)} na fila · {mau} com erro")
        print("  aceitar:  python3 uai.py aceitar <ficheiro>")
        print("  devolver: python3 uai.py devolver <ficheiro> \"motivo\"")
        return 1 if mau else 0
    if cmd in ("aceitar", "devolver"):
        if len(argv) < 3:
            print(f"uso: uai.py {cmd} <ficheiro>")
            return 2
        ficheiro = ENTREGAS / Path(argv[2]).name
        if not ficheiro.exists():
            print("erro: não há", ficheiro)
            return 1
        if cmd == "aceitar":
            id_, erros = receber(ler_entrega(ficheiro.read_text(encoding="utf-8")))
            for x in erros:
                print("erro:", x)
            if erros:
                print("recusada — a entrega fica na fila até estar em ordem")
                return 1
            destino = ENTREGAS / "aceites"
            destino.mkdir(exist_ok=True)
            shutil.move(str(ficheiro), str(destino / ficheiro.name))
            print(f"✓ aceite em fichas/{id_}.json · {ficheiro.name} → entregas/aceites/")
            return 0
        motivo = argv[3] if len(argv) > 3 else "(sem motivo dito)"
        destino = ENTREGAS / "devolvidas"
        destino.mkdir(exist_ok=True)
        alvo = destino / ficheiro.name
        shutil.move(str(ficheiro), str(alvo))
        (destino / "motivos.md").open("a", encoding="utf-8").write(
            f"- {dt.date.today().isoformat()} · {ficheiro.name} · {motivo}\n")
        print(f"✓ devolvida · {ficheiro.name} → entregas/devolvidas/ · motivo registado")
        return 0

    if cmd == "selar":
        # 24/11/2026 — põe o carimbo próprio nas fichas que ainda não o têm (e confirma as outras).
        # A lei «nada se apaga» passa a viajar dentro da ficha: não depende do `git show`.
        n, maus = 0, 0
        for pasta in (FICHAS, GENTE):
            if not pasta.is_dir():
                continue
            for caminho in sorted(pasta.glob("*.json")):
                ficha = json.loads(caminho.read_text(encoding="utf-8"))
                erros = carimbo_quebrado(ficha)
                if erros:
                    maus += 1
                    print(f"✗ {caminho.name}")
                    for x in erros:
                        print(f"    erro: {x}")
                    continue
                antes = json.dumps(ficha, ensure_ascii=False, sort_keys=True)
                selar(ficha)
                depois = json.dumps(ficha, ensure_ascii=False, sort_keys=True)
                if depois != antes:
                    caminho.write_text(json.dumps(ficha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    n += 1
                    print(f"✓ {caminho.name} selada")
                else:
                    print(f"✓ {caminho.name} já selada")
        print(f"{n} ficha(s) selada(s) · {maus} com o carimbo quebrado")
        return 1 if maus else 0

    if cmd == "validar":
        fichas, fotos, ruim = carregar(), fotos_do_acervo(), 0
        for id_, f in fichas.items():
            erros, avisos = validar_ficha(id_, f, fotos)
            erros += nunca_apagar(versao_anterior(id_), f)
            print(("✗ " if erros else "✓ ") + id_)
            for x in erros:
                print("    erro:", x)
            for x in avisos:
                print("    aviso:", x)
            ruim += bool(erros)
        print(f"{len(fichas) - ruim}/{len(fichas)} fichas de pé")
        onde = mapa.carregar_onde()
        erros_onde = validar_onde(onde, fichas, mapa.carregar_regiao()["moldura"])
        for x in erros_onde:
            print("✗", x)
        sem = sorted(set(fichas) - set(onde))
        moldura = mapa.carregar_regiao()["moldura"]
        fora = sorted(i for i, o in onde.items() if not erros_onde and not no_mapa(o, moldura))
        print(f"{len(onde) - len(fora)}/{len(fichas)} fichas no mapa de Passos"
              + (f" — fora do mapa: {', '.join(fora)}" if fora else "")
              + (f" — falta saber onde: {', '.join(sem)}" if sem else ""))
        regiao = mapa.carregar_regiao()
        hoje = dt.date.today()
        js, erros_j = mapa.tracar_jornadas(mapa.carregar_jornadas(), regiao,
                                           {l["id"]: l for l in lugares_no_mapa(fichas, onde, regiao["moldura"], hoje)})
        for x in erros_j:
            print("✗", x)
        for j in js:
            print(f"✓ jornada «{j['nome']}»: {len(j['paradas'])} paradas, {mapa.distancia(j['metros'])}, {mapa.a_pe(j['minutos'])}")
        return 1 if ruim or erros_onde or erros_j else 0
    if cmd == "construir":
        saida = Path(argv[2]) if len(argv) > 2 else RAIZ / "site"
        problemas = construir(saida)
        for p in problemas:
            print("erro:", p)
        if not problemas:
            print(f"site em {saida}")
        return 1 if problemas else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
