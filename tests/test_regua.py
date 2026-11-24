#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A régua de prova, posta à prova (24/11/2026).

Frente 1 do plano a dois: *Atena define · Hefesto forja.* Atena escreveu a régua
em linhas curtas (`REGUA-DE-PROVA.md`); estes testes forjam-na no código.

**Contra-exemplo antes da lei.** A ordem importa: primeiro prende-se o caso que a
casa DEIXOU PASSAR — a *foto-fantasma*, um registo que diz «verificado» apontando
para uma foto que o acervo não tem. Na régua antiga, três leitores decidiam por
si, e dois deles (o tempo e a folha) não sabiam do acervo — por isso mostravam o
selo «verificado» a uma prova que não existia. Este ficheiro reprova isso; só
depois é que a lei (uma régua só) faz os três leitores concordarem.

Correr da raiz:  python3 -m unittest discover tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import regua  # noqa: E402
import uai  # noqa: E402

HOJE = date(2026, 11, 24)

# Um acervo de teste explícito — para o veredicto não depender do disco.
ACERVO_COM_FOTO = {"ponte.jpg": {"ficheiro": "ponte.jpg", "autor": "x", "licenca": "CC BY 4.0"}}
ACERVO_VAZIO: dict = {}


def registo(**mais):
    r = {"tipo": "verificado", "data": "2026-11-05", "entrou": "2026-11-05",
         "texto": "A praça existe, e eu vi.", "fonte": {"descricao": "visto no local"}}
    r.update(mais)
    return r


def ficha_com(reg):
    return {"lugar": {"nome": "Praça de Teste", "referencia": "rua de teste"}, "registos": [reg]}


class OContraExemplo_FotoFantasma(unittest.TestCase):
    """O caso que a régua antiga deixava passar. Contra-exemplo antes da lei.

    Um registo «verificado» cujo `fonte.foto` nomeia um ficheiro que o acervo NÃO
    tem. Não é prova: é promessa de prova. Os três leitores têm de o reprovar.
    """

    def setUp(self):
        self.reg = registo(fonte={"descricao": "visto no local", "foto": "nao-existe.jpg"})
        self.ficha = ficha_com(self.reg)

    def test_regua_reprova_a_foto_fantasma(self):
        veredicto = regua.avaliar(self.reg, ACERVO_VAZIO)
        self.assertFalse(veredicto["tem_prova"], "a régua contou uma foto que não existe como prova")
        self.assertTrue(veredicto["verificado_sem_prova"])

    def test_leitor_do_arquivo_reprova(self):
        """validar_ficha: na estante vira aviso «prova por juntar»; na porta, erro."""
        _erros, avisos = uai.validar_ficha("praca-de-teste", self.ficha, ACERVO_VAZIO)
        self.assertTrue(any("prova por juntar" in a for a in avisos), avisos)
        erros_porta, _ = uai.validar_ficha("praca-de-teste", self.ficha, ACERVO_VAZIO, na_porta=True)
        self.assertTrue(any("prova por juntar" in e for e in erros_porta), erros_porta)

    def test_leitor_do_tempo_reprova(self):
        """situacao: a ficha fica com o cuidado «prova por juntar»."""
        s = uai.situacao(self.ficha, HOJE, ACERVO_VAZIO)
        self.assertIn("prova por juntar", s["cuidado"], s["cuidado"])

    def test_leitor_da_folha_reprova(self):
        """_registo_li: o selo «verificado» não se mostra; diz-se que a prova falta."""
        li = uai._registo_li(self.reg, 1, ACERVO_VAZIO)
        self.assertNotIn('>verificado</span>', li, "o selo apareceu sobre uma foto que não existe")
        self.assertIn("prova por juntar", li)


class UmaRegua_TresLeitores(unittest.TestCase):
    """A lei: os três leitores dão SEMPRE o mesmo veredicto sobre a prova.

    É esta a cura da doença de hoje — «três réguas para uma verdade». Não há mais
    uma cópia da regra no arquivo, no tempo e na folha: há uma função só.
    """

    CASOS = {
        "link público": registo(fonte={"descricao": "jornal", "url": "https://exemplo.org/foto"}),
        "foto no acervo": registo(fonte={"descricao": "vi", "foto": "ponte.jpg"}),
        "foto-fantasma": registo(fonte={"descricao": "vi", "foto": "nao-existe.jpg"}),
        "só descrição": registo(fonte={"descricao": "visto por mim"}),
        "verificado sem fonte extra": registo(),
    }

    def _vozes(self, reg):
        """O veredicto dos três leitores, cada um dito no seu formato."""
        arquivo = not any(
            "prova por juntar" in a for a in uai.validar_ficha("praca-de-teste", ficha_com(reg), ACERVO_COM_FOTO)[1])
        tempo = "prova por juntar" not in uai.situacao(ficha_com(reg), HOJE, ACERVO_COM_FOTO)["cuidado"]
        folha = "prova por juntar" not in uai._registo_li(reg, 1, ACERVO_COM_FOTO)
        return {"arquivo": arquivo, "tempo": tempo, "folha": folha}

    def test_os_tres_concordam(self):
        for nome, reg in self.CASOS.items():
            vozes = self._vozes(reg)
            self.assertEqual(len(set(vozes.values())), 1,
                             f"«{nome}»: os leitores divergiram — {vozes} (a doença de hoje)")
            # E o veredicto tem de bater com a régua, que é a fonte única.
            esperado = regua.tem_prova(reg, ACERVO_COM_FOTO)
            self.assertEqual(vozes["arquivo"], esperado, f"«{nome}»: o arquivo não leu a régua")

    def test_com_prova_mostra_o_selo_e_sem_prova_nao(self):
        com = self.CASOS["link público"]
        sem = self.CASOS["foto-fantasma"]
        self.assertIn('>verificado</span>', uai._registo_li(com, 1, ACERVO_COM_FOTO))
        self.assertNotIn('>verificado</span>', uai._registo_li(sem, 1, ACERVO_COM_FOTO))


class OQueNaoConta(unittest.TestCase):
    """O que Atena põe de fora — mesmo parecendo que conta — não sobe o grau."""

    def test_a_regua_nomeia_o_que_nao_conta(self):
        for falso in ("mtime", "verificado por IA", "auto-carimbo", "confiança", "hash sozinho"):
            self.assertTrue(any(falso in linha for linha in regua.O_QUE_NAO_CONTA), falso)

    def test_auto_carimbo_de_verificado_nao_e_prova(self):
        """Um registo que se declara «verificado» a si mesmo é circular — grau 0."""
        v = regua.avaliar(registo(), ACERVO_COM_FOTO)
        self.assertEqual(v["grau"], 0)
        self.assertFalse(v["tem_prova"])

    def test_uma_foto_que_o_acervo_tem_e_prova_de_grau_2(self):
        v = regua.avaliar(registo(fonte={"descricao": "vi", "foto": "ponte.jpg"}), ACERVO_COM_FOTO)
        self.assertEqual(v["grau"], 2)
        self.assertTrue(v["tem_prova"])
        self.assertEqual(v["artefacto"]["tipo"], "foto")

    def test_url_que_nao_e_publica_nao_conta(self):
        """file:// não é link público — é caminho de casa."""
        v = regua.avaliar(registo(fonte={"descricao": "foto", "url": "file:///home/x/f.jpg"}), ACERVO_COM_FOTO)
        self.assertFalse(v["tem_prova"])

    def test_o_que_falta_diz_o_que_juntar(self):
        v = regua.avaliar(registo(fonte={"descricao": "vi", "foto": "nao-existe.jpg"}), ACERVO_VAZIO)
        self.assertTrue(any("não está no acervo" in x for x in v["o_que_falta"]), v["o_que_falta"])


if __name__ == "__main__":
    unittest.main()
