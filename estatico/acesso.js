/* UAI — acesso para toda a gente.
   Letra maior, contraste alto, só texto (sem mapa: mais leve, melhor para
   leitor de tela) e ouvir a página em voz alta. As escolhas ficam guardadas
   neste aparelho — e só nele. Quem está com poupança de dados começa no modo
   leve, sem o mapa, e pode pedi-lo com um toque. */
(() => {
  "use strict";
  const raiz = document.documentElement;
  const OPCOES = ["letra-grande", "contraste", "so-texto"];
  const ler = (k) => { try { return localStorage.getItem("uai:" + k); } catch { return null; } };
  const guardar = (k, v) => { try { localStorage.setItem("uai:" + k, v); } catch { /* sem memória: vale só agora */ } };

  for (const o of OPCOES) if (ler(o) === "1") raiz.classList.add(o);
  const poupanca = navigator.connection && navigator.connection.saveData;
  if (poupanca && ler("so-texto") === null) raiz.classList.add("so-texto", "modo-leve");

  // ───── ouvir ─────
  const voz = "speechSynthesis" in window ? window.speechSynthesis : null;
  function vozPt() {
    const vozes = voz ? voz.getVoices() : [];
    return vozes.find((v) => /pt[-_]BR/i.test(v.lang)) || vozes.find((v) => /^pt/i.test(v.lang)) || null;
  }
  function falar(textos, aoAcabar) {
    if (!voz) return;
    voz.cancel();
    const lista = textos.map((t) => t.replace(/\s+/g, " ").trim()).filter(Boolean);
    lista.forEach((t, i) => {
      const u = new SpeechSynthesisUtterance(t);
      u.lang = "pt-BR";
      const v = vozPt();
      if (v) u.voice = v;
      u.rate = 0.95;
      if (i === lista.length - 1 && aoAcabar) u.onend = aoAcabar;
      voz.speak(u);
    });
  }
  // o que se lê: o essencial da página, pela ordem, sem os botões
  function textosDaPagina() {
    const sel = "h1, .sub, .cartao h3, .cartao .linha-estado, .registo .topo, .registo > p:first-of-type, .onde, .avisos, .leis li, .conversa .msg";
    return [...document.querySelectorAll(`.painel :is(${sel})`)]
      .filter((el) => el.offsetParent !== null)
      .map((el) => el.textContent);
  }
  window.uaiFalar = (t) => { if (raiz.classList.contains("voz-ligada")) falar([t]); };

  // ───── a barra ─────
  function montarBarra() {
    const painel = document.querySelector(".painel");
    if (!painel) return;
    const barra = document.createElement("div");
    barra.className = "acesso";
    barra.setAttribute("role", "toolbar");
    barra.setAttribute("aria-label", "Jeitos de ver e ouvir");
    const botoes = [
      ["letra-grande", "Aa", "letra maior"],
      ["contraste", "◐", "contraste"],
      ["so-texto", "☰", "só texto"],
    ];
    for (const [classe, simbolo, rotulo] of botoes) {
      const b = document.createElement("button");
      b.type = "button";
      b.innerHTML = `<span aria-hidden="true">${simbolo}</span> ${rotulo}`;
      b.setAttribute("aria-pressed", raiz.classList.contains(classe));
      b.addEventListener("click", () => {
        const liga = !raiz.classList.contains(classe);
        raiz.classList.toggle(classe, liga);
        raiz.classList.remove("modo-leve");
        b.setAttribute("aria-pressed", liga);
        guardar(classe, liga ? "1" : "0");
        if (classe === "so-texto" && !liga) document.dispatchEvent(new Event("uai:mapa"));
      });
      barra.append(b);
    }
    if (voz) {
      const b = document.createElement("button");
      b.type = "button";
      const rot = (a) => (b.innerHTML = a ? '<span aria-hidden="true">■</span> parar' : '<span aria-hidden="true">▶</span> ouvir');
      rot(false);
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => {
        const ligar = !raiz.classList.contains("voz-ligada");
        raiz.classList.toggle("voz-ligada", ligar);
        b.setAttribute("aria-pressed", ligar);
        rot(ligar);
        if (ligar) falar(textosDaPagina(), () => { raiz.classList.remove("voz-ligada"); rot(false); b.setAttribute("aria-pressed", "false"); });
        else voz.cancel();
      });
      barra.append(b);
    }
    // o fundo: verde mata, noite azul ou terra roxa — dá a volta a cada toque
    const FUNDOS = [["mata", "verde mata"], ["azul", "noite azul"], ["terra", "terra roxa"]];
    const fb = document.createElement("button");
    fb.type = "button";
    const rotFundo = () => {
      const [, nome] = FUNDOS.find(([k]) => k === (raiz.dataset.fundo || "mata"));
      fb.innerHTML = `<span aria-hidden="true">◧</span> fundo: ${nome}`;
      fb.setAttribute("aria-label", `fundo: ${nome} — tocar para trocar`);
    };
    rotFundo();
    fb.addEventListener("click", () => {
      const i = FUNDOS.findIndex(([k]) => k === (raiz.dataset.fundo || "mata"));
      const [prox] = FUNDOS[(i + 1) % FUNDOS.length];
      if (prox === "mata") delete raiz.dataset.fundo; else raiz.dataset.fundo = prox;
      guardar("fundo", prox);
      rotFundo();
    });
    barra.append(fb);
    painel.prepend(barra);
    if (raiz.classList.contains("modo-leve")) {
      const aviso = document.createElement("p");
      aviso.className = "aviso-leve";
      aviso.innerHTML = 'Modo leve: o mapa não foi carregado para poupar a sua internet. <button type="button">mostrar o mapa</button>';
      aviso.querySelector("button").addEventListener("click", () => {
        raiz.classList.remove("so-texto", "modo-leve");
        guardar("so-texto", "0");
        aviso.remove();
        barra.querySelector("button:nth-child(3)").setAttribute("aria-pressed", "false");
        document.dispatchEvent(new Event("uai:mapa"));
      });
      barra.after(aviso);
    }
  }

  // ───── a pega da folha (23/11/2026) ─────
  // O ::before desenhava a barra e não aceitava gesto — parecia e não era (achado do Atena).
  // Agora a barra é um botão: toca para estender, arrasta para cima ou para baixo, e o teclado chega.
  function ligarPega() {
    const pega = document.getElementById("pega");
    const painel = document.getElementById("conteudo");
    if (!pega || !painel) return;
    const so = matchMedia("(max-width: 899px)");
    const alta = () => painel.classList.contains("alta");
    function mudar(vai) {
      painel.classList.toggle("alta", vai);
      document.documentElement.classList.toggle("folha-alta", vai);
      pega.setAttribute("aria-expanded", String(vai));
      pega.setAttribute("aria-label", vai ? "recolher a folha" : "estender a folha");
      if (!vai) painel.focus({ preventScroll: true });
    }
    let y0 = null, mexeu = false;
    pega.addEventListener("click", () => {
      if (!so.matches) return;
      if (mexeu) { mexeu = false; return; }   // foi arrasto, não toque
      mudar(!alta());
    });
    pega.addEventListener("pointerdown", (ev) => {
      if (!so.matches) return;
      y0 = ev.clientY; mexeu = false;
      try { pega.setPointerCapture(ev.pointerId); } catch (e) { /* sem captura, segue */ }
    });
    pega.addEventListener("pointermove", (ev) => {
      if (y0 === null) return;
      const d = ev.clientY - y0;
      if (Math.abs(d) > 8) mexeu = true;
      if (d > 40 && alta()) mudar(false);
      if (d < -40 && !alta()) mudar(true);
    });
    pega.addEventListener("pointerup", () => { y0 = null; });
    pega.addEventListener("pointercancel", () => { y0 = null; });
    pega.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowUp") { ev.preventDefault(); mudar(true); }
      if (ev.key === "ArrowDown") { ev.preventDefault(); mudar(false); }
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { montarBarra(); ligarPega(); });
  } else { montarBarra(); ligarPega(); }
})();
