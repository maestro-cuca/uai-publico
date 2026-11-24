#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes dos campos que a casa pediu no Exame do Saruman (23/11/2026).

O medo de pedir não tem ficha — mas o pedido, o não e o laço têm.
Estes testes prendem o que a vida precisa que a UAI meça.
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uai  # noqa: E402

FONTE = {"descricao": "dito em casa"}
REG_OK = {"data": "2026-11-23", "entrou": "2026-11-23", "tipo": "contado",
          "texto": "A porta bateu e abriu.", "fonte": FONTE}


def ficha(**mudancas):
    f = {"lugar": {"nome": "A Porta"}, "registos": [dict(REG_OK)]}
    for k, v in mudancas.items():
        if v is None:
            f.pop(k, None)
        else:
            f[k] = v
    return f


class OPedidoENaoEDoLaco(unittest.TestCase):

    def test_o_pedido_entra_com_pediu_em(self):
        r = dict(REG_OK)
        r["tipo"] = "pedido"
        r["pediu_em"] = "2026-11-20"
        f = ficha(registos=[r])
        erros, _ = uai.validar_ficha("a-porta", f)
        self.assertEqual(erros, [], erros)

    def test_o_pediu_em_tem_de_ser_data_valida(self):
        r = dict(REG_OK)
        r["tipo"] = "pedido"
        r["pediu_em"] = "ontem"
        f = ficha(registos=[r])
        erros, _ = uai.validar_ficha("a-porta", f)
        self.assertTrue(any("pediu_em" in e for e in erros), erros)

    def test_o_nao_entra_com_recusou(self):
        r = dict(REG_OK)
        r["recusou"] = {"por": "Maria", "quando": "2026-11-22"}
        f = ficha(registos=[r])
        erros, _ = uai.validar_ficha("a-porta", f)
        self.assertEqual(erros, [], erros)

    def test_o_recusou_precisa_de_quem_e_de_quando(self):
        r = dict(REG_OK)
        r["recusou"] = {"por": "Maria"}
        f = ficha(registos=[r])
        erros, _ = uai.validar_ficha("a-porta", f)
        self.assertTrue(any("recusou.quando" in e for e in erros), erros)

    def test_o_recusou_continua_sem_nome_de_quem_contou(self):
        r = dict(REG_OK)
        r["recusou"] = {"por": "Maria", "quando": "2026-11-22", "quem": "o vizinho"}
        f = ficha(registos=[r])
        erros, _ = uai.validar_ficha("a-porta", f)
        self.assertTrue(any("«quem»" in e for e in erros), erros)

    def test_o_toca_liga_a_outra_ficha(self):
        r = dict(REG_OK)
        r["toca"] = ["maria"]
        f = ficha(registos=[r])
        outra = {"pessoa": {"nome": "Maria"}, "registos": [dict(REG_OK)]}
        erros, _ = uai.validar_ficha("a-porta", f, gente={"maria": outra})
        self.assertEqual(erros, [], erros)

    def test_o_toca_avisa_se_a_outra_tem_retirada(self):
        r = dict(REG_OK)
        r["toca"] = ["maria"]
        f = ficha(registos=[r])
        outra = {"pessoa": {"nome": "Maria"}, "registos": [dict(REG_OK)],
                 "retirada": {"quando": "2026-11-23", "pedido_por": "ela"}}
        erros, avisos = uai.validar_ficha("a-porta", f, gente={"maria": outra})
        self.assertEqual(erros, [], erros)
        self.assertTrue(any("retirada" in a for a in avisos), avisos)

    def test_a_ficha_que_so_tem_pedidos_e_esperando_resposta(self):
        r = dict(REG_OK)
        r["tipo"] = "pedido"
        f = ficha(registos=[r])
        s = uai.situacao(f, date(2026, 11, 23))
        self.assertIn("esperando_resposta", s["cuidado"], s)

    def test_a_ficha_com_resposta_nao_e_esperando_resposta(self):
        pedido = dict(REG_OK)
        pedido["tipo"] = "pedido"
        resposta = dict(REG_OK)
        resposta["tipo"] = "contado"
        f = ficha(registos=[pedido, resposta])
        s = uai.situacao(f, date(2026, 11, 23))
        self.assertNotIn("esperando_resposta", s["cuidado"], s)


if __name__ == "__main__":
    unittest.main()
