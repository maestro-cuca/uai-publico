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


class APortaDeQuemNaoVe(unittest.TestCase):
    """Vistoria de 24/11/2026 — medida no navegador, não no olho.

    Achados: o «em branco» dava 4,42:1 no fundo verde-mata (o mínimo é 4,5:1),
    e os botões da barra de acesso tinham 36 px de altura (o dedo pede 44).
    """

    def _luminancia(self, rgb):
        def canal(v):
            v = v / 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = (canal(x) for x in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _contraste(self, a, b):
        la, lb = self._luminancia(a), self._luminancia(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    def _hex(self, s):
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))

    def test_o_em_branco_passa_no_fundo_verde_mata(self):
        # a cor do TEMA DE SEMPRE (o escuro), não a do tema claro — a primeira ocorrência é a do claro
        m = re.search(r"--rotulo: #F2EAD3;.*?--e-nenhum:\s*(#[0-9a-fA-F]{6})", CSS, re.S)
        self.assertIsNotNone(m, "o «em branco» perdeu a cor própria")
        fundo = self._hex("#0F2A22")  # o verde-mata, o fundo de sempre
        razao = self._contraste(self._hex(m.group(1)), fundo)
        self.assertGreaterEqual(razao, 4.5,
                                f"«em branco» a {razao:.2f}:1 no verde-mata — abaixo do mínimo (4,5:1)")

    def test_os_botoes_da_barra_sao_alvo_de_dedo(self):
        m = re.search(r"\.acesso button\s*\{[^}]*min-height:\s*(\d+)px", CSS, re.S)
        self.assertIsNotNone(m, "a barra de acesso perdeu a medida dos botões")
        self.assertGreaterEqual(int(m.group(1)), 44,
                                f"botão de {m.group(1)} px — o dedo precisa de 44")

    def test_a_porta_de_voz_existe_e_e_um_botao(self):
        """A porta de quem não vê é o áudio. A barra é montada pelo acesso.js — verificar os dois."""
        pagina = uai.pagina_inicio(uai.carregar(), date(2026, 11, 24))
        self.assertIn("acesso.js", pagina, "a página perdeu o ficheiro que monta a barra de acesso")
        self.assertIn("ouvir", JS, "o botão «ouvir» desapareceu da barra — é a porta de quem não lê")
        self.assertIn("speechSynthesis", JS, "sem voz do sistema, o botão não fala")


if __name__ == "__main__":
    unittest.main()
