#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A régua de prova — a lei num sítio só. (24/11/2026)

Atena escreveu-a em linhas curtas (`REGUA-DE-PROVA.md`, dos Conselhos de 24/11);
aqui ela corre. **Uma régua, três leitores** (`plano-a-dois.md`, frente 1): o
arquivo (`validar_ficha`), a estante e o tempo (`situacao`) e a folha
(`_registo_li`) perguntam todos à MESMA função — para não nascer a segunda
régua, que é a doença de hoje (três cópias a decidir a mesma coisa, e a
divergirem em silêncio).

O que a régua diz, e porquê:

  · Um registo que diz «verificado» só tem prova se trouxer um **artefacto
    verificável**: um link público (http/https), ou uma fotografia que ESTEJA
    no acervo (com autor, licença e origem registados lá). Sem isso é **selo
    emprestado** — diz-se «prova por juntar», e a lista diz o que falta.

  · Uma **foto-fantasma** — um nome de foto que o acervo não tem — não é prova:
    é promessa de prova. (Contra-exemplo de 24/11: a régua antiga mostrava o
    selo «verificado» a uma foto que não existia, porque cada leitor decidia
    por si e só um deles sabia do acervo.)

  · O que Atena põe de fora vale aqui: mtime, «verificado por IA», auto-carimbo,
    confiança, hash sozinho. Nenhum deles sobe o grau acima de zero.

Os graus são de Atena (1–4). A UAI só consegue conferir o grau 2 a partir do que
guarda hoje (`fonte`: descricao · url · foto). Por isso a régua é honesta: dá o
grau que se pode conferir, e para o resto diz «prova por juntar» com a lista.
"""
from __future__ import annotations

import re

# Os graus de Atena (REGUA-DE-PROVA.md). A UAI confere o 2; os outros ficam
# nomeados para o dia em que a casa guardar chave, hash e cadeia de custódia.
GRAUS = {
    0: "sem prova",
    1: "testemunho assinado",
    2: "artefacto com proveniência",
    3: "registo de sistema auditável",
    4: "cópia com cadeia de custódia",
}

_URL_PUBLICA = re.compile(r"^https?://", re.I)

# O que não conta, dito por extenso — para a lista do que falta ser honesta.
O_QUE_NAO_CONTA = (
    "mtime/ctime — mudável por touch, tar, backup; não prova autor nem momento",
    "«verificado por IA» — eco, não testemunha; sem identidade nem chave",
    "auto-carimbo — um texto que se declara verdadeiro é circular",
    "confiança — é relação, não prova; serve para delegar, não para arquivar",
    "hash sozinho — prova integridade, não autoria nem momento",
)


def artefacto(registo: dict, fotos: dict | None) -> dict | None:
    """O artefacto verificável que o registo traz — ou None.

    Conta uma URL pública (http/https) ou uma foto que ESTEJA no acervo.
    Uma foto que o acervo não tem é fantasma: nome de prova, sem prova.
    """
    fonte = registo.get("fonte")
    if not isinstance(fonte, dict):
        return None
    url = fonte.get("url")
    if isinstance(url, str) and _URL_PUBLICA.match(url.strip()):
        return {"tipo": "url", "valor": url.strip()}
    foto = fonte.get("foto")
    if isinstance(foto, str) and foto.strip() and fotos and foto in fotos:
        return {"tipo": "foto", "valor": foto}
    return None


def avaliar(registo: dict, fotos: dict | None) -> dict:
    """A régua. O veredicto sobre a prova de UM registo.

    Devolve:
      grau                 — 0 a 4 (de Atena). O que a UAI confere é o 2.
      tem_prova            — há artefacto verificável?
      verificado_sem_prova — o registo DIZ «verificado» e não tem prova? É o caso
                             que a casa trata como «prova por juntar».
      o_que_falta          — a lista do que faria disto prova.
      artefacto            — o artefacto que sustenta a prova, se houver.
    """
    achado = artefacto(registo, fotos)
    tem_prova = achado is not None
    verificado_sem_prova = registo.get("tipo") == "verificado" and not tem_prova

    falta: list[str] = []
    if verificado_sem_prova:
        fonte = registo.get("fonte")
        foto = fonte.get("foto") if isinstance(fonte, dict) else None
        if isinstance(foto, str) and foto.strip():
            falta.append(f"a foto «{foto}» não está no acervo — juntá-la, com autor e licença")
        else:
            falta.append("um link público (http/https) ou uma foto no acervo")
        falta.append("autor identificado e momento (a data do registo)")

    return {
        "grau": 2 if tem_prova else 0,
        "tem_prova": tem_prova,
        "verificado_sem_prova": verificado_sem_prova,
        "o_que_falta": falta,
        "artefacto": achado,
    }


def tem_prova(registo: dict, fotos: dict | None) -> bool:
    """Atalho para um leitor que só quer o sim/não."""
    return artefacto(registo, fotos) is not None
