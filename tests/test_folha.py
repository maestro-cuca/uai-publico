#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da folha só (folha.py) — 23/11/2026.

A folha existe porque o sítio **não abre a partir de um ficheiro** (o navegador proíbe as
leituras locais) e a casa não tem onde hospedar. Estes testes prendem as duas coisas que
fazem a folha ser uma folha: **não pedir nada a ninguém** e **trazer o mapa dentro**.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import folha  # noqa: E402


class AFolhaSo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.caminho, cls.tamanho = folha.construir_folha(Path(cls._tmp.name) / "uai.html")
        cls.html = cls.caminho.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_nao_pede_nada_a_ninguem(self):
        """Sem servidor e sem rede: nenhum script, folha de estilo ou fonte de fora."""
        self.assertFalse(re.search(r'<script[^>]+src=', self.html), "ficou um script de fora")
        self.assertFalse(re.search(r'<link[^>]+stylesheet', self.html), "ficou um CSS de fora")
        self.assertNotIn("fontes/", self.html, "ficou uma fonte de fora")

    def test_traz_o_mapa_dentro(self):
        self.assertIn("window.UAI_INLINE", self.html)
        self.assertIn("mapa.svg", self.html)
        self.assertIn("chao.bin", self.html)
        self.assertIn("data:image/jpeg;base64,", self.html, "o relevo tem de vir dentro")

    def test_o_chao_vem_descomprimido_e_legivel(self):
        """O que entra na folha é o chão já aberto — o browser não tem de descomprimir nada."""
        dados = folha.bytes_crus(folha.RAIZ / "mapa" / "chao.bin") if (folha.RAIZ / "mapa" / "chao.bin").exists() else None
        if dados:  # o ficheiro em bruto pode não existir; o importante é o tamanho do que entrou
            self.assertGreater(len(dados), 0)
        self.assertRegex(self.html, r'"chao\.bin": "[A-Za-z0-9+/=]{500,}"')

    def test_os_scripts_vem_depois_da_cena(self):
        """Foi este o defeito: sem «defer» que valha, um script no <head> corre antes de haver cena."""
        self.assertIn('id="cena"', self.html)
        self.assertLess(self.html.index('id="cena"'), self.html.index("window.UAI_INLINE"),
                        "o aviso ao mapa tem de vir depois da cena existir")

    def test_as_fichas_entram_como_seccoes(self):
        self.assertIn('class="folha-ficha"', self.html)
        self.assertIn('href="#f-coreto-da-praca-da-matriz"', self.html,
                      "os links para as fichas passam a ser dentro da folha")
        self.assertNotIn('href="coreto-da-praca-da-matriz.html"', self.html)

    def test_a_folha_tem_tamanho_de_mensagem(self):
        """Tem de caber num envio: abaixo de 20 MB, com folga."""
        self.assertLess(self.tamanho, 20 * 1024 * 1024)
        self.assertGreater(self.tamanho, 100_000)


if __name__ == "__main__":
    unittest.main()
