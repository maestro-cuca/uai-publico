#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ouvir.py — a UAI ouve quem não escreve (23/11/2026).

PORQUE EXISTE: o app tem de ser simples para quem não vê — o tio João. Para ele, a porta nunca
foi um ecrã: é um áudio no WhatsApp. Mas um áudio exige alguém que o ouça e passe a história
para o papel — e o guardião não pode ser essa pessoa para sempre.

Aqui o áudio deixa de depender de mãos: pousa em entregas/audios/, é transcrito, e aparece na
fila da UAI pronto a decidir. A ponte humana sai do meio.

O QUE NÃO FAZ, de propósito: não escreve a ficha por si. A transcrição é guardada crua, como
quem ouviu — quem estrutura (o guardião, ou o agente da casa) lê o que foi dito e escreve a
entrega. Nada é inventado no meio.

USO:
    python3 ouvir.py             # transcreve os áudios novos e mostra o que dizem
    python3 ouvir.py --espera    # só lista o que está à espera (vigia; saída determinística)
"""
from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
AUDIOS = RAIZ / "entregas" / "audios"
OUVIDOS = AUDIOS / "ouvidos"
TEXTOS = RAIZ / "entregas" / "textos"

TRANSCREVE = Path("/home/strondinha/.hermes/scripts/transcreve.py")
PY_VOZ = Path("/home/strondinha/.hermes/hermes-agent/venv/bin/python")
SUFIXOS = (".ogg", ".oga", ".opus", ".mp3", ".m4a", ".wav", ".aac", ".amr", ".3gp", ".webm")


def slug(t: str, limite: int = 40) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()[:limite].strip("-") or "audio"


def a_espera() -> list[Path]:
    """Os áudios que ainda não foram ouvidos. Ordem estável — a vigia compara saídas."""
    if not AUDIOS.is_dir():
        return []
    return sorted(p for p in AUDIOS.iterdir()
                  if p.is_file() and p.suffix.lower() in SUFIXOS and not p.name.startswith("."))


def transcrever(entrada: Path) -> str:
    """Transcreve um áudio (mono 16 kHz primeiro, como manda o ofício da casa)."""
    wav = Path("/tmp") / (entrada.stem + "-16k.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada),
                    "-ac", "1", "-ar", "16000", str(wav)], check=True)
    r = subprocess.run([str(PY_VOZ), str(TRANSCREVE), str(wav), "small"],
                       capture_output=True, text=True)
    saida = (r.stdout or "").strip()
    return re.sub(r"^\[.*?\]\s*", "", saida, flags=re.S).strip()


def ouvir(ficheiro: Path) -> Path | None:
    """Transcreve e guarda o texto cru. Devolve o ficheiro de texto, ou None se saiu vazio."""
    texto = transcrever(ficheiro)
    if not texto:
        print(f"!! {ficheiro.name}: a transcrição saiu vazia — não invento o que foi dito.")
        return None
    TEXTOS.mkdir(parents=True, exist_ok=True)
    OUVIDOS.mkdir(parents=True, exist_ok=True)
    data = datetime.fromtimestamp(ficheiro.stat().st_mtime).strftime("%Y-%m-%d")
    destino = TEXTOS / f"{data}-{slug(ficheiro.stem)}.txt"
    destino.write_text(
        f"# O que foi dito — {ficheiro.name}\n"
        f"# ouvido em {datetime.now().strftime('%Y-%m-%d %H:%M')} · transcrição crua, sem correcções\n"
        f"# ninguém foi identificado: quem contou não tem nome aqui\n\n{texto}\n",
        encoding="utf-8")
    ficheiro.rename(OUVIDOS / ficheiro.name)
    return destino


def main(argv: list[str]) -> int:
    if "--espera" in argv:
        pend = a_espera()
        for p in pend:
            print(p.name)
        if not pend:
            print("nada à espera")
        return 0

    pend = a_espera()
    if not pend:
        print("nenhum áudio novo em entregas/audios/")
        return 0

    for ficheiro in pend:
        print(f"── {ficheiro.name}")
        destino = ouvir(ficheiro)
        if destino:
            print(destino.read_text(encoding="utf-8").split("\n\n", 1)[-1].strip())
            print(f"\n   guardado em {destino.relative_to(RAIZ)} — falta virar entrega\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
