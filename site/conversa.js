/* UAI — contar uma história, conversando.
   Uma pergunta de cada vez, em palavras simples. Responde-se escrevendo,
   tocando numa opção ou falando. No fim, a ficha sai pronta para mandar
   pelo WhatsApp — a quem a pessoa quiser, sem conta nem senha.
   Não é uma inteligência artificial: é um roteiro, sempre o mesmo, e nada
   sai do aparelho sem a pessoa tocar em «mandar». As leis valem aqui
   também: sem fonte não fecha, e contato de ninguém entra. */
(() => {
  "use strict";
  const caixa = document.getElementById("conversa");
  if (!caixa) return;
  const dados = JSON.parse(document.getElementById("conversa-dados").textContent);
  const log = caixa.querySelector(".log");
  const opcoes = caixa.querySelector(".opcoes");
  const form = caixa.querySelector("form");
  const entrada = form.querySelector("textarea");
  const mic = form.querySelector(".mic");
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hojeISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };

  // ───── falar e ouvir ─────
  function uai(texto) {
    const m = document.createElement("p");
    m.className = "msg uai";
    m.textContent = texto;
    log.append(m);
    rolar();
    if (window.uaiFalar) window.uaiFalar(texto);
  }
  function pessoa(texto) {
    const m = document.createElement("p");
    m.className = "msg pessoa";
    m.textContent = texto;
    log.append(m);
    rolar();
  }
  const rolar = () => log.lastElementChild?.scrollIntoView({ block: "nearest", behavior: RM ? "auto" : "smooth" });

  // ───── respostas ─────
  let esperando = null; // a função que recebe a próxima resposta
  function perguntar(texto, { escolhas = [], livre = true, dica = "" } = {}) {
    uai(texto);
    opcoes.replaceChildren();
    for (const [rotulo, valor] of escolhas) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = rotulo;
      b.addEventListener("click", () => responder(rotulo, valor));
      opcoes.append(b);
    }
    form.hidden = !livre;
    entrada.placeholder = dica || "escreva aqui…";
    entrada.value = "";
    if (livre && !matchMedia("(pointer: coarse)").matches) entrada.focus();
    else opcoes.querySelector("button")?.focus();
    return new Promise((resolve) => (esperando = resolve));
  }
  function responder(mostrar, valor) {
    if (!esperando) return;
    pessoa(mostrar);
    const r = esperando;
    esperando = null;
    opcoes.replaceChildren();
    r(valor === undefined ? mostrar : valor);
  }
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const t = entrada.value.trim();
    if (t) responder(t);
  });
  entrada.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  // microfone: só aparece se o navegador souber transcrever
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Rec && mic) {
    mic.hidden = false;
    let rec = null;
    mic.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new Rec();
      rec.lang = "pt-BR";
      rec.interimResults = true;
      const antes = entrada.value ? entrada.value.trim() + " " : "";
      rec.onresult = (ev) => {
        entrada.value = antes + [...ev.results].map((r) => r[0].transcript).join(" ");
      };
      rec.onend = () => { rec = null; mic.classList.remove("ouvindo"); mic.setAttribute("aria-pressed", "false"); entrada.focus(); };
      rec.onerror = () => rec && rec.stop();
      mic.classList.add("ouvindo");
      mic.setAttribute("aria-pressed", "true");
      rec.start();
    });
  }

  // ───── as leis, em conversa ─────
  // e-mail, CPF, celular (9xxxx-xxxx) e fixo com DDD — sem confundir «1987-1990»
  const CONTATO = [/\S+@\S+\.\S+/, /\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b/, /\b9\d{4}[-\s]?\d{4}\b/, /\(?\b\d{2}\)?\s?[2-5]\d{3}[-\s]?\d{4}\b/];
  const temContato = (t) => CONTATO.some((r) => r.test(t));
  async function semContato(pergunta, opts) {
    for (;;) {
      const t = await perguntar(pergunta, opts);
      if (typeof t !== "string" || !temContato(t)) return t;
      pergunta = "Parece que aí tem telefone, e-mail ou documento. A UAI num guarda quem contou — pode contar de novo, sem isso?";
    }
  }

  const COMO = [
    ["Eu vi", "verificado", ["vi no local, hoje", "tenho foto"]],
    ["Eu vivi, ou me contaram", "contado", ["eu vivi isso", "minha família contava", "ouvi de vizinhos"]],
    ["É o que eu acho", "leitura", ["é a minha impressão, de quem passa por lá"]],
    ["É uma pergunta", "falta saber", ["pergunta de quem mora perto"]],
  ];
  const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

  function quando(t) {
    const s = String(t).trim().toLowerCase();
    if (s === "hoje") return { data: hojeISO() };
    if (/^\d{4}(-\d{2}(-\d{2})?)?$/.test(s)) return { data: s };
    const br = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (br) return { data: `${br[3]}-${br[2].padStart(2, "0")}-${br[1].padStart(2, "0")}` };
    if (/^\d{4}$/.test(s)) return { data: s };
    return { epoca: String(t).trim() || "sem data dita" };
  }
  const dizerQuando = (q) => {
    if (q.epoca) return q.epoca;
    const [a, m, d] = q.data.split("-");
    return d ? `${+d} de ${MESES[+m - 1]} de ${a}` : m ? `${MESES[+m - 1]} de ${a}` : a;
  };

  // ───── o roteiro ─────
  async function conversar() {
    log.replaceChildren();
    caixa.querySelector(".fim").hidden = true;
    const q = new URLSearchParams(location.search);
    const daUrl = dados.lugares.find((l) => l.id === q.get("lugar"));
    let lugar = null;

    uai("Uai, chegue aqui, sô! Aqui cê conta um caso de um canto de Passos — uma praça, uma rua, uma ponte, uma beira de rio. Num precisa dizer o seu nome, não.");
    if (daUrl) {
      const ok = await perguntar(`É sobre ${daUrl.nome}, certo?`, { escolhas: [["Sim", true], ["Outro lugar", false]], livre: false });
      if (ok) lugar = { id: daUrl.id, nome: daUrl.nome };
    } else if (q.get("nome")) {
      const nome = q.get("nome").slice(0, 120);
      const ok = await perguntar(`É sobre ${nome}, certo?`, { escolhas: [["Sim", true], ["Outro lugar", false]], livre: false });
      if (ok) lugar = { nome };
    }
    while (!lugar) {
      const r = await perguntar("Sobre que canto cê quer contar?", {
        escolhas: dados.lugares.map((l) => [l.nome, l]),
        dica: "o nome como o povo conhece: ex. Praça da Matriz, Ponte do Rio Grande",
      });
      if (typeof r === "object") lugar = { id: r.id, nome: r.nome };
      else if (r.trim().length >= 3) lugar = { nome: r.trim() };
      else uai("Escreve o nome com mais jeito, sô — do jeito que o povo chama o lugar.");
    }

    let texto = "";
    while (texto.length < 5) {
      texto = await semContato(`O que você quer contar sobre ${lugar.nome}? Pode escrever ou, se preferir, tocar no microfone e falar.`, {
        dica: "o que aconteceu, o que falta, o que você vê, do que se lembra…",
      });
      texto = String(texto).trim();
      if (texto.length < 5) uai("Conta um pouquim mais, nem que seja uma frase.");
    }

    const [, tipo, fontes] = await perguntar("E como cê sabe disso?", {
      escolhas: COMO.map((c) => [c[0], c]), livre: false,
    });

    const qd = quando(await perguntar("Quando foi isso? Pode ser um ano, uma data — ou do seu jeito, tipo «quando eu era menino».", {
      escolhas: [["Hoje", "hoje"], ["Não sei", "sem data dita"]],
      dica: "ex.: 1987, 15/03/2024, «no tempo da banda»",
    }));
    if (qd.data && qd.data > hojeISO()) qd.epoca = dizerQuando(qd), delete qd.data;

    let fonte = "";
    while (!fonte) {
      fonte = String(await semContato("De onde vem esse caso? A UAI sempre diz a fonte — mas nunca o nome de quem contou, não.", {
        escolhas: fontes.map((f) => [f, f]),
        dica: "ex.: vi hoje; jornal de 1962; minha avó contava",
      })).trim();
    }

    let estado = null;
    if (tipo !== "falta saber") {
      estado = await perguntar("E como o lugar tá hoje?", {
        escolhas: [
          ["Está bonito, vivo", "floresce"], ["Pede cuidado", "pede cuidado"],
          ["Falta fazer", "por fazer"], ["Em obra", "em obra"], ["Não sei dizer", null],
        ],
        livre: false,
      });
    }

    // a ficha, no formato que o «uai.py receber» entende
    const reg = { tipo, texto, ...qd, entrou: hojeISO() };
    if (estado) reg.estado = estado;
    reg.fonte = { descricao: fonte };
    const ficha = lugar.id ? { acrescentar_a: lugar.id, registo: reg } : { lugar: { nome: lugar.nome }, registos: [reg] };

    const COMO_DIZ = Object.fromEntries(COMO.map((c) => [c[1], c[0].toLowerCase()]));
    const resumo = [
      `Lugar: ${lugar.nome}`,
      `O que conto: ${texto}`,
      `Como sei: ${COMO_DIZ[tipo]}`,
      `Quando: ${dizerQuando(qd)}`,
      `De onde vem: ${fonte}`,
      estado ? `Como está: ${estado}` : "",
    ].filter(Boolean).join("\n");
    uai("Pronto! Ficou assim — dá uma olhada se num tem nome de ninguém:");
    const r = document.createElement("pre");
    r.className = "msg resumo";
    r.textContent = resumo;
    log.append(r);
    if (window.uaiFalar) window.uaiFalar(resumo);

    const tecnica = JSON.stringify(ficha);
    const mensagem = `História para a UAI — Passos\n\n${resumo}\n\n(ficha: ${tecnica})`;
    const fim = caixa.querySelector(".fim");
    fim.hidden = false;

    // 23/11/2026 — o destinatário estava EM FALTA: o botão apontava para `wa.me` sem número, e a
    // história não chegava a ninguém («o fluxo morre no copiar»). Agora vem declarado no
    // contato.json, num sítio só e à vista.
    const c = window.UAI_CONTATO || {};
    const so_digitos = String(c.whatsapp || "").replace(/\D/g, "");
    const zap = fim.querySelector(".zap");
    zap.href = so_digitos
      ? "https://wa.me/" + so_digitos + "?text=" + encodeURIComponent(mensagem)
      : "https://wa.me/?text=" + encodeURIComponent(mensagem);
    const mail = fim.querySelector(".email");
    if (mail && c.email) {
      mail.hidden = false;
      mail.href = "mailto:" + c.email + "?subject=" + encodeURIComponent("História para a UAI — Passos") +
                  "&body=" + encodeURIComponent(mensagem);
    }
    const destino = fim.querySelector("#destino");
    if (destino) {
      destino.textContent = so_digitos
        ? `Esta história vai para ${c.nome || "a UAI"}. O «copiar» fica ali para quem preferir outro caminho.`
        : "Escolhe pra quem mandar — o site ainda num tem destinatário declarado.";
    }
    uai(so_digitos
      ? `Pronto. O botão manda para ${c.nome || "a UAI"} — e o «copiar» serve se preferir outro caminho.`
      : "Agora é só mandar. Pelo WhatsApp cê escolhe pra quem — pra quem guarda a UAI no seu bairro, ou pra um grupo.");
    fim.querySelector(".tecnica").textContent = JSON.stringify(ficha, null, 2);
    fim.querySelector(".copiar").onclick = async (ev) => {
      try { await navigator.clipboard.writeText(mensagem); ev.target.textContent = "copiado ✓"; }
      catch { ev.target.textContent = "selecione o texto e copie"; }
    };
    form.hidden = true;
    rolar();
    fim.querySelector(".zap").focus();
  }

  caixa.querySelector(".de-novo").addEventListener("click", () => {
    history.replaceState(null, "", location.pathname);
    conversar();
  });
  caixa.hidden = false;
  document.getElementById("formulario")?.removeAttribute("open");
  conversar();
  // ───── ouvir o que fazer (23/11/2026) ─────
  const ouvir = document.getElementById("ouvir-tudo");
  if (ouvir) ouvir.addEventListener("click", () => {
    const guiao = "Pra contar um caso tem dois caminhos. Um: escrever aqui, respondendo"
      + " às perguntas. Dois: mandar um áudio no WhatsApp da UAI, pro número que tá"
      + " nesta página. Num precisa de conta, nem de senha. E o nome de quem conta num"
      + " fica registado — o caso é da cidade, não seu.";
    if (window.uaiFalar) window.uaiFalar(guiao);
    else ouvir.textContent = "o seu aparelho não lê em voz alta — peça a alguém para ler";
  });

})();
