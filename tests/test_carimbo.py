"""O carimbo próprio da ficha — a lei «nada se apaga» sem depender do `git show`.

24/11/2026. Antes, a lei comparava a ficha com a versão do último commit: sem
repositório, sem commit, ou sem git instalado, a lei ficava muda. Agora cada ficha
traz a sua corrente de selos: mudar ou tirar um registo antigo quebra o carimbo, e
vê-se só com o ficheiro na mão.

Correr da raiz: python3 -m unittest discover tests
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uai  # noqa: E402

FOTOS = {"ponte.jpg": {"ficheiro": "ponte.jpg", "autor": "x", "licenca": "CC BY 4.0"}}


def ficha():
    return {
        "lugar": {"nome": "Ponte", "referencia": "centro"},
        "registos": [
            {
                "data": "2026-11-05", "entrou": "2026-11-19", "tipo": "contado",
                "texto": "o guarda-corpo tem um vão", "fonte": {"descricao": "vi no local"},
            }
        ],
    }


def pessoa():
    return {
        "pessoa": {"nome": "João", "oficio": "pedreiro"},
        "autorizou": {"por": "João", "quando": "2026-11-23", "como": "disse em voz"},
        "registos": [
            {"data": "2026-11-23", "entrou": "2026-11-23", "tipo": "contado",
             "texto": "fez o muro da praça", "fonte": {"descricao": "ele contou"}},
        ],
    }


def com_registo_novo(f):
    g = copy.deepcopy(f)
    g["registos"].append({
        "data": "2026-11-20", "entrou": "2026-11-20", "tipo": "contado",
        "texto": "outra história", "fonte": {"descricao": "contaram-me"},
    })
    return g


class OCarimboProprio(unittest.TestCase):

    def test_ficha_sem_carimbo_nao_e_erro(self):
        """Ficha antiga (de antes de 24/11) não cai: o `selar` põe-lhe o carimbo."""
        self.assertEqual(uai.carimbo_quebrado(ficha()), [])

    def test_selar_guarda_a_corrente_dentro_da_ficha(self):
        f = ficha()
        uai.selar(f)
        self.assertEqual(f["carimbos"], uai.carimbos(f))
        self.assertEqual(uai.carimbo_quebrado(f), [])

    def test_mudar_um_registo_antigo_quebra_o_carimbo(self):
        """A prova de que a lei já não precisa do git: a ficha é um dicionário em memória."""
        f = ficha()
        uai.selar(f)
        f["registos"][0]["texto"] = "afinal está tudo bem"
        erros = uai.carimbo_quebrado(f)
        self.assertTrue(any("não fecha" in e for e in erros), erros)
        erros_validar, _ = uai.validar_ficha("ponte", f, FOTOS)
        self.assertTrue(any("carimbo" in e for e in erros_validar), erros_validar)

    def test_tirar_um_registo_quebra_o_carimbo(self):
        f = com_registo_novo(ficha())
        uai.selar(f)
        f["registos"] = f["registos"][:1]
        erros = uai.carimbo_quebrado(f)
        self.assertTrue(any("tirado" in e for e in erros), erros)

    def test_acrescentar_preserva_os_selos_antigos(self):
        """Acrescentar não reescreve a história: o prefixo da corrente fica igual."""
        f = ficha()
        uai.selar(f)
        antes = list(f["carimbos"])
        g = com_registo_novo(f)
        uai.selar(g)
        self.assertEqual(g["carimbos"][:len(antes)], antes)
        self.assertEqual(len(g["carimbos"]), len(antes) + 1)
        self.assertEqual(uai.carimbo_quebrado(g), [])

    def test_a_cabeca_da_pessoa_tambem_sela(self):
        """Numa pessoa, o nome e o ofício e a autorização entram no primeiro selo."""
        p = pessoa()
        uai.selar(p)
        self.assertEqual(uai.carimbo_quebrado(p), [])
        p["pessoa"]["oficio"] = "outro"
        self.assertTrue(any("não fecha" in e for e in uai.carimbo_quebrado(p)))

    def test_a_retirada_tambem_nao_se_apaga(self):
        p = pessoa()
        p["retirada"] = {"quando": "2026-11-24", "pedido_por": "ele"}
        uai.selar(p)
        self.assertEqual(uai.carimbo_quebrado(p), [])
        sem = copy.deepcopy(p)
        del sem["retirada"]
        self.assertTrue(any("retirada" in e for e in uai.carimbo_quebrado(sem)))

    def test_o_selo_comprido_ou_torto_e_recusado(self):
        f = ficha()
        f["carimbos"] = ["nao-e-um-selo"]
        self.assertTrue(uai.carimbo_quebrado(f))
        f["carimbos"] = "isto-não-é-uma-lista"
        self.assertTrue(uai.carimbo_quebrado(f))


class ALeiSemGit(unittest.TestCase):

    def test_receber_recusa_uma_ficha_adulterada_e_nao_grava(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            f = ficha()
            uai.selar(f)
            f["registos"][0]["texto"] = "afinal está tudo bem"
            (pasta / "ponte.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
            reg = {"tipo": "contado", "epoca": "anos 80", "entrou": "2026-11-21",
                   "texto": "passava o trem", "fonte": {"descricao": "minha avó contava"}}
            id_, erros = uai.receber({"acrescentar_a": "ponte", "registo": reg}, pasta)
            self.assertTrue(any("carimbo" in e for e in erros), erros)
            guardada = json.loads((pasta / "ponte.json").read_text(encoding="utf-8"))
            self.assertEqual(len(guardada["registos"]), 1, "não podia gravar por cima")

    def test_receber_acrescenta_e_sela_de_novo(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            f = ficha()
            uai.selar(f)
            (pasta / "ponte.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
            antes = list(f["carimbos"])
            reg = {"tipo": "contado", "epoca": "anos 80", "entrou": "2026-11-21",
                   "texto": "passava o trem", "fonte": {"descricao": "minha avó contava"}}
            id_, erros = uai.receber({"acrescentar_a": "ponte", "registo": reg}, pasta)
            self.assertEqual(erros, [])
            guardada = json.loads((pasta / "ponte.json").read_text(encoding="utf-8"))
            self.assertEqual(guardada["carimbos"][:len(antes)], antes)
            self.assertEqual(uai.carimbo_quebrado(guardada), [])

    def test_receber_uma_ficha_nova_ja_nasce_selada(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            reg = {"tipo": "falta saber", "data": "2026-11-21", "entrou": "2026-11-21",
                   "texto": "quem limpa?", "fonte": {"descricao": "pergunta de quem passa"}}
            id_, erros = uai.receber({"lugar": {"nome": "Praça do Rosário"}, "registos": [reg]}, pasta)
            self.assertEqual((id_, erros), ("praca-do-rosario", []))
            guardada = json.loads((pasta / "praca-do-rosario.json").read_text(encoding="utf-8"))
            self.assertIn("carimbos", guardada, "a ficha nova tem de nascer com o carimbo próprio")
            self.assertEqual(uai.carimbo_quebrado(guardada), [])

    def test_prever_entrega_denuncia_a_ficha_adulterada(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            f = ficha()
            uai.selar(f)
            f["registos"][0]["texto"] = "mudado"
            (pasta / "ponte.json").write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
            reg = {"tipo": "contado", "epoca": "anos 80", "entrou": "2026-11-21",
                   "texto": "passava o trem", "fonte": {"descricao": "minha avó contava"}}
            _, erros, _ = uai.prever_entrega({"acrescentar_a": "ponte", "registo": reg}, pasta, FOTOS)
            self.assertTrue(any("carimbo" in e for e in erros), erros)


if __name__ == "__main__":
    unittest.main()
