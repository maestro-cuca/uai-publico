#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da ficha de PESSOA — a segunda metade da UAI (23/11/2026).

Uma pessoa não é um lugar. Estes testes prendem a diferença — que é toda a razão de existir
desta metade: **entra com a sua palavra, e sai quando quiser.**
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uai  # noqa: E402

FONTE = {"descricao": "dito por ele, em casa"}
REG = {"data": "2026-11-23", "entrou": "2026-11-23", "tipo": "contado",
       "texto": "Ele conta histórias da cidade desde que se lembra.", "fonte": FONTE}


def ficha_ok(**mudancas):
    f = {"pessoa": {"nome": "Maria do Coreto", "se_chama": "Dona Maria", "oficio": "conta histórias"},
         "autorizou": {"por": "Maria do Coreto", "quando": "2026-11-23", "como": "disse em voz"},
         "registos": [dict(REG)]}
    for k, v in mudancas.items():
        if v is None:
            f.pop(k, None)
        else:
            f[k] = v
    return f


class AFichaDePessoa(unittest.TestCase):

    def test_uma_pessoa_sem_autorizacao_nao_entra(self):
        erros, _ = uai.validar_ficha("dona-maria", ficha_ok(autorizou=None))
        self.assertTrue(any("autorizou" in e for e in erros), erros)

    def test_a_autorizacao_precisa_das_tres_palavras(self):
        for falta in ("por", "quando", "como"):
            a = {"por": "João", "quando": "2026-11-23", "como": "disse em voz"}
            a.pop(falta)
            erros, _ = uai.validar_ficha("dona-maria", ficha_ok(autorizou=a))
            self.assertTrue(any(falta in e for e in erros), f"faltava {falta}: {erros}")

    def test_o_modo_de_autorizar_tem_de_ser_dos_da_casa(self):
        a = {"por": "João", "quando": "2026-11-23", "como": "talvez"}
        erros, _ = uai.validar_ficha("dona-maria", ficha_ok(autorizou=a))
        self.assertTrue(any("autorizou.como" in e for e in erros), erros)

    def test_quem_contou_continua_proibido_mas_quem_autorizou_nao(self):
        """A distinção central: o arquivo não guarda quem contou — guarda quem autorizou."""
        f = ficha_ok()
        f["autorizou"]["quem"] = "alguém"
        erros, _ = uai.validar_ficha("dona-maria", f)
        self.assertTrue(any("«quem»" in e for e in erros), erros)
        # e «por» passa: é o nome de quem disse sim, e fica à vista
        self.assertFalse(any("autorizou.por" in e for e in uai.validar_ficha("dona-maria", ficha_ok())[0]))

    def test_nao_pode_ser_lugar_e_pessoa_ao_mesmo_tempo(self):
        f = ficha_ok()
        f["lugar"] = {"nome": "Praça"}
        erros, _ = uai.validar_ficha("dona-maria", f)
        self.assertTrue(any("OU" in e for e in erros), erros)

    def test_a_pessoa_precisa_de_nome(self):
        erros, _ = uai.validar_ficha("x", ficha_ok(pessoa={"oficio": "nada"}))
        self.assertIn("falta pessoa.nome", erros)

    def test_onde_vive_com_numero_avisa(self):
        f = ficha_ok(pessoa={"nome": "João", "onde_vive": "Rua das Flores, 210"})
        erros, avisos = uai.validar_ficha("dona-maria", f)
        self.assertEqual(erros, [])
        self.assertTrue(any("número" in a for a in avisos), avisos)

    def test_a_retirada_tira_a_ficha_do_sitio(self):
        f = ficha_ok(retirada={"quando": "2026-11-23", "pedido_por": "Maria do Coreto"})
        erros, avisos = uai.validar_ficha("dona-maria", f)
        self.assertEqual(erros, [], erros)
        self.assertFalse(uai.de_pe(f))

    def test_uma_retirada_nao_se_apaga(self):
        antiga = ficha_ok(retirada={"quando": "2026-11-23", "pedido_por": "ele"})
        erros = uai.nunca_apagar(antiga, ficha_ok())
        self.assertTrue(any("retirada" in e for e in erros), erros)

    def test_a_retirada_precisa_de_quem_a_pediu_e_do_dia(self):
        erros, _ = uai.validar_ficha("dona-maria", ficha_ok(retirada={"pedido_por": "ele"}))
        self.assertTrue(any("retirada.quando" in e for e in erros), erros)
        erros, _ = uai.validar_ficha("dona-maria", ficha_ok(retirada={"quando": "2026-11-23"}))
        self.assertTrue(any("pedido_por" in e for e in erros), erros)

    def test_uma_pessoa_grava_em_gente_nao_em_fichas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            gente, fichas = base / "gente", base / "fichas"
            gente.mkdir(), fichas.mkdir()
            antigas = (uai.GENTE, uai.FICHAS)
            uai.GENTE, uai.FICHAS = gente, fichas
            try:
                entrega = {k: v for k, v in ficha_ok().items()}
                id_, erros = uai.receber(entrega)
                self.assertEqual(erros, [])
                self.assertTrue((gente / f"{id_}.json").exists(), "a pessoa mora em gente/")
                self.assertFalse((fichas / f"{id_}.json").exists())
            finally:
                uai.GENTE, uai.FICHAS = antigas


class OSitioDasPessoas(unittest.TestCase):

    def test_a_lista_nao_mostra_quem_saiu(self):
        """Quem saiu tem de ser OUTRA pessoa — senão o teste não prende nada.

        (24/11/2026: este teste afirmava `assertNotIn("Maria", ...)` e «Maria» nunca esteve na
        ficha de exemplo — passava por ser VAZIO. Aqui a pessoa que sai é distinta.)
        """
        saiu = ficha_ok(
            pessoa={"nome": "Zefa do Alto", "se_chama": "Dona Zefa", "oficio": "benze"},
            autorizou={"por": "Zefa do Alto", "quando": "2026-11-23", "como": "disse em voz"},
            retirada={"quando": "2026-11-23", "pedido_por": "ela própria"},
        )
        pagina = uai.pagina_gente({"dona-maria": ficha_ok(), "zefa-do-alto": saiu})
        self.assertIn("Maria do Coreto", pagina, "quem ficou na lista tem o nome que usa")
        self.assertNotIn("Zefa", pagina, "quem pediu para sair nao aparece na lista")
        self.assertIn("retirada", pagina, "mas fica dito que alguem saiu")
    def test_a_pagina_de_uma_pessoa_diz_quem_autorizou(self):
        pagina = uai.pagina_pessoa("dona-maria", ficha_ok(), date(2026, 11, 23), [])
        self.assertIn("autorizou", pagina)
        self.assertIn("Maria do Coreto", pagina)
        self.assertIn("disse em voz", pagina)
        self.assertIn("sai com a sua palavra", pagina)

    def test_a_pagina_de_quem_saiu_diz_que_saiu(self):
        f = ficha_ok(retirada={"quando": "2026-11-23", "pedido_por": "Maria do Coreto"})
        pagina = uai.pagina_pessoa("dona-maria", f, date(2026, 11, 23), [])
        self.assertIn("pediu para sair", pagina)
        self.assertIn("não se apagou", pagina)
        self.assertIn("Quem sai, sai", pagina)

    def test_o_sitio_constroi_com_gente(self):
        """A gente entra na construção — e sai dela se for retirada."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            gente = base / "gente"
            gente.mkdir()
            (gente / "dona-maria.json").write_text(__import__("json").dumps(ficha_ok(), ensure_ascii=False),
                                             encoding="utf-8")
            antigo = uai.GENTE
            uai.GENTE = gente
            try:
                saida = base / "site"
                self.assertEqual(uai.construir(saida), [])
                self.assertTrue((saida / "gente.html").exists())
                self.assertTrue((saida / "gente" / "dona-maria.html").exists())
                self.assertIn("Maria do Coreto", (saida / "gente.html").read_text(encoding="utf-8"))
            finally:
                uai.GENTE = antigo


if __name__ == "__main__":
    unittest.main()
