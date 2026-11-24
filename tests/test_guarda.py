#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes do grupo GUARDA — a prova (24/11/2026).

Nasceram do achado do Chagas: *o barbeiro da UAI é o selo emprestado.* Um registo dizia
«verificado» sem link nem foto — e a ficha entrava, e o pino ia pro mapa.

A lei que fica: **na porta, recusa-se; na estante, o selo não se mostra.**
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uai  # noqa: E402

SEM_PROVA = {"tipo": "verificado", "data": "2026-11-05", "entrou": "2026-11-05",
             "texto": "A praça existe, e eu vi.", "fonte": {"descricao": "visto no local"}}
COM_PROVA = dict(SEM_PROVA, fonte={"descricao": "visto no local", "url": "https://exemplo.org/foto"})


def ficha_com(registo):
    return {"lugar": {"nome": "Praça de Teste", "referencia": "rua de teste"}, "registos": [registo]}


class OAchadoDoChagas(unittest.TestCase):
    """O selo emprestado."""

    def test_na_porta_o_selo_sem_prova_e_recusado(self):
        erros, _ = uai.validar_ficha("praça-de-teste", ficha_com(SEM_PROVA), na_porta=True)
        self.assertTrue(any("prova por juntar" in x for x in erros),
                        f"o selo emprestado passou na porta: {erros}")

    def test_na_porta_o_selo_com_prova_entra(self):
        erros, _ = uai.validar_ficha("praça-de-teste", ficha_com(COM_PROVA), na_porta=True)
        self.assertEqual([x for x in erros if "prova" in x], [])

    def test_na_estante_a_ficha_num_cai_por_causa_do_selo(self):
        """A ficha que já está dentro não derruba a construção — mas fica com o aviso."""
        _, avisos = uai.validar_ficha("praça-de-teste", ficha_com(SEM_PROVA))
        self.assertTrue(any("prova por juntar" in x for x in avisos))
        _erros, avisos_prova = uai.validar_ficha("praça-de-teste", ficha_com(COM_PROVA))
        self.assertEqual([x for x in avisos_prova if "prova" in x], [],
                         "com prova, o aviso da prova desaparece")

    def test_o_selo_nao_se_mostra_quando_nao_ha_prova(self):
        pagina = uai.pagina_lugar("praça-de-teste", ficha_com(SEM_PROVA), date(2026, 11, 24), [])
        self.assertNotIn('>verificado</span>', pagina, "o selo apareceu sem prova")
        self.assertIn("prova por juntar", pagina, "tem de dizer que a prova falta")

    def test_o_selo_mostra_se_quando_ha_prova(self):
        pagina = uai.pagina_lugar("praça-de-teste", ficha_com(COM_PROVA), date(2026, 11, 24), [])
        self.assertIn('>verificado</span>', pagina)
        self.assertNotIn("prova por juntar", pagina)

    def test_o_zelo_marca_a_ficha_do_selo_emprestado(self):
        s = uai.situacao(ficha_com(SEM_PROVA), date(2026, 11, 24))
        self.assertIn("prova por juntar", s["cuidado"])
        s2 = uai.situacao(ficha_com(COM_PROVA), date(2026, 11, 24))
        self.assertNotIn("prova por juntar", s2["cuidado"])

    def test_o_sinal_novo_nao_derruba_a_pagina(self):
        """O «esperando_resposta» entrou a 23/11 e não tinha rótulo — a folha rebentava."""
        # os conhecidos mostram o rótulo humano; um desconhecido mostra-se a si próprio
        for sinal in ("esperando_resposta", "adormecida", "prova por juntar"):
            self.assertTrue(uai._chips_cuidado({"cuidado": [sinal]}), f"«{sinal}» derrubou a folha")
        self.assertIn("sinal-que-ainda-nao-existe",
                      uai._chips_cuidado({"cuidado": ["sinal-que-ainda-nao-existe"]}),
                      "um sinal novo tem de aparecer, não derrubar")

    def test_o_receber_recusa_e_nao_grava(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "fichas"
            pasta.mkdir()
            antes = uai.FICHAS
            uai.FICHAS = pasta
            try:
                id_, erros = uai.receber({"lugar": {"nome": "Lugar Novo"},
                                          "registos": [SEM_PROVA]})
                self.assertTrue(erros, "a porta deixou entrar um selo emprestado")
                self.assertFalse((pasta / f"{id_}.json").exists(), "gravou o que devia recusar")
            finally:
                uai.FICHAS = antes


if __name__ == "__main__":
    unittest.main()
