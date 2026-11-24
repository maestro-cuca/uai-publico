#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da ponte de voz (ouvir.py) — 23/11/2026.

Não correm a transcrição (é lenta e depende do motor da casa): provam a *porta* — o que entra,
o que fica à espera, o que se recusa. A transcrição a sério foi corrida à mão e está registada
no olimpo: áudio → texto cru → fila.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ouvir  # noqa: E402


class APonteDeVoz(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self._audios, self._textos = ouvir.AUDIOS, ouvir.TEXTOS
        ouvir.AUDIOS = self.base / "entregas" / "audios"
        ouvir.OUVIDOS = ouvir.AUDIOS / "ouvidos"
        ouvir.TEXTOS = self.base / "entregas" / "textos"
        ouvir.AUDIOS.mkdir(parents=True)

    def tearDown(self):
        ouvir.AUDIOS, ouvir.TEXTOS = self._audios, self._textos
        ouvir.OUVIDOS = ouvir.AUDIOS / "ouvidos"
        self._tmp.cleanup()

    def test_ve_os_audios_mas_nao_os_restos(self):
        (ouvir.AUDIOS / "historia.ogg").write_bytes(b"x")
        (ouvir.AUDIOS / "outra.m4a").write_bytes(b"x")
        (ouvir.AUDIOS / "notas.txt").write_text("não é áudio")
        (ouvir.AUDIOS / ".escondido.ogg").write_bytes(b"x")
        nomes = [p.name for p in ouvir.a_espera()]
        self.assertEqual(nomes, ["historia.ogg", "outra.m4a"])

    def test_pasta_que_ainda_nao_existe_nao_rebenta(self):
        ouvir.AUDIOS.rmdir()
        self.assertEqual(ouvir.a_espera(), [])

    def test_nada_a_espera_diz_o_mesmo_de_cada_vez(self):
        self.assertEqual(ouvir.a_espera(), [])

    def test_o_slug_nao_deixa_lixo_no_nome(self):
        self.assertEqual(ouvir.slug("Áudio da Dona Maria!!.ogg"), "audio-da-dona-maria-ogg")
        self.assertEqual(ouvir.slug("..."), "audio")

    def test_transcricao_vazia_nao_vira_entrega(self):
        ficheiro = ouvir.AUDIOS / "mudo.ogg"
        ficheiro.write_bytes(b"x")
        ouvir.transcrever = lambda p: ""          # o motor devolveu nada
        self.assertIsNone(ouvir.ouvir(ficheiro))
        self.assertTrue(ficheiro.exists(), "o áudio fica onde está — não se perde a voz de ninguém")
        self.assertFalse(ouvir.TEXTOS.exists())

    def test_a_transcricao_fica_como_quem_ouviu_e_o_audio_vai_para_ouvidos(self):
        ficheiro = ouvir.AUDIOS / "historia.ogg"
        ficheiro.write_bytes(b"x")
        ouvir.transcrever = lambda p: "Nos domingos a banda tocava no coreto."
        destino = ouvir.ouvir(ficheiro)
        self.assertIsNotNone(destino)
        texto = destino.read_text(encoding="utf-8")
        self.assertIn("Nos domingos a banda tocava no coreto.", texto)
        self.assertIn("transcrição crua, sem correcções", texto)
        self.assertIn("quem contou não tem nome aqui", texto)
        self.assertTrue((ouvir.OUVIDOS / "historia.ogg").exists())
        self.assertFalse(ficheiro.exists())


if __name__ == "__main__":
    unittest.main()
