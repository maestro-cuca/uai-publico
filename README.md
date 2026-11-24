# UAI — uma biblioteca viva de uma cidade

**UAI** (Unidade de Acompanhamento e Informação) é um programa — e uma ideia: **nenhum lugar da cidade
deve ser esquecido, e quem conta uma história não vira dado.**

Feita em **Passos, Minas Gerais**, por gente que queria o contrário de um museu parado:
um mapa que **floresce**, **pede cuidado** e mostra **o que ainda falta saber** — com a data e a fonte
ao lado de cada coisa.

## O que está aqui

| parte | o que é |
|---|---|
| `uai.py` | o motor: valida as fichas, recebe histórias, constrói o sítio, a mesa do curador e o cartão |
| `folha.py` | **a folha só** — mete a cidade inteira num ficheiro que abre sem servidor e sem internet |
| `ouvir.py` | a **ponte de voz**: recebe um áudio, transcreve, e propõe a entrega (nunca a inventa) |
| `mapa.py` | desenha o chão, o relevo, os lugares e as jornadas |
| `estatico/` | o mapa, o CSS, o diálogo de quem conta, as escolhas de acessibilidade |
| `fichas/` | as fichas dos **lugares** — sem dono, com procedência |
| `gente/` | as fichas das **pessoas** — e a lei que as governa (`LEIAME.md`) |
| `tests/` | **171 testes** que prendem as leis, não só o código |

## Como correr

```bash
python3 uai.py construir saida/          # constrói o sítio inteiro
python3 uai.py folha cidade.html         # a cidade num só ficheiro (abre offline)
python3 uai.py fila                      # a fila de entregas, com parecer antes de decidir
python3 -m unittest discover -s tests    # os testes
```

## A lei da casa — lê antes de usar

**O código é do mundo. A vida de quem contou, não.**

Está em **[`LEI-DA-CASA.md`](LEI-DA-CASA.md)**, e são seis linhas: uma pessoa só entra com a sua
palavra · quem contou não ganha nome · quem sai, sai · nada se apaga · com procedência · a casa não é
de quem guarda.

> **Se copiares este programa para a tua cidade, copia também aquela página.**
> O código sem estas seis linhas é só um banco de dados.

## Um selo não se empresta

Um registo só se diz **«verificado»** com prova à vista — link ou foto do acervo. Sem prova, a porta
recusa a ficha, e o que já está na estante passa a **«prova por juntar»**: o selo não se mostra.

## A vez de quem não vê

O critério primeiro deste projeto é **quem não lê um ecrã**. Não se resolve cegueira com letra maior:
resolve-se dando **outra porta** — áudio no WhatsApp, cartão de bolso em preto no branco com um QR,
um botão que lê a página em voz alta («ouvir», com o motor de voz do próprio aparelho), modo «só texto»
para leitor de tela, e contraste **medido** (não escolhido a olho).

## Estado

**Protótipo vivo**, feito em novembro de 2026. Números medidos, não estimados: 171 testes, dois lugares
no mapa, uma ficha de pessoa, e a cidade inteira num ficheiro de 3,3 MB.

## Créditos

**Maestro Cuca** (Passos, MG) — e a casa que ajudou a pensar: dezoito vozes entre deuses gregos,
filósofos e cientistas, com o Mago à frente.

O que a UAI deve a quem está em **[`CREDITOS.md`](CREDITOS.md)**: as fotografias (Creative Commons,
autor e licença de cada uma, com o link), o mapa (© colaboradores do OpenStreetMap, base sob ODbL),
o relevo (Terrain Tiles / SRTM, cortesia do U.S. Geological Survey) e as letras (SIL OFL 1.1).

**Licença:** MIT para o código (ver [`LICENSE`](LICENSE)). A ética, essa, não é MIT: está em `LEI-DA-CASA.md`.
