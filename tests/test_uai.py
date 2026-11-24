"""As leis da casa, testadas. Correr da raiz: python3 -m unittest discover tests"""
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mapa  # noqa: E402
import uai  # noqa: E402

FOTOS = {"ponte.jpg": {"ficheiro": "ponte.jpg", "autor": "x", "licenca": "CC BY 4.0"}}


def ficha(**mais):
    f = {
        "lugar": {"nome": "Ponte", "referencia": "centro"},
        "registos": [
            {
                "data": "2026-11-05", "entrou": "2026-11-19", "tipo": "verificado", "estado": "pede cuidado",
                "texto": "o guarda-corpo tem um vão", "fonte": {"descricao": "vi no local", "foto": "ponte.jpg"},
            }
        ],
    }
    f.update(mais)
    return f


def validar(f, id_="ponte"):
    return uai.validar_ficha(id_, f, FOTOS)


class ComProcedencia(unittest.TestCase):
    def test_ficha_boa_passa_sem_avisos(self):
        self.assertEqual(validar(ficha()), ([], []))

    def test_sem_fonte_nao_entra(self):
        f = ficha()
        del f["registos"][0]["fonte"]
        erros, _ = validar(f)
        self.assertTrue(any("procedência" in x for x in erros), erros)

    def test_link_tem_de_ser_publico(self):
        f = ficha()
        f["registos"][0]["fonte"] = {"descricao": "foto", "url": "file:///home/alguem/foto.jpg"}
        erros, _ = validar(f)
        self.assertTrue(any("link público" in x for x in erros), erros)

    def test_foto_tem_de_estar_no_acervo(self):
        f = ficha()
        f["registos"][0]["fonte"]["foto"] = "inventada.jpg"
        erros, _ = validar(f)
        self.assertTrue(any("não está no acervo" in x for x in erros), erros)

    def test_verificado_sem_prova_e_aviso_nao_erro(self):
        f = ficha()
        del f["registos"][0]["fonte"]["foto"]
        erros, avisos = validar(f)
        self.assertEqual(erros, [])
        self.assertTrue(any("prova por juntar" in x for x in avisos), avisos)


class NuncaQuemContou(unittest.TestCase):
    def test_campos_de_identificacao_sao_recusados(self):
        for onde in ("ficha", "registo", "fonte"):
            f = ficha()
            alvo = {"ficha": f, "registo": f["registos"][0], "fonte": f["registos"][0]["fonte"]}[onde]
            alvo["autor"] = "Fulano"
            erros, _ = validar(f)
            self.assertTrue(any("nunca quem contou" in x for x in erros), (onde, erros))


class DataEEstado(unittest.TestCase):
    def test_epoca_em_palavras_vale_no_lugar_da_data(self):
        f = ficha()
        r = f["registos"][0]
        del r["data"]
        r["epoca"] = "quando a banda tocava aos domingos"
        self.assertEqual(validar(f)[0], [])

    def test_sem_data_nem_epoca_nao_entra(self):
        f = ficha()
        del f["registos"][0]["data"]
        self.assertTrue(validar(f)[0])

    def test_estado_fora_do_vocabulario(self):
        f = ficha()
        f["registos"][0]["estado"] = "à espera de quem o faça cantar"
        self.assertTrue(any("estado deve ser" in x for x in validar(f)[0]))

    def test_data_depois_de_entrar_e_impossivel(self):
        f = ficha()
        f["registos"][0]["data"] = "2026-12-01"
        self.assertTrue(any("depois de ter entrado" in x for x in validar(f)[0]))

    def test_situacao_calcula_estado_desde_e_dias(self):
        f = ficha()
        # 24/11/2026: um «verificado» passou a precisar de prova — este leva link
        f["registos"].append({"data": "2026-11-20", "entrou": "2026-11-20", "tipo": "verificado", "estado": "em obra",
                              "texto": "começou a obra",
                              "fonte": {"descricao": "vi", "url": "https://exemplo.org/obra"}})
        f["registos"].append({"data": "2026-11-20", "entrou": "2026-11-20", "tipo": "falta saber",
                              "texto": "até quando?", "fonte": {"descricao": "pergunta"}})
        s = uai.situacao(f, dt.date(2026, 11, 30), FOTOS)
        self.assertEqual((s["estado"], s["desde"], s["dias"], s["perguntas"]), ("em obra", "2026-11-20", 10, 1))
        self.assertEqual(s["cuidado"], [])

    def test_zelo_broto_e_adormecida(self):
        f = ficha()
        f["registos"][0]["tipo"] = "leitura"
        s = uai.situacao(f, dt.date(2027, 3, 1))
        self.assertIn("broto", s["cuidado"])
        self.assertIn("adormecida", s["cuidado"])


class NuncaApagar(unittest.TestCase):
    def test_acrescentar_e_permitido(self):
        antiga = ficha()
        nova = copy.deepcopy(antiga)
        nova["registos"].append({**antiga["registos"][0], "entrou": "2026-11-20"})
        self.assertEqual(uai.nunca_apagar(antiga, nova), [])

    def test_mudar_ou_tirar_um_registo_e_recusado(self):
        antiga = ficha()
        mudada = copy.deepcopy(antiga)
        mudada["registos"][0]["texto"] = "afinal está tudo bem"
        self.assertTrue(uai.nunca_apagar(antiga, mudada))
        vazia = copy.deepcopy(antiga)
        vazia["registos"] = []
        self.assertTrue(uai.nunca_apagar(antiga, vazia))

    def test_registo_novo_nao_entra_no_meio(self):
        f = ficha()
        f["registos"].append({**f["registos"][0], "entrou": "2026-11-01", "data": "2026-11-01"})
        self.assertTrue(any("só se acrescentam no fim" in x for x in validar(f)[0]))

    def test_carimbo_denuncia_mudanca_antiga(self):
        f = ficha()
        f["registos"].append({**f["registos"][0], "entrou": "2026-11-20"})
        antes = uai.carimbos(f)
        f["registos"][0]["texto"] += "."
        depois = uai.carimbos(f)
        self.assertNotEqual(antes[0], depois[0])
        self.assertNotEqual(antes[-1], depois[-1])
        self.assertEqual(depois, uai.carimbos(json.loads(json.dumps(f))), "o carimbo é estável: mesma ficha, mesmo número")


class Receber(unittest.TestCase):
    def test_acrescenta_no_fim_e_recusa_o_que_nao_presta(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            base = ficha()
            del base["registos"][0]["fonte"]["foto"]  # o acervo real não tem ponte.jpg
            (pasta / "ponte.json").write_text(json.dumps(base), encoding="utf-8")
            reg = {"tipo": "contado", "epoca": "anos 80", "entrou": "2026-11-21", "texto": "passava o trem",
                   "fonte": {"descricao": "minha avó contava"}}
            id_, erros = uai.receber({"acrescentar_a": "ponte", "registo": reg}, pasta)
            self.assertEqual(erros, [])
            self.assertEqual(json.loads((pasta / "ponte.json").read_text())["registos"][-1], reg)
            _, erros = uai.receber({"acrescentar_a": "ponte", "registo": {**reg, "fonte": {}}}, pasta)
            self.assertTrue(erros)
            self.assertEqual(len(json.loads((pasta / "ponte.json").read_text())["registos"]), 2)

    def test_lugar_novo_vira_ficheiro_com_nome_limpo(self):
        with tempfile.TemporaryDirectory() as d:
            reg = {"tipo": "falta saber", "data": "2026-11-21", "entrou": "2026-11-21", "texto": "quem limpa?",
                   "fonte": {"descricao": "pergunta de quem passa"}}
            id_, erros = uai.receber({"lugar": {"nome": "Praça do Rosário"}, "registos": [reg]}, Path(d))
            self.assertEqual((id_, erros), ("praca-do-rosario", []))


class PeloWhatsApp(unittest.TestCase):
    def test_a_mensagem_inteira_vira_ficha(self):
        msg = ("História para a UAI — Passos\n\nLugar: Praça Trindade\nO que conto: pipoqueiro (aos domingos)\n\n"
               '(ficha: {"lugar":{"nome":"Praça Trindade"},"registos":[{"tipo":"contado","texto":"pipoqueiro (aos domingos)",'
               '"epoca":"anos 80","entrou":"2026-11-20","fonte":{"descricao":"minha família contava"}}]})')
        with tempfile.TemporaryDirectory() as d:
            id_, erros = uai.receber(uai.ler_entrega(msg), Path(d))
            self.assertEqual((id_, erros), ("praca-trindade", []))

    def test_json_puro_tambem(self):
        self.assertEqual(uai.ler_entrega('{"acrescentar_a": "x"}'), {"acrescentar_a": "x"})


class OSite(unittest.TestCase):
    def test_texto_e_escapado(self):
        f = ficha()
        f["registos"][0]["texto"] = "<script>alert(1)</script>"
        out = uai.pagina_lugar("ponte", f, dt.date(2026, 11, 20), [])
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;", out)

    def test_constroi_com_as_fichas_do_repositorio(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(uai.construir(Path(d) / "site", dt.date(2026, 11, 20)), [])
            inicio = (Path(d) / "site" / "index.html").read_text(encoding="utf-8")
            self.assertIn("A primeira história", inicio)
            for id_ in uai.carregar():
                self.assertTrue((Path(d) / "site" / f"{id_}.html").exists())
            svg = (Path(d) / "site" / "mapa.svg").read_text(encoding="utf-8")
            moldura = mapa.carregar_regiao()["moldura"]
            for id_, o in mapa.carregar_onde().items():
                if not uai.no_mapa(o, moldura):
                    self.assertNotIn(f'href="{id_}.html"', svg)
                    self.assertIn("fora do mapa", (Path(d) / "site" / f"{id_}.html").read_text(encoding="utf-8"))
                    continue
                self.assertIn(f'href="{id_}.html"', svg)
                pag = (Path(d) / "site" / f"{id_}.html").read_text(encoding="utf-8")
                self.assertIn(f'data-foco="{id_}"', pag)
            for f in ("uai.css", "mapa.js", "relevo.jpg", "fontes/fontes.css"):
                self.assertTrue((Path(d) / "site" / f).exists(), f)
            self.assertIn("OpenStreetMap", inicio, "a atribuição do mapa (ODbL) tem de estar à vista")
            self.assertIn('href="#conteudo"', inicio, "pular o mapa: o primeiro link da página")
            deixar = (Path(d) / "site" / "deixar.html").read_text(encoding="utf-8")
            self.assertIn('id="conversa"', deixar)
            self.assertIn("conversa.js", deixar)
            for f in ("acesso.js", "conversa.js"):
                self.assertTrue((Path(d) / "site" / f).exists(), f)


MOLDURA = {"norte": -20.650, "sul": -20.775, "oeste": -46.685, "leste": -46.555, "kx": 104_000, "ky": 110_574}


def onde(**mais):
    o = {"lat": -20.7194, "lon": -46.6105, "precisao": "exato", "fonte": {"descricao": "vi no OpenStreetMap"}}
    o.update(mais)
    return {"ponte": o}


class OMapa(unittest.TestCase):
    def test_ponto_com_fonte_entra(self):
        self.assertEqual(uai.validar_onde(onde(), {"ponte": ficha()}, MOLDURA), [])

    def test_ponto_sem_fonte_nao_entra(self):
        erros = uai.validar_onde(onde(fonte={}), {"ponte": ficha()}, MOLDURA)
        self.assertTrue(any("procedência" in x for x in erros), erros)

    def test_duvida_diz_o_seu_tamanho(self):
        erros = uai.validar_onde(onde(precisao="aproximado"), {"ponte": ficha()}, MOLDURA)
        self.assertTrue(any("raio_m" in x for x in erros), erros)
        self.assertEqual(uai.validar_onde(onde(precisao="aproximado", raio_m=300), {"ponte": ficha()}, MOLDURA), [])

    def test_fora_do_mapa_e_ficha_que_nao_existe(self):
        self.assertTrue(any("longe demais" in x for x in uai.validar_onde(onde(lat=-19.9), {"ponte": ficha()}, MOLDURA)))
        perto = onde(lat=-20.64, lon=-46.50)  # o Glória: fora da moldura, mas não é engano
        self.assertEqual(uai.validar_onde(perto, {"ponte": ficha()}, MOLDURA), [])
        self.assertFalse(uai.no_mapa(perto["ponte"], MOLDURA))
        self.assertTrue(any("não há ficha" in x for x in uai.validar_onde(onde(), {}, MOLDURA)))

    def test_nunca_quem_contou_tambem_no_mapa(self):
        erros = uai.validar_onde(onde(autor="Fulano"), {"ponte": ficha()}, MOLDURA)
        self.assertTrue(any("nunca quem contou" in x for x in erros), erros)

    def test_caminho_relativo(self):
        self.assertEqual(mapa.caminho([0, 0, 10, 0, 10, -5]), "M0 0l10 0 0-5")
        self.assertEqual(mapa.caminho([5, 5, 5, 5]), "", "um traço sem comprimento não se desenha")
        self.assertEqual(mapa.caminho([0, 0, 3, 4, 0, 0], fechar=True), "M0 0l3 4-3-4z")

    def test_pino_escapa_o_nome_e_mostra_a_duvida(self):
        regiao = {"moldura": {"largura": 1000, "altura": 1000}, "camadas": {k: [] for k in (
            "agua", "matas", "campos", "parques", "urbano", "rios", "riachos", "vias_grandes", "vias", "ruas", "pontes", "lugares", "curvas")}}
        lg = {"id": "ponte", "nome": "<b>Ponte</b>", "estado": "pede cuidado", "x": 10, "y": 20, "raio": 300,
              "precisao": "aproximado", "rotulo": "Ponte"}
        out = mapa.svg(regiao, [lg])
        self.assertNotIn("<b>Ponte", out)
        self.assertIn('class="lugar e-pede-cuidado" href="ponte.html"', out)
        self.assertIn('data-raio="300"', out)
        self.assertIn('<ellipse class="area"/><g class="pino" data-x="10" data-y="20">', out)

    def test_o_mapa_leva_o_que_os_jeitos_de_ver_precisam(self):
        regiao = {"moldura": {"largura": 1000, "altura": 1000, "oeste": -46.6, "norte": -20.6, "kx": 104000, "ky": 110000},
                  "camadas": {k: [] for k in ("agua", "matas", "campos", "parques", "urbano", "rios", "riachos",
                                              "vias_grandes", "vias", "ruas", "pontes", "lugares", "curvas")}}
        regiao["camadas"]["marcos"] = [{"nome": "Praça <X>", "cat": "praca", "x": 5, "y": 5}]
        lg = {"id": "coreto", "nome": "Coreto", "estado": "em obra", "x": 10, "y": 20, "raio": 0,
              "precisao": "exato", "rotulo": "Coreto"}
        out = mapa.svg(regiao, [lg])
        self.assertIn('data-oeste="-46.6" data-norte="-20.6" data-kx="104000" data-ky="110000"', out)
        self.assertIn('data-estado="em-obra"', out)
        self.assertIn('data-cat="praca" data-nome="Praça &lt;X&gt;"', out)

    def test_o_cartao_de_ver_e_pouco_e_nao_guarda_quem(self):
        cartao = uai.cartao_ver()
        self.assertEqual(cartao.count('data-modo="'), 3)
        self.assertEqual(cartao.count('data-camada="'), 5)
        self.assertIn('data-estado="nenhum"', cartao)
        for k in mapa.CATEGORIAS:
            self.assertIn(f'data-cat="{k}"', cartao)
        # o tempo também se filtra — senão adormecer e florescer ficam iguais no mapa
        for s in ("floresce", "adormeceu", "tem-raiz"):
            self.assertIn(f'data-estado="{s}"', cartao)

    def _mapa_com_tempo(self):
        """Três fichas no mapa: uma de ontem, uma de há dois anos, uma firme."""
        def com(entrou, nome):
            return ficha(lugar={"nome": nome, "referencia": ""},
                         registos=[{"data": entrou, "entrou": entrou, "tipo": "contado",
                                    "texto": "contado em voz", "fonte": {"descricao": "disse"}}])
        hoje = dt.date(2026, 11, 24)
        fichas = {"ponte": com("2026-11-20", "Ponte"),      # 4 dias → floresce
                  "poco": com("2024-11-24", "Poço"),        # 2 anos → adormeceu
                  "coreto": com("2026-09-22", "Coreto")}    # ~63 dias → tem raiz
        onde = {i: {"lat": -20.70, "lon": -46.60, "precisao": "exato"} for i in fichas}
        return fichas, uai.lugares_no_mapa(fichas, onde, MOLDURA, hoje), hoje

    def test_adormecidas_do_mapa_sao_as_do_guardiao(self):
        """O teste-fecho: o mapa e a mesa do guardião contam as mesmas adormecidas."""
        fichas, lugares, hoje = self._mapa_com_tempo()
        no_mapa = {lg["id"] for lg in lugares if lg["estado"] == "adormeceu"}
        conta = uai.conta_do_acervo(fichas, hoje)
        self.assertEqual(no_mapa, {i for i, _ in conta["adormecidas"]})
        self.assertEqual(no_mapa, {"poco"})

    def test_o_mapa_leva_a_idade_decidida_pela_regua(self):
        """O mapa não faz uma segunda régua: só transporta o que a régua disse."""
        _, lugares, _ = self._mapa_com_tempo()
        tempos = {lg["id"]: lg["tempo"] for lg in lugares}
        self.assertEqual(tempos, {"ponte": "floresce", "poco": "adormeceu", "coreto": "tem raiz"})

    def test_ontem_e_dois_anos_atras_nao_sao_o_mesmo_pino(self):
        _, lugares, _ = self._mapa_com_tempo()
        out = mapa.svg(_regiao(), lugares)
        self.assertIn('data-tempo="floresce"', out)
        self.assertIn('data-tempo="adormeceu"', out)
        self.assertIn('<circle class="tempo t-floresce"', out)
        self.assertIn('<circle class="tempo t-adormeceu"', out)
        # «tem raiz» não desenha mancha: nem fresca nem esquecida
        self.assertEqual(out.count('<circle class="tempo'), 2)



def _regiao(**camadas):
    base = {k: [] for k in ("agua", "matas", "campos", "parques", "urbano", "rios", "riachos",
                            "vias_grandes", "vias", "ruas", "pontes", "lugares", "curvas", "marcos")}
    base.update(camadas)
    return {"moldura": {"largura": 100, "altura": 100}, "camadas": base}


class OChaoEmPixel(unittest.TestCase):
    def test_um_quadrado_de_mata_vira_quadradinhos_de_mata(self):
        ch = mapa.chao(_regiao(matas=[[20, 20, 60, 20, 60, 60, 20, 60]]), cel=10)
        self.assertEqual((ch["colunas"], ch["linhas"]), (10, 10))
        mata = mapa.C["mata"]
        dentro = {(x, y) for y in range(10) for x in range(10) if ch["dados"][y * 10 + x] == mata}
        self.assertEqual(dentro, {(x, y) for x in range(2, 6) for y in range(2, 6)})

    def test_a_rua_passa_por_cima_do_chao(self):
        ch = mapa.chao(_regiao(matas=[[0, 0, 100, 0, 100, 100, 0, 100]], ruas=[[5, 55, 95, 55]]), cel=10)
        linha = ch["dados"][5 * 10:6 * 10]
        self.assertEqual(set(linha), {mapa.C["rua"]})

    def test_o_chao_e_so_classes(self):
        ch = mapa.chao(_regiao(agua=[[0, 0, 50, 0, 50, 50, 0, 50]]), cel=10)
        self.assertTrue(set(ch["dados"]) <= set(range(len(mapa.CLASSES))))


class OChaoEmQuadrinhos(unittest.TestCase):
    def _grade(self, lado=400, passo=20):
        ruas = [[0, y, lado, y] for y in range(10, lado, passo)] + [[x, 0, x, lado] for x in range(10, lado, passo)]
        reg = _regiao(ruas=ruas, matas=[[20, 20, 60, 20, 60, 60, 20, 60]])
        reg["moldura"] = {"largura": lado, "altura": lado}
        return reg

    def test_onde_ha_muita_rua_a_cidade_vira_uma_mancha_de_bordas_redondas(self):
        reg = self._grade()
        t = mapa.tracos(reg, mapa.chao(reg))
        self.assertTrue(t["cidade"])
        anel = t["cidade"][0]
        self.assertEqual(len(anel) % 2, 0)
        pontos = list(zip(anel[::2], anel[1::2]))
        self.assertTrue(all(0 <= x <= 400 and 0 <= y <= 400 for x, y in pontos))
        # arredondada: nenhum canto de régua (três pontos seguidos em ângulo reto exato) sobra
        retos = sum(1 for i in range(len(pontos)) if (pontos[i - 1][0] == pontos[i][0]) != (pontos[i - 1][1] == pontos[i][1])
                    and (pontos[i][0] == pontos[(i + 1) % len(pontos)][0]) != (pontos[i][1] == pontos[(i + 1) % len(pontos)][1])
                    and (pontos[i - 1][0] == pontos[i][0]) != (pontos[i][0] == pontos[(i + 1) % len(pontos)][0]))
        self.assertEqual(retos, 0)

    def test_o_traco_leva_as_camadas_tal_como_vem(self):
        reg = self._grade()
        t = mapa.tracos(reg, mapa.chao(reg))
        self.assertEqual(t["matas"], [[20, 20, 60, 20, 60, 60, 20, 60]])
        self.assertEqual(len(t["ruas"]), len(reg["camadas"]["ruas"]))
        self.assertTrue(all(isinstance(n, int) for p in t["ruas"] for n in p))

    def test_sem_ruas_nao_ha_cidade(self):
        reg = _regiao(matas=[[0, 0, 100, 0, 100, 100, 0, 100]])
        self.assertEqual(mapa.tracos(reg, mapa.chao(reg))["cidade"], [])


class ARedeEAsJornadas(unittest.TestCase):
    def test_ruas_que_se_cruzam_sem_no_em_comum_ligam_se(self):
        # duas ruas em cruz, sem vértice partilhado (como fica o mapa simplificado)
        adj = mapa.rede(_regiao(ruas=[[0, 50, 100, 50], [50, 0, 50, 100]]))
        self.assertIn((50, 50), adj)
        d, cam = mapa.rota(adj, (0, 50), (50, 0))
        self.assertAlmostEqual(d, 100)
        self.assertEqual(cam, [(0, 50), (50, 50), (50, 0)])

    def test_ponta_solta_gruda_na_rua_perto(self):
        adj = mapa.rede(_regiao(ruas=[[0, 50, 100, 50], [50, 70, 50, 100]]))  # a segunda acaba a 20 m da primeira
        d, cam = mapa.rota(adj, (0, 50), (50, 100))
        self.assertTrue(cam)
        self.assertAlmostEqual(d, 50 + 20 + 30)

    def test_jornada_segue_as_ruas_e_diz_a_distancia(self):
        r = _regiao(ruas=[[0, 50, 100, 50], [50, 0, 50, 100]],
                    marcos=[{"nome": "Praça A", "cat": "praca", "x": 0, "y": 52}, {"nome": "Igreja B", "cat": "fe", "x": 52, "y": 0}])
        js, erros = mapa.tracar_jornadas({"volta": {"nome": "Volta", "convite": "…", "fonte": {"descricao": "teste"},
                                                    "paradas": [{"marco": "Praça A"}, {"marco": "Igreja B"}]}}, r, {})
        self.assertEqual(erros, [])
        self.assertEqual(js[0]["metros"], 100)
        self.assertEqual(js[0]["pontos"][0], (0, 52))
        self.assertIn((50, 50), js[0]["pontos"])

    def test_jornada_sem_fonte_ou_com_parada_que_nao_existe_nao_entra(self):
        r = _regiao(ruas=[[0, 50, 100, 50]], marcos=[{"nome": "Praça A", "cat": "praca", "x": 0, "y": 50}])
        js, erros = mapa.tracar_jornadas({"x": {"nome": "X", "paradas": [{"marco": "Praça A"}, {"marco": "Lugar Inventado"}]}}, r, {})
        self.assertEqual(js, [])
        self.assertTrue(any("sem fonte" in e for e in erros))
        self.assertTrue(any("Lugar Inventado" in e for e in erros))

    def test_ficha_como_parada_tem_de_ter_lugar_no_mapa(self):
        r = _regiao(ruas=[[0, 50, 100, 50]], marcos=[{"nome": "Praça A", "cat": "praca", "x": 0, "y": 50}])
        _, erros = mapa.tracar_jornadas({"x": {"nome": "X", "fonte": {"descricao": "t"},
                                               "paradas": [{"marco": "Praça A"}, {"ficha": "sem-ponto"}]}}, r, {})
        self.assertTrue(any("sem-ponto" in e for e in erros))

    def test_a_pe(self):
        self.assertEqual(mapa.a_pe(26), "uns 26 min a pé")
        self.assertEqual(mapa.a_pe(75), "uma hora e 15 min a pé")
        self.assertEqual(mapa.distancia(2208), "2,2 km")


class AsFichasDoRepositorio(unittest.TestCase):
    def test_todas_passam_nas_leis(self):
        fotos = uai.fotos_do_acervo()
        for id_, f in uai.carregar().items():
            self.assertEqual(uai.validar_ficha(id_, f, fotos)[0], [], id_)

    def test_as_jornadas_do_repositorio_tracam_se(self):
        regiao, onde = mapa.carregar_regiao(), mapa.carregar_onde()
        lugares = uai.lugares_no_mapa(uai.carregar(), onde, regiao["moldura"], uai.dt.date.today())
        js, erros = mapa.tracar_jornadas(mapa.carregar_jornadas(), regiao, {l["id"]: l for l in lugares})
        self.assertEqual(erros, [])
        self.assertEqual(len(js), len(mapa.carregar_jornadas()))

    def test_os_pontos_do_mapa_tem_fonte(self):
        self.assertEqual(uai.validar_onde(mapa.carregar_onde(), uai.carregar(), mapa.carregar_regiao()["moldura"]), [])


class ADestinoEDasHistorias(unittest.TestCase):
    """23/11/2026 — o defeito que os dezoito apanharam: a história não chegava a ninguém."""

    def test_o_contato_declarado_tem_whatsapp_so_digitos(self):
        c = uai.carregar_contato()
        self.assertTrue(c["nome"])
        self.assertTrue(c["whatsapp"], "sem destinatário declarado, a história não chega a ninguém")
        self.assertRegex(c["whatsapp"], r"^\d+$")

    def test_o_contato_do_repositorio_esta_em_ordem(self):
        d = json.loads((uai.RAIZ / "contato.json").read_text(encoding="utf-8"))
        self.assertIn("whatsapp", d)
        self.assertIn("_leia", d, "um ficheiro declarado tem de dizer o que é")

    def test_o_deixar_carrega_o_contato_antes_da_conversa(self):
        pagina = uai.pagina_deixar(uai.carregar())
        self.assertIn("contato.js", pagina)
        self.assertLess(pagina.index("contato.js"), pagina.index("conversa.js"),
                        "o destino tem de estar carregado antes de a história ser montada")

    def test_a_mesa_nao_e_para_o_povo(self):
        fichas = uai.carregar()
        regiao = mapa.carregar_regiao()
        pagina = uai.pagina_curador(fichas, mapa.carregar_onde(), {}, uai.dt.date.today(),
                                    regiao["moldura"], regiao)
        self.assertIn("Mesa do guardião", pagina)
        self.assertIn("cartao-num", pagina)


class AFilaDaCuradoria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fichas = Path(self.tmp.name) / "fichas"
        self.fichas.mkdir()
        self.entregas = Path(self.tmp.name) / "entregas"
        self.entregas.mkdir()
        self._fichas, self._entregas = uai.FICHAS, uai.ENTREGAS
        uai.FICHAS, uai.ENTREGAS = self.fichas, self.entregas

    def tearDown(self):
        uai.FICHAS, uai.ENTREGAS = self._fichas, self._entregas
        self.tmp.cleanup()

    def test_uma_entrega_boa_preve_sem_erros(self):
        entrega = {"lugar": {"nome": "Ponte"}, "registos": [dict(ficha()["registos"][0])]}
        id_, erros, avisos = uai.prever_entrega(entrega, self.fichas, FOTOS)
        self.assertEqual(erros, [])
        self.assertEqual(id_, "ponte")

    def test_uma_entrega_sem_fonte_e_apanhada_antes_de_gravar(self):
        entrega = {"lugar": {"nome": "Ponte"}, "registos": [{"tipo": "verificado", "texto": "nada"}]}
        id_, erros, _ = uai.prever_entrega(entrega, self.fichas, FOTOS)
        self.assertTrue(erros, "sem fonte não entra — e a mesa tem de o dizer antes da decisão")
        self.assertEqual(list(self.fichas.iterdir()), [], "prever não pode gravar nada")

    def test_acrescentar_a_uma_ficha_que_nao_existe_e_recusado(self):
        id_, erros, _ = uai.prever_entrega({"acrescentar_a": "nao-existe", "registo": {}}, self.fichas, FOTOS)
        self.assertTrue(erros)
        self.assertEqual(id_, "nao-existe")

    def test_a_fila_so_ve_ficheiros_de_entrega(self):
        (self.entregas / "a.json").write_text("{}", encoding="utf-8")
        (self.entregas / "leia.md").write_text("nada", encoding="utf-8")
        (self.entregas / "pasta").mkdir()
        pend = uai._entregas_pendentes()
        self.assertEqual([f.name for f in pend], ["a.json"])


class OsNumerosDoGuardiao(unittest.TestCase):
    def test_os_numeros_saem_todos_do_motor(self):
        hoje = uai.dt.date(2026, 11, 23)
        c = uai.conta_do_acervo({"ponte": ficha()}, hoje)
        self.assertIn("adormecidas", c)
        self.assertIn("brotos", c)
        self.assertIn("contestadas", c)
        self.assertEqual(c["perguntas_abertas"], 0)

    def test_uma_ficha_parada_ha_90_dias_entra_no_silencio(self):
        f = ficha()
        f["registos"][0]["entrou"] = "2026-01-01"
        # A ficha de teste usa foto «ponte.jpg», e o acervo real não a tem —
        # a régua do estado devolve «pede cuidado» (prova por juntar), que tem precedência.
        # Para o teste do silêncio, usamos um registo que não pede prova: contado.
        f["registos"][0] = {"tipo": "contado", "data": "2026-01-01", "entrou": "2026-01-01",
                            "texto": "dizem que era assim", "fonte": {"descricao": "de ouvir dizer"}}
        c = uai.conta_do_acervo({"ponte": f}, uai.dt.date(2026, 11, 23))
        self.assertIn("ponte", [i for i, _ in c["adormecidas"]])

    def test_uma_ficha_so_de_leitura_e_broto(self):
        f = ficha()
        f["registos"] = [{"data": "2026-11-20", "entrou": "2026-11-20", "tipo": "leitura",
                          "texto": "parece", "fonte": {"descricao": "eu"} }]
        c = uai.conta_do_acervo({"ponte": f}, uai.dt.date(2026, 11, 23))
        self.assertIn("ponte", c["brotos"])


class APortaDeQuemNaoVe(unittest.TestCase):
    """23/11/2026 — pedido do navegante, a pensar em quem não vê."""

    def test_o_telefone_e_dito_como_se_fala(self):
        self.assertEqual(uai.telefone_bonito("5535991002375"), "(35) 99100-2375")
        self.assertEqual(uai.telefone_bonito("3535221100"), "(35) 3522-1100")
        self.assertEqual(uai.telefone_bonito(""), "")

    def test_o_link_do_whatsapp_leva_o_destino_dentro(self):
        z = uai._zap({"nome": "UAI", "whatsapp": "5535991002375", "email": ""}, "olá mundo")
        self.assertTrue(z.startswith("https://wa.me/5535991002375?text="))
        self.assertIn("ol%C3%A1%20mundo", z)

    def test_sem_destino_declarado_nao_se_inventa_um_link(self):
        self.assertEqual(uai._zap({"nome": "UAI", "whatsapp": "", "email": ""}), "https://wa.me/")

    def test_o_cartao_e_preto_no_branco_e_letra_grande(self):
        cartao = uai.pagina_cartao({"nome": "UAI · Passos", "whatsapp": "5535991002375", "email": ""})
        self.assertIn("background:#fff", cartao)
        self.assertIn("color:#000", cartao)
        self.assertIn("(35) 99100-2375", cartao)
        self.assertIn("Pode falar", cartao)
        self.assertIn("qr/contar-uai.png", cartao)
        self.assertIn("Nunca com o nome de quem contou", cartao)

    def test_o_qr_existe_no_repositorio(self):
        qr = uai.RAIZ / "estatico" / "qr" / "contar-uai.png"
        self.assertTrue(qr.exists(), "sem o ficheiro, o cartão aponta para o vazio")
        self.assertGreater(qr.stat().st_size, 300)

    def test_a_pagina_de_contar_abre_a_porta_por_voz(self):
        pagina = uai.pagina_deixar(uai.carregar())
        self.assertIn("ouvir-tudo", pagina)
        self.assertIn("Mande um <b>áudio</b>", pagina)
        self.assertIn(uai.telefone_bonito(uai.carregar_contato()["whatsapp"]), pagina)
        self.assertLess(pagina.index("por-voz"), pagina.index('id="conversa"'),
                        "a porta de voz vem antes do formulário — quem não lê precisa de a encontrar primeiro")


if __name__ == "__main__":
    unittest.main()
