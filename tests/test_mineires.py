#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da voz mineira da UAI (23/11/2026).

Pedido do navegante: *«usa o sotaque daqui do sul de minas, uai»*.
O que estes testes prendem é a regra da tradução: **muda o jeito de dizer, nunca o que se diz.**
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uai  # noqa: E402


class AFalaMineira(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.capa = uai.pagina_inicio(uai.carregar(), date(2026, 11, 23))
        cls.contar = uai.pagina_deixar(uai.carregar())
        cls.cartao = uai.pagina_cartao({"nome": "UAI · Passos", "whatsapp": "5535991002375", "email": ""})
        cls.gente = uai.pagina_gente({})

    def test_a_capa_fala_da_terra(self):
        self.assertIn("<h2>O que o povo guardou</h2>", self.capa)
        self.assertIn("conta o que cê sabe", self.capa)
        self.assertIn("só o lugar e o dia", self.capa)

    def test_a_pagina_de_contar_fala_da_terra(self):
        self.assertIn("Conta <b>o que cê sabe</b>", self.contar)
        self.assertIn("sem cê apertar", self.contar)
        self.assertIn("Pode <b>falar</b>, sô", self.contar)

    def test_o_cartao_fala_da_terra(self):
        self.assertIn("Pode falar, sô", self.cartao)
        self.assertIn("Num precisa escrever nada", self.cartao)
        self.assertIn("o que cê lembra", self.cartao)

    def test_a_gente_fala_da_terra(self):
        self.assertIn("tá vazia", self.gente)
        self.assertIn("entra pela própria palavra", self.gente)

    def test_a_voz_mudou_e_o_conteudo_nao(self):
        """A regra: muda o jeito de dizer, nunca o que se diz."""
        self.assertEqual(len(uai.LEIS), 7, "as leis da casa são sete — e continuam sete")
        tudo = " ".join(a + " " + b for a, b in uai.LEIS)
        for ideia in ("Nunca quem falhou", "Nunca quem contou", "nunca apagar",
                      "procedência", "Museu não é álbum", "Sem dono", "data e estado"):
            self.assertIn(ideia, tudo, f"a lei «{ideia}» desapareceu na tradução")

    def test_a_conversa_fala_da_terra(self):
        """É a fala que o visitante sente — mais que os títulos."""
        js = (Path(__file__).resolve().parents[1] / "estatico" / "conversa.js").read_text(encoding="utf-8")
        for fala in ("Uai, chegue aqui, sô!", "Sobre que canto cê quer contar?",
                     "E como cê sabe disso?", "Conta um pouquim mais",
                     "fica registado — o caso é da cidade, não seu"):
            self.assertIn(fala, js, f"a conversa perdeu a fala «{fala}»")

    def test_a_conversa_mantem_as_regras(self):
        """O mineirês muda a voz; as regras da casa ficam ditas do mesmo jeito."""
        js = (Path(__file__).resolve().parents[1] / "estatico" / "conversa.js").read_text(encoding="utf-8")
        self.assertIn("num guarda quem contou", js)
        self.assertIn("sempre diz a fonte", js)

    def test_o_mineires_nao_virou_brincadeira(self):
        """Tempero, não comida: o «sô» e o «uai» entram com parcimónia."""
        self.assertLessEqual(self.capa.count(" sô"), 2, "«sô» demais vira caipirês de brincadeira")
        self.assertLessEqual(self.capa.count("uai "), 1)
        self.assertLessEqual(self.contar.count(" sô"), 2)


if __name__ == "__main__":
    unittest.main()
