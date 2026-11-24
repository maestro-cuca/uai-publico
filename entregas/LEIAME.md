# entregas/ — a fila da UAI

As histórias que o povo manda pelo WhatsApp (ou por e-mail) **pousam aqui antes de entrar no acervo.**
Um ficheiro por entrega — o texto inteiro que chegou, com o `(ficha: {…})` no fim, tal como o site gera.
*(O `uai.py` aceita também o JSON puro.)*

## O ciclo

```bash
python3 uai.py fila                          # ver o que espera, com ✓/✗ e os erros à frente
python3 uai.py aceitar <ficheiro>            # aceita → grava em fichas/ → move para aceites/
python3 uai.py devolver <ficheiro> "motivo"  # devolve com o motivo registado → devolvidas/
```

**Nada entra sem passar a régua.** *O `aceitar` corre os mesmos validadores do `receber`: sem fonte, não
entra; registo antigo alterado, não entra; nome de quem contou, não entra.* **E a decisão fica
registada** — *era isso que faltava: antes o `receber` gravava directo e ninguém escrevia porquê.*

**O motivo de devolver não é castigo:** é o que se diz a quem contou, para que a história possa voltar
em ordem. *As devolvidas ficam em `devolvidas/`, com os motivos em `devolvidas/motivos.md`.*
