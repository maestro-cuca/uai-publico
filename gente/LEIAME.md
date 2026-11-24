# gente/ — a segunda metade da UAI

**A UAI nasceu de lugares. Mas o que esta casa tem de mais rico é gente.** *(Cinco vozes do Olimpo viram-no sozinhas, a 23/11/2026.)*

*Aqui não entram verbetes: entram pessoas.*

---

## A lei desta metade — e é diferente da lei dos lugares

1. **Uma pessoa entra só com a sua palavra.** *Sem `autorizou` (por, quando, como) a ficha não entra — **erro, não aviso**.*
2. **O nome é o que ela usa.** *Não o do registo civil, não o que os papéis dizem. E se ela se apresentar de outra maneira, é essa que vem primeiro (`se_chama`).*
3. **A autorização fica à vista.** *Quem lê sabe porque é que esta pessoa está aqui: porque disse que sim, no dia tal, desta maneira.*
4. **Quem sai, sai.** *A ficha ganha `retirada` e deixa de aparecer no sítio — **e é a única excepção à lei «nada se apaga»**. Os lugares não têm esse direito; as pessoas têm. A retirada fica registada, para a história não ser reescrita.*
5. **A rua e o número não entram.** *`onde_vive` diz a terra ou o bairro — nunca a porta de casa. O `validar` avisa se vir um número.*
6. **O nome de quem contou continua proibido.** *Uma pessoa entra com o **seu** nome porque autorizou. Quem conta uma história sobre outra pessoa não ganha nome nenhum. São coisas diferentes, e a confusão entre elas é que faz os arquivos parecerem coleccionadores.*

## O que uma ficha de pessoa tem

```json
{
  "pessoa":     { "nome": "…", "se_chama": "…", "oficio": "…", "onde_vive": "…", "referencia": "…" },
  "autorizou":  { "por": "…", "quando": "AAAA-MM-DD", "como": "disse em voz | escreveu | a família autorizou | publica ele mesmo" },
  "registos":   [ … os mesmos de qualquer ficha: data, tipo, texto, fonte … ],
  "retirada":   { "quando": "AAAA-MM-DD", "pedido_por": "…" }
}
```

**Só `pessoa.nome`, `autorizou` e `registos` são obrigatórios.** *O `retirada` só existe para quem sai.*

## Como se trabalha

```
python3 uai.py gente                    # quem está de pé, quem saiu, e o que falta
python3 uai.py validar                  # as duas metades passam pela mesma régua
python3 uai.py construir site/          # o sítio nasce com gente.html e gente/<id>.html
```

**Uma pessoa também pode entrar por áudio:** *manda o áudio no WhatsApp da UAI, o guardião guarda-o em `entregas/audios/`, e a ponte de voz transcreve.* **Mas a autorização tem de vir dita por ela** — e há-de estar dita na transcrição, ou pedida à parte. *Sem isso, fica em `POR-AUTORIZAR-…` e não entra.*
