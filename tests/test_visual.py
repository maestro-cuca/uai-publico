#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes do que a casa pediu no visual (23/11/2026).

Nasceram de dois achados dos dezoito — e de dois erros do Mago:
  · «o index no telemóvel é uma tira de 3 809 px» — medido: a lista de lugares começava a 743 px,
    e as leis a 2 344 px;
  · «a pega da folha parece arrastar-se e não se arrasta» — o Atena tinha razão, e o Mago mediu mal
    (um `querySelector('::before')` não lê pseudo-elementos).
Estes testes prendem a correcção: a folha estende-se a sério, e a lista chega cedo ao polegar.
"""
import re
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uai  # noqa: E402

CSS = (uai.RAIZ / "estatico" / "uai.css").read_text(encoding="utf-8")
JS = (uai.RAIZ / "estatico" / "acesso.js").read_text(encoding="utf-8")


class AFolhaEstendeSe(unittest.TestCase):

    def setUp(self):
        self.pagina = uai.pagina_inicio(uai.carregar(), date(2026, 11, 23))

    def test_a_pega_e_um_botao_a_serio(self):
        """Era um ::before — desenhava-se e não aceitava gesto."""
        self.assertIn('id="pega"', self.pagina)
        self.assertIn('aria-controls="conteudo"', self.pagina)
        self.assertIn('aria-expanded="false"', self.pagina)
        self.assertRegex(self.pagina, r'<button[^>]*class="pega"[^>]*>')

    def test_a_pega_tem_gesto_e_teclado(self):
        self.assertIn("ligarPega", JS)
        self.assertIn("pointerdown", JS)
        self.assertIn("ArrowUp", JS, "o teclado também tem de estender a folha")
        self.assertIn('"recolher a folha"', JS, "o rótulo diz o que o botão faz, agora")

    def test_a_folha_alta_tem_regra_e_esconde_o_mapa(self):
        self.assertIn(".painel.alta", CSS)
        self.assertIn("html.folha-alta #cena", CSS)

    def test_a_pega_desaparece_no_so_texto(self):
        self.assertIn("html.so-texto button.pega", CSS)

    def test_a_pega_e_alvo_grande(self):
        """44 px — a medida mínima para um dedo (o padrão do toque)."""
        m = re.search(r"button\.pega\s*\{[^}]*min-height:\s*(\d+)px", CSS)
        self.assertIsNotNone(m, "a pega perdeu o tamanho mínimo — alvo pequeno é alvo errado")
        self.assertGreaterEqual(int(m.group(1)), 44, f"alvo pequeno demais: {m.group(1)}px")


class AListaChegaCedo(unittest.TestCase):

    def test_a_lista_de_lugares_vem_antes_do_mapa(self):
        pagina = uai.pagina_inicio(uai.carregar(), date(2026, 11, 23))
        self.assertLess(pagina.index("<h2>O que o povo guardou</h2>"), pagina.index("<h2>O mapa</h2>"),
                        "a lista é o que a UAI guarda — não pode ficar depois do mapa")

    def test_as_leis_colapsam_no_telemovel(self):
        pagina = uai.pagina_inicio(uai.carregar(), date(2026, 11, 23))
        self.assertIn('<details class="leis"', pagina, "as leis eram 2 344 px de tira")
        self.assertIn(".leis details", CSS)

    def test_a_faixa_do_mapa_e_variavel(self):
        self.assertIn("--faixa-mapa", CSS)
        m = re.search(r"@media \(max-width: 899px\) \{:?[^}]*--faixa-mapa:\s*(\d+)vh", CSS, re.S)
        self.assertIsNotNone(m, "o telemóvel perdeu a sua medida própria")
        self.assertLessEqual(int(m.group(1)), 25, "no telemóvel, mais de 25vh de mapa é tira")


if __name__ == "__main__":
    unittest.main()
