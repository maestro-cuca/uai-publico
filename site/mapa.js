/* UAI — o mapa vivo, em quadrinhos. Sem bibliotecas.
   O chão vem de hq.bin: o traço de cada coisa (rua, mata, água, prédio…) em metros,
   desenhado num canvas como numa HQ — cor chapada, contorno de tinta, retícula —
   com as cores do fundo escolhido ou do contraste; por baixo, chao.bin (quadradinhos
   de 10 m) dá só o relevo. Por cima, mapa.svg traz só o
   que se toca e se lê (lugares, convites, nomes, jornadas); cada coisa guarda a
   sua posição em metros e o JS põe-na no ecrã.
   A vista é {x, y, m, inc}: o ponto (em metros) no centro da área livre, quantos
   metros cabem num píxel, e a inclinação (0 = de cima, 1 = inclinada, como os
   jogos antigos: cada linha do ecrã é uma faixa do chão). A área livre desconta
   a folha de leitura (à esquerda no computador, em baixo no telefone) e o cartão
   «jeitos de ver» quando está aberto. */
(() => {
  "use strict";
  const cena = document.getElementById("cena");
  if (!cena) return;
  const raiz = document.documentElement;
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const LADO = matchMedia("(min-width: 900px)");
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  const versao = document.currentScript?.dataset.versao || "";
  const comVersao = (f) => f + (versao ? "?v=" + versao : "");
  let pedido = false;
  // a UAI numa folha só (23/11/2026): quando o chão vem dentro do ficheiro, não se pede nada a ninguém
  const ENL = window.UAI_INLINE || null;
  const deBase64 = (b) => Uint8Array.from(atob(b), (c) => c.charCodeAt(0));
  const pegar = (nome) => {
    if (ENL && ENL[nome] != null) {
      return Promise.resolve(nome === "mapa.svg" ? ENL[nome] : deBase64(ENL[nome]));
    }
    return nome === "mapa.svg"
      ? fetch(comVersao(nome)).then((r) => (r.ok ? r.text() : Promise.reject(r.status)))
      : fetch(comVersao(nome)).then(inflar);
  };
  async function inflar(r) {
    if (!r.ok) throw new Error(String(r.status));
    const fluxo = r.body.pipeThrough(new DecompressionStream("deflate"));
    return new Uint8Array(await new Response(fluxo).arrayBuffer());
  }
  // no modo «só texto» o mapa nem se baixa; pede-se quando a pessoa o quiser
  function carregar() {
    if (pedido) return;
    pedido = true;
    if (!ENL && !("DecompressionStream" in window)) { cena.classList.add("sem-mapa"); return; }
    Promise.all([
      pegar("mapa.svg"),
      pegar("chao.bin"),
      pegar("hq.bin").then((b) => JSON.parse(new TextDecoder().decode(b))),
    ]).then(([texto, dados, hq]) => montar(texto, dados, hq))
      .catch(() => cena.classList.add("sem-mapa"));
  }
  if (raiz.classList.contains("so-texto")) document.addEventListener("uai:mapa", carregar, { once: true });
  else carregar();

  function montar(texto, dados, hq) {
    cena.insertAdjacentHTML("afterbegin", texto);
    const svg = cena.querySelector("svg");
    const tela = document.createElement("canvas");
    tela.className = "chao";
    tela.setAttribute("aria-hidden", "true");
    cena.insertBefore(tela, svg);
    const ctx = tela.getContext("2d", { alpha: false });
    const d = svg.dataset;
    const W = +d.largura, H = +d.altura, CEL = +d.cel, COL = +d.colunas, LIN = +d.linhas;
    const NS = "http://www.w3.org/2000/svg";
    const ctr = cena.querySelector(".controles");
    const cartao = document.getElementById("ver");
    const botaoVer = ctr && ctr.querySelector('[data-acao="ver"]');

    const lugares = [...svg.querySelectorAll(".lugar")];
    const pinos = lugares.map((a) => a.querySelector(".pino"));
    const marcos = [...svg.querySelectorAll(".marco")];
    const icones = marcos.map((a) => a.querySelector(".icone"));
    const rotulos = [...svg.querySelectorAll(".m-rotulos text")];
    const paradas = [...svg.querySelectorAll(".parada")];
    const jornadas = [...svg.querySelectorAll(".jornada")].map((g) => ({
      g, id: g.dataset.id, borda: g.querySelector(".j-borda"), traco: g.querySelector(".j-traco"),
      pontos: g.dataset.pontos.split(" ").map((p) => p.split(",").map(Number)),
    }));
    const pos = (el) => ({ x: +el.dataset.x, y: +el.dataset.y });
    const escala = document.getElementById("escala");
    const M_MIN = 0.6, M_MAX = 40, PHI = (58 * Math.PI) / 180;
    let v = { x: W / 2, y: H / 2, m: 20, inc: 0 };
    let tam = { w: 1, h: 1 };
    let explorar = false;
    let aqui = null;       // {x, y} em metros — só neste aparelho, nunca sai dele
    let marcaAqui = null;
    let aoMover = null;    // quem quer saber que a vista mudou (a lista «perto daqui»)
    let jornadaAtiva = null;
    let camadas = { relevo: true, nomes: true, convites: true, gente: true, jornadas: true };

    // ───── o chão: classes → cores do tema ─────
    const CLASSES = ["terra", "cidade", "campo", "parque", "mata", "praca", "agua", "rua", "via", "grande", "ponte", "predio", "rio", "riacho"];
    const TONS = [0.9, 0.95, 1, 1.035];
    const mips = [0, 1, 2].map((n) => {
      const c = document.createElement("canvas");
      c.width = Math.ceil(COL / 2 ** n);
      c.height = Math.ceil(LIN / 2 ** n);
      return c;
    });
    let sombra = null;  // Uint8Array COL×LIN com o tom do relevo (0–3), quando pedido
    let corPapel = "#f4efe3";
    const tinta = document.createElement("canvas").getContext("2d");
    function rgb(cor) {
      tinta.fillStyle = "#000";
      tinta.fillStyle = cor || "#000";
      const h = tinta.fillStyle;  // o navegador normaliza para #rrggbb
      return h.startsWith("#") ? [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) : [0, 0, 0];
    }
    function colorir() {
      const cs = getComputedStyle(raiz);
      corPapel = (cs.getPropertyValue("--px-fundo").trim() || cs.getPropertyValue("--papel").trim()) || corPapel;
      const pal = CLASSES.map((k) => rgb(cs.getPropertyValue("--px-" + k).trim()));
      const img = new ImageData(COL, LIN);
      const px = img.data;
      const comRelevo = camadas.relevo && sombra && !raiz.classList.contains("contraste");  // contraste alto: sem meios-tons
      // por baixo de tudo, só a terra com o relevo (suave); o resto desenha-se em traço, por cima
      for (let i = 0, j = 0; i < dados.length; i++, j += 4) {
        const p = pal[0];
        const t = comRelevo ? TONS[sombra[i]] : 1;
        px[j] = p[0] * t; px[j + 1] = p[1] * t; px[j + 2] = p[2] * t; px[j + 3] = 255;
      }
      mips[0].getContext("2d").putImageData(img, 0, 0);
      for (let n = 1; n < mips.length; n++) {
        const c = mips[n].getContext("2d");
        c.imageSmoothingEnabled = true;
        c.imageSmoothingQuality = "high";
        c.drawImage(mips[n - 1], 0, 0, mips[n].width, mips[n].height);
      }
      tintasHQ(cs);
      aplicar();
    }
    // o relevo: a imagem sombreada, reduzida aos quadradinhos e em quatro tons — degraus, como num jogo
    let relevoPedido = false;
    function pedirRelevo() {
      if (relevoPedido) return;
      relevoPedido = true;
      const im = new Image();
      im.onload = () => {
        // em blocos de 2×2 quadradinhos: degraus mais largos, menos grão
        const bw = Math.ceil(COL / 2), bh = Math.ceil(LIN / 2);
        const c = document.createElement("canvas");
        c.width = bw; c.height = bh;
        const g = c.getContext("2d", { willReadFrequently: true });
        g.imageSmoothingQuality = "high";
        g.drawImage(im, 0, 0, bw, bh);
        const px = g.getImageData(0, 0, bw, bh).data;
        const lum = new Uint8Array(COL * LIN), hist = new Uint32Array(256);
        for (let i = 0; i < lum.length; i++) {
          const j = (((i / COL) >> 1) * bw + ((i % COL) >> 1)) * 4;
          lum[i] = (px[j] * 0.3 + px[j + 1] * 0.59 + px[j + 2] * 0.11) | 0;
          hist[lum[i]]++;
        }
        // os cortes pelos quantis: 12% mais escuro, 40%, 85% — e o resto ao sol
        const cortes = [0.12, 0.4, 0.85].map((q) => { let s = 0, k = 0; while (k < 255 && (s += hist[k]) < q * lum.length) k++; return k; });
        sombra = new Uint8Array(lum.length);
        for (let i = 0; i < lum.length; i++) sombra[i] = lum[i] <= cortes[0] ? 0 : lum[i] <= cortes[1] ? 1 : lum[i] <= cortes[2] ? 2 : 3;
        colorir();
      };
      im.src = (window.UAI_INLINE && window.UAI_INLINE["relevo.jpg"]) || comVersao("relevo.jpg");  // a folha traz o relevo dentro do ficheiro (23/11/2026)
    }


    // ───── o chão em quadrinhos: cor chapada, contorno de tinta, retícula ─────
    // Cada camada vem em metros; projeta-se ponto a ponto (uma reta continua reta
    // também inclinada). As ruas agrupam-se pela distância, para a largura encolher ao longe.
    const caixaHQ = (p) => {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < p.length; i += 2) {
        if (p[i] < x0) x0 = p[i]; if (p[i] > x1) x1 = p[i];
        if (p[i + 1] < y0) y0 = p[i + 1]; if (p[i + 1] > y1) y1 = p[i + 1];
      }
      return { p, x0, y0, x1, y1, cy: (y0 + y1) / 2 };
    };
    const T = Object.fromEntries(Object.entries(hq).map(([k, l]) => [k, l.map(caixaHQ)]));
    const WMIN = 0.15;
    let K = null, yLim = Infinity, vis = null;
    let cor = {}, tintaHQ = "#1b1a16", retinas = {};
    function retina(ponto, passo = 6, r = 1.15) {
      const c = document.createElement("canvas");
      c.width = c.height = passo;
      const g = c.getContext("2d");
      g.fillStyle = ponto;
      g.beginPath(); g.arc(passo / 2, passo / 2, r, 0, 7); g.fill();
      return ctx.createPattern(c, "repeat");
    }
    function misturar(a, b, t) {
      const [r1, g1, b1] = rgb(a), [r2, g2, b2] = rgb(b);
      return `rgb(${r1 + (r2 - r1) * t | 0},${g1 + (g2 - g1) * t | 0},${b1 + (b2 - b1) * t | 0})`;
    }
    function tintasHQ(cs) {
      const ler = (k, padrao) => cs.getPropertyValue(k).trim() || padrao;
      for (const k of CLASSES) cor[k] = ler("--px-" + k, "#888");
      const contraste = raiz.classList.contains("contraste");
      tintaHQ = contraste ? ler("--tinta", "#000") : ler("--hq-tinta", "#1b1a16");
      retinas = contraste ? {} : {
        mata: retina(misturar(cor.mata, tintaHQ, 0.45)),
        parque: retina(misturar(cor.parque, tintaHQ, 0.3), 5, 0.9),
        agua: retina(misturar(cor.agua, "#ffffff", 0.35), 7, 1.2),
        cidade: retina(misturar(cor.cidade, tintaHQ, 0.18), 4, 0.7),
      };
    }
    function P(x, y) {
      const X = x - v.x, Y = y - v.y, w = 1 - Y * K.s;
      return [K.ox + X / (K.m * w), K.oy + (Y * K.cos) / (K.m * w)];
    }
    const visivel = (f) => f.x1 >= vis.x0 && f.x0 <= vis.x1 && f.y1 >= vis.y0 && f.y0 <= vis.y1;
    // o pedaço do anel aquém do corte (inclinado, o que fica atrás de quem olha não se desenha)
    function cortarAnel(p) {
      const out = [], n = p.length / 2;
      for (let i = 0; i < n; i++) {
        const ax = p[2 * ((i + n - 1) % n)], ay = p[2 * ((i + n - 1) % n) + 1], bx = p[2 * i], by = p[2 * i + 1];
        const aDentro = ay <= yLim, bDentro = by <= yLim;
        if (aDentro !== bDentro) { const t = (yLim - ay) / (by - ay); out.push(ax + (bx - ax) * t, yLim); }
        if (bDentro) out.push(bx, by);
      }
      return out;
    }
    function anel(f) {
      const p = yLim < Infinity && f.y1 > yLim ? cortarAnel(f.p) : f.p;
      if (p.length < 6) return;
      let [x, y] = P(p[0], p[1]);
      ctx.moveTo(x, y);
      for (let i = 2; i < p.length; i += 2) { [x, y] = P(p[i], p[i + 1]); ctx.lineTo(x, y); }
      ctx.closePath();
    }
    function linha(f) {
      const p = f.p;
      let solto = true;
      for (let i = 0; i < p.length; i += 2) {
        let x = p[i], y = p[i + 1];
        if (y > yLim) {  // passou do corte: fecha o traço no corte
          if (!solto && i) { const ay = p[i - 1], ax = p[i - 2], t = (yLim - ay) / (y - ay); const q = P(ax + (x - ax) * t, yLim); ctx.lineTo(q[0], q[1]); }
          solto = true;
          continue;
        }
        if (solto && i && p[i - 1] > yLim) { const ay = p[i - 1], ax = p[i - 2], t = (yLim - ay) / (y - ay); const q = P(ax + (x - ax) * t, yLim); ctx.moveTo(q[0], q[1]); solto = false; }
        const q = P(x, y);
        if (solto) { ctx.moveTo(q[0], q[1]); solto = false; } else ctx.lineTo(q[0], q[1]);
      }
    }
    function camadaArea(nome, preencher, { tinta = 1.4, ret = null, sombra_ = 0 } = {}) {
      const l = T[nome];
      if (!l || !l.length) return;
      ctx.beginPath();
      let algum = false;
      for (const f of l) if (visivel(f)) { anel(f); algum = true; }
      if (!algum) return;
      if (sombra_) {  // a sombra chapada das HQ: o mesmo desenho, em tinta, um pouco ao lado
        ctx.save(); ctx.translate(sombra_, sombra_); ctx.fillStyle = tintaHQ; ctx.fill("evenodd"); ctx.restore();
      }
      ctx.fillStyle = preencher;
      ctx.fill("evenodd");
      if (ret) { ctx.fillStyle = ret; ctx.fill("evenodd"); }
      if (tinta) { ctx.lineWidth = tinta; ctx.strokeStyle = tintaHQ; ctx.stroke(); }
    }
    // largura em píxeis de um traço de `metros`, à distância da coisa
    const larg = (f, metros) => metros / (K.m * Math.max(WMIN, 1 - (f.cy - v.y) * K.s));
    function camadaLinha(nome, metros, corTraco, { borda = 1.3, min = 0.8, max = 40, soTinta = false, alfa = 1 } = {}) {
      const l = T[nome];
      if (!l || !l.length) return;
      // agrupa por largura (de cima, é uma só; inclinada, umas poucas)
      const grupos = new Map();
      for (const f of l) {
        if (!visivel(f)) continue;
        const w = clamp(larg(f, metros), min, max);
        const chave = Math.round(w * 4) / 4;
        if (!grupos.has(chave)) grupos.set(chave, []);
        grupos.get(chave).push(f);
      }
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.globalAlpha = alfa;
      if (borda && !soTinta) {
        ctx.strokeStyle = tintaHQ;
        for (const [w, fs] of grupos) { ctx.beginPath(); for (const f of fs) linha(f); ctx.lineWidth = w + 2 * borda; ctx.stroke(); }
      }
      ctx.strokeStyle = soTinta ? tintaHQ : corTraco;
      for (const [w, fs] of grupos) { ctx.beginPath(); for (const f of fs) linha(f); ctx.lineWidth = w; ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
    function desenharHQ(k) {
      K = k;
      yLim = k.s ? v.y + (1 - WMIN) / k.s : Infinity;
      if (k.s) vis = { x0: -Infinity, y0: -Infinity, x1: Infinity, y1: yLim };
      else {
        const folga = 40 * v.m;
        vis = { x0: v.x - k.ox * v.m - folga, x1: v.x + (tam.w - k.ox) * v.m + folga, y0: v.y - k.oy * v.m - folga, y1: v.y + (tam.h - k.oy) * v.m + folga };
      }
      const perto = v.m < 3.2, longe = v.m > 9;
      const tinta = longe ? 1 : perto ? 2.2 : 1.6;
      camadaArea("campos", cor.campo, { tinta: 0 });
      camadaArea("cidade", cor.cidade, { tinta: tinta + 0.6, ret: retinas.cidade });
      camadaArea("parques", cor.parque, { tinta, ret: retinas.parque });
      camadaArea("matas", cor.mata, { tinta, ret: retinas.mata });
      camadaArea("agua", cor.agua, { tinta: tinta + 0.4, ret: retinas.agua });
      camadaLinha("riachos", 4, cor.riacho, { min: 1.2, borda: longe ? 0.6 : 1 });
      camadaLinha("rios", 14, cor.rio, { min: 2, borda: 1.2 });
      camadaArea("pracas", cor.praca, { tinta });
      if (perto) {
        camadaArea("quadras", cor.parque, { tinta: 1.2 });
        camadaArea("piscinas", cor.agua, { tinta: 1.2 });
      }
      // as ruas: de longe, um fio de tinta (o hachurado da cidade); de perto, borda preta e miolo claro
      const rua = 7 / v.m;
      if (rua < 1.8) camadaLinha("ruas", 7, cor.rua, { soTinta: true, min: 0.5, max: 1, alfa: 0.55 });
      else camadaLinha("ruas", 7, cor.rua, { borda: 1.2, min: 1.2 });
      camadaLinha("vias", 11, cor.via, { borda: rua < 1.8 ? 0.8 : 1.3, min: 1.4 });
      camadaLinha("grandes", 18, cor.grande, { borda: 1.6, min: 2.4 });
      camadaLinha("pontes", 18, cor.ponte, { borda: 1.6, min: 2.6 });
      if (v.m < 4) camadaArea("predios", cor.predio, { tinta: 1.3, sombra_: v.m < 2 ? 3 : 2 });
    }

    // ───── a câmara ─────
    function livre() {
      const f = { esq: 0, dir: 0, baixo: 0 };
      const p = document.querySelector(".painel");
      if (p && LADO.matches) f.esq = Math.min(p.getBoundingClientRect().width + 24, tam.w / 2);
      else if (p) f.baixo = Math.max(0, tam.h - p.offsetTop);
      if (cartao && !cartao.hidden && LADO.matches) f.dir = Math.min(cartao.offsetWidth + 84, tam.w / 3);
      return f;
    }
    function camera() {
      const f = livre();
      const alto = Math.max(200, tam.h - f.baixo);
      const phi = v.inc * PHI;
      const foco = 0.9 * alto;  // em píxeis
      return {
        ox: f.esq + (tam.w - f.esq - f.dir) / 2,
        oy: alto / 2 + v.inc * 0.1 * alto,
        cos: Math.cos(phi), s: Math.sin(phi) / (foco * v.m), m: v.m, f,
      };
    }
    // do metro para o píxel (e o quanto encolhe com a distância), e de volta
    function naTela(x, y, k) {
      const X = x - v.x, Y = y - v.y, w = 1 - Y * k.s;
      if (w < 0.12) return null;
      return { x: k.ox + X / (k.m * w), y: k.oy + (Y * k.cos) / (k.m * w), w };
    }
    function noMapa(px, py, k = camera()) {
      const sy = py - k.oy, den = k.cos + sy * k.m * k.s;
      if (den < 0.04) return null;  // o céu
      const Y = (sy * k.m) / den, w = 1 - Y * k.s;
      return { x: v.x + (px - k.ox) * k.m * w, y: v.y + Y, w };
    }

    // ───── desenhar: pede-se à vontade, desenha-se uma vez por quadro ─────
    let pedidoQuadro = 0;
    function aplicar() {
      v.m = clamp(v.m, M_MIN, M_MAX);
      v.x = clamp(v.x, 0, W);
      v.y = clamp(v.y, 0, H);
      if (!pedidoQuadro) pedidoQuadro = requestAnimationFrame(quadro);
    }
    function quadro() {
      pedidoQuadro = 0;
      const k = camera();
      desenharChao(k);
      posicionar(k);
      if (aoMover) aoMover();
    }

    function desenharChao(k) {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const cw = Math.round(tam.w * dpr), ch = Math.round(tam.h * dpr);
      if (tela.width !== cw || tela.height !== ch) { tela.width = cw; tela.height = ch; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = corPapel;
      ctx.fillRect(0, 0, tam.w, tam.h);
      const nivel = (pxPorCel) => { let n = 0; while (n < mips.length - 1 && pxPorCel * 2 ** n < 0.9) n++; return n; };
      if (!k.s) {
        const n = nivel(CEL / v.m), esc = CEL * 2 ** n;
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(mips[n], (v.x - k.ox * v.m) / esc, (v.y - k.oy * v.m) / esc, (tam.w * v.m) / esc, (tam.h * v.m) / esc, 0, 0, tam.w, tam.h);
        desenharHQ(k);
        return;
      }
      // inclinada: cada linha do ecrã é uma faixa do chão, mais larga quanto mais longe
      let topo = tam.h;
      let suave = null;
      for (let py = 0; py < tam.h; py++) {
        const p = noMapa(k.ox, py + 0.5, k);
        if (!p) continue;
        if (topo === tam.h) topo = py;
        const n = nivel(CEL / (v.m * p.w)), esc = CEL * 2 ** n, img = mips[n];
        const sy = Math.floor(p.y / esc);
        if (sy < 0 || sy >= img.height) continue;
        if (!suave) { suave = true; ctx.imageSmoothingEnabled = true; }
        const xl = v.x - k.ox * v.m * p.w;
        ctx.drawImage(img, xl / esc, sy, (tam.w * v.m * p.w) / esc, 1, 0, py, tam.w, 1);
      }
      desenharHQ(k);
      // a névoa ao longe: o mapa desfaz-se no papel
      const fundo = Math.min(tam.h, topo + 0.28 * (tam.h - k.f.baixo));
      const g = ctx.createLinearGradient(0, topo, 0, fundo);
      const [r, gg, b] = rgb(corPapel);
      g.addColorStop(0, `rgb(${r},${gg},${b})`);
      g.addColorStop(1, `rgba(${r},${gg},${b},0)`);
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, tam.w, fundo);
    }

    // ───── o que fica por cima: posto no ecrã, e os nomes sem se encavalarem ─────
    const tamanho = (p) => (v.inc ? clamp(Math.pow(1 / p.w, 0.55), 0.62, 1.45) : 1);
    const PRIORIDADE = ["r-agua", "r-rio", "r-vila", "r-bairro", "r-povoado", "r-corrego", "r-ponte"];
    const FONTE = { "r-agua": 13, "r-rio": 12, "r-vila": 12, "r-bairro": 10, "r-povoado": 10, "r-corrego": 10, "r-ponte": 10 };
    rotulos.sort((a, b) => PRIORIDADE.indexOf(a.getAttribute("class")) - PRIORIDADE.indexOf(b.getAttribute("class")));
    const larguraRotulo = rotulos.map((t) => t.textContent.length * (FONTE[t.getAttribute("class")] || 10) * 0.64 + 6);
    const mostrar = (el, sim) => { if ((el.style.display !== "none") !== sim) el.style.display = sim ? "" : "none"; };

    function posicionar(k) {
      svg.setAttribute("viewBox", `0 0 ${tam.w} ${tam.h}`);
      const ocupado = [];
      const bate = (r) => ocupado.some((o) => r.x0 < o.x1 && r.x1 > o.x0 && r.y0 < o.y1 && r.y1 > o.y0);
      const dentro = (p, folga = 60) => p && p.x > -folga && p.x < tam.w + folga && p.y > -folga && p.y < tam.h + folga;

      // as jornadas: o traço pelas ruas
      for (const j of jornadas) {
        const ver_ = camadas.jornadas && (!jornadaAtiva || jornadaAtiva === j.id);
        mostrar(j.g, ver_);
        if (!ver_) continue;
        j.g.classList.toggle("ativa", jornadaAtiva === j.id);
        let dd = "", solto = true;
        for (const [x, y] of j.pontos) {
          const p = naTela(x, y, k);
          if (!p) { solto = true; continue; }
          dd += (solto ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1);
          solto = false;
        }
        j.borda.setAttribute("d", dd);
        j.traco.setAttribute("d", dd);
      }

      // os lugares da UAI primeiro: são a razão do mapa
      lugares.forEach((a, i) => {
        const pino = pinos[i], p = naTela(+pino.dataset.x, +pino.dataset.y, k);
        const vis = !a.classList.contains("filtrado") && dentro(p, 300);
        mostrar(a, vis);
        if (!vis) return;
        const e = tamanho(p);
        pino.setAttribute("transform", `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${e.toFixed(3)})`);
        const area = a.querySelector(".area");
        if (area) {
          const r = +a.dataset.raio / (k.m * p.w);
          area.setAttribute("cx", p.x.toFixed(1)); area.setAttribute("cy", p.y.toFixed(1));
          area.setAttribute("rx", r.toFixed(1)); area.setAttribute("ry", (r * k.cos).toFixed(1));
        }
        // a plaquinha vai à direita; se não couber, à esquerda; se nem assim, por baixo
        const et = pino.querySelector(".etiqueta"), lw = +et.dataset.largura;
        const lado = p.x + 16 + lw * e <= tam.w - k.f.dir - 8 ? "dir" : p.x - 16 - lw * e >= k.f.esq + 8 ? "esq" : "baixo";
        if (pino.dataset.lado !== lado) {
          pino.dataset.lado = lado;
          et.setAttribute("transform", { dir: "translate(16 0)", esq: `translate(${-16 - lw} 0)`, baixo: `translate(${-lw / 2} 26)` }[lado]);
          const g = pino.querySelector(".gente");
          if (g) g.setAttribute("transform", lado === "esq" ? "scale(-1 1)" : lado === "baixo" ? "translate(0 -50)" : "");
        }
        const x0 = lado === "esq" ? p.x - (16 + lw) * e : lado === "baixo" ? p.x - (lw / 2) * e : p.x - 16 * e;
        const x1 = lado === "dir" ? p.x + (16 + lw) * e : lado === "baixo" ? p.x + (lw / 2) * e : p.x + 16 * e;
        ocupado.push({ x0, x1, y0: p.y - 18 * e, y1: p.y + (lado === "baixo" ? 50 : 18) * e });
      });

      // as paradas da jornada aberta
      for (const pa of paradas) {
        const p = naTela(+pa.dataset.x, +pa.dataset.y, k);
        const vis = camadas.jornadas && jornadaAtiva === pa.dataset.jornada && dentro(p);
        mostrar(pa, vis);
        if (!vis) continue;
        const e = tamanho(p);
        pa.setAttribute("transform", `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${e.toFixed(3)})`);
        ocupado.push({ x0: p.x - 11 * e, x1: p.x + 11 * e, y0: p.y - 11 * e, y1: p.y + 11 * e });
      }

      // os convites: o ícone primeiro; o nome só quando perto e se couber
      const verConvites = camadas.convites && (explorar || v.m <= 14 || v.inc > 0.5);
      const perto = v.m <= (explorar ? 7 : 3);
      marcos.forEach((a, i) => {
        const ic = icones[i], p = verConvites && !a.classList.contains("filtrado") ? naTela(+ic.dataset.x, +ic.dataset.y, k) : null;
        if (!dentro(p)) { mostrar(a, false); return; }
        const e = tamanho(p);
        const bola = { x0: p.x - 10 * e, x1: p.x + 10 * e, y0: p.y - 10 * e, y1: p.y + 10 * e };
        if (bate(bola)) { mostrar(a, false); return; }
        mostrar(a, true);
        ocupado.push(bola);
        ic.setAttribute("transform", `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${e.toFixed(3)})`);
        const nome = { x0: p.x + 12 * e, x1: p.x + (12 + +ic.dataset.largura) * e, y0: p.y - 9 * e, y1: p.y + 9 * e };
        const cabe = perto && p.w > 0.55 && !bate(nome);
        a.classList.toggle("com-nome", cabe);
        if (cabe) ocupado.push(nome);
      });

      // os nomes do chão: pela ordem de importância; quem bate, esconde-se
      const zoom = v.m > 14 ? "longe" : v.m > 3 ? "meio" : "perto";
      rotulos.forEach((t, i) => {
        const cl = t.getAttribute("class");
        const cedo = zoom === "longe" && ["r-povoado", "r-corrego", "r-ponte", "r-bairro"].includes(cl);
        const p = camadas.nomes && !cedo && !(zoom === "meio" && cl === "r-ponte") ? naTela(+t.dataset.x, +t.dataset.y, k) : null;
        if (!dentro(p, 0) || p.w < 0.45) { mostrar(t, false); return; }
        const e = tamanho(p), lw = larguraRotulo[i] * e, h = (FONTE[cl] || 10) * e;
        const r = { x0: p.x - lw / 2, x1: p.x + lw / 2, y0: p.y - h, y1: p.y + h * 0.4 };
        if (bate(r)) { mostrar(t, false); return; }
        mostrar(t, true);
        ocupado.push(r);
        t.setAttribute("transform", `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${e.toFixed(3)})`);
      });

      if (marcaAqui) {
        const p = naTela(aqui.x, aqui.y, k);
        mostrar(marcaAqui, !!p);
        if (p) marcaAqui.setAttribute("transform", `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${tamanho(p).toFixed(3)})`);
      }
      svg.dataset.zoom = zoom;
      svg.dataset.gente = camadas.gente && v.m <= (explorar ? 9 : 5) ? "sim" : "nao";
      if (escala) {
        escala.hidden = v.inc > 0;  // inclinado, a régua mentiria
        const alvo = 110 * v.m;
        const passo = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000].reduce((a, b) => (Math.abs(b - alvo) < Math.abs(a - alvo) ? b : a));
        escala.querySelector("i").style.width = `${passo / v.m}px`;
        escala.querySelector("b").textContent = passo >= 1000 ? `${passo / 1000} km` : `${passo} m`;
      }
    }

    // ───── mexer: arrastar, beliscar, roda, teclado ─────
    function zoomEm(px, py, fator) {
      const antes = noMapa(px, py);
      v.m = clamp(v.m * fator, M_MIN, M_MAX);
      const depois = noMapa(px, py);
      if (antes && depois) { v.x += antes.x - depois.x; v.y += antes.y - depois.y; }
      aplicar();
    }
    let animacao = 0;
    function voar(alvo, ms = 900) {
      cancelAnimationFrame(animacao);
      // a inclinação vai sempre para a que a pessoa escolheu — um voo cortado a meio não a deixa torta
      alvo = { ...v, inc: ver.vista === "inclinada" ? 1 : 0, ...alvo };
      if (RM) { Object.assign(v, alvo); aplicar(); return; }
      const de = { ...v }, t0 = performance.now();
      const lm0 = Math.log(de.m), lm1 = Math.log(alvo.m);
      const passo = (t) => {
        const q = clamp((t - t0) / ms, 0, 1);
        const s = q < 0.5 ? 4 * q * q * q : 1 - Math.pow(-2 * q + 2, 3) / 2;
        v.x = de.x + (alvo.x - de.x) * s;
        v.y = de.y + (alvo.y - de.y) * s;
        v.m = Math.exp(lm0 + (lm1 - lm0) * s);
        v.inc = de.inc + (alvo.inc - de.inc) * s;
        aplicar();
        if (q < 1) animacao = requestAnimationFrame(passo);
      };
      animacao = requestAnimationFrame(passo);
    }
    // enquadrar caixas {x, y, r} (metros) na área livre; as margens em píxeis de ecrã
    function enquadrar(caixas, { esq = 40, dir = 40, vert = 50, minimo = 900 } = {}) {
      if (!caixas.length) caixas = [{ x: W / 2, y: H / 2, r: Math.max(W, H) / 2 }];
      const x0 = Math.min(...caixas.map((c) => c.x - c.r)), x1 = Math.max(...caixas.map((c) => c.x + c.r));
      const y0 = Math.min(...caixas.map((c) => c.y - c.r)), y1 = Math.max(...caixas.map((c) => c.y + c.r));
      const f = livre();
      const lw = Math.max(160, tam.w - f.esq - f.dir - esq - dir), lh = Math.max(160, tam.h - f.baixo - 2 * vert);
      // inclinado, o longe encolhe: pede-se um pouco mais de chão
      const folga = 1 + 0.25 * v.inc;
      const m = clamp(Math.max(Math.max(x1 - x0, minimo) / lw, Math.max(y1 - y0, minimo) / lh) * folga, M_MIN, M_MAX);
      return { x: (x0 + x1) / 2 + ((dir - esq) / 2) * m, y: (y0 + y1) / 2, m };
    }
    const caixa = (a) => ({ ...pos(a.querySelector(".pino")), r: Math.max(+a.dataset.raio, 120) });
    function vistaInicial() {
      const foco = document.body.dataset.foco;
      const a = foco && lugares.find((l) => l.dataset.id === foco);
      if (a) { a.classList.add("foco"); return enquadrar([caixa(a)], { dir: 220, minimo: 1400 }); }
      const estreito = tam.w < 600;
      const centro = { x: +d.centroX || W / 2, y: +d.centroY || H / 2, r: estreito ? 1700 : 2500 };
      return enquadrar([centro, ...lugares.map(caixa)], { esq: estreito ? 12 : 30, dir: estreito ? 12 : 230, minimo: estreito ? 3600 : 5000 });
    }

    const medir = () => { const r = cena.getBoundingClientRect(); tam = { w: r.width, h: r.height }; };
    medir();
    Object.assign(v, vistaInicial());
    new ResizeObserver(() => { medir(); aplicar(); }).observe(cena);
    LADO.addEventListener("change", aplicar);

    const toques = new Map();
    let arrastou = false, inicio = null;
    const rel = (e) => { const r = cena.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    svg.addEventListener("pointerdown", (e) => {
      if (e.button > 0) return;
      cancelAnimationFrame(animacao);
      toques.set(e.pointerId, rel(e));
      if (toques.size === 1) { arrastou = false; inicio = rel(e); }
    });
    svg.addEventListener("pointermove", (e) => {
      if (!toques.has(e.pointerId)) return;
      const agora = rel(e), antes = toques.get(e.pointerId);
      if (toques.size === 1) {
        if (!arrastou && Math.hypot(agora.x - inicio.x, agora.y - inicio.y) < 5) return;
        if (!arrastou) { arrastou = true; svg.setPointerCapture(e.pointerId); svg.classList.add("arrastando"); }
        // o chão que estava debaixo do dedo fica debaixo do dedo — também inclinado
        const a = noMapa(antes.x, antes.y), b = noMapa(agora.x, agora.y);
        if (a && b) { v.x += a.x - b.x; v.y += a.y - b.y; aplicar(); }
      } else if (toques.size === 2) {
        arrastou = true;
        const [outro] = [...toques].filter(([id]) => id !== e.pointerId).map(([, p]) => p);
        const d0 = Math.hypot(antes.x - outro.x, antes.y - outro.y), d1 = Math.hypot(agora.x - outro.x, agora.y - outro.y);
        if (d0 > 0 && d1 > 0) zoomEm((agora.x + outro.x) / 2, (agora.y + outro.y) / 2, d0 / d1);
      }
      toques.set(e.pointerId, agora);
    });
    const largar = (e) => { toques.delete(e.pointerId); if (!toques.size) svg.classList.remove("arrastando"); };
    svg.addEventListener("pointerup", largar);
    svg.addEventListener("pointercancel", largar);
    svg.addEventListener("click", (e) => { if (arrastou) { e.preventDefault(); e.stopPropagation(); arrastou = false; } }, true);
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const p = rel(e);
      const dd = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      zoomEm(p.x, p.y, Math.exp(clamp(dd, -120, 120) * (e.ctrlKey ? 0.01 : 0.002)));
    }, { passive: false });
    svg.addEventListener("dblclick", (e) => { const p = rel(e); zoomEm(p.x, p.y, e.shiftKey ? 2 : 0.5); });
    svg.addEventListener("keydown", (e) => {
      const k = camera(), passo = 90 * v.m;
      const acoes = {
        ArrowLeft: () => { v.x -= passo; aplicar(); }, ArrowRight: () => { v.x += passo; aplicar(); },
        ArrowUp: () => { v.y -= passo; aplicar(); }, ArrowDown: () => { v.y += passo; aplicar(); },
        "+": () => zoomEm(k.ox, k.oy, 0.6), "=": () => zoomEm(k.ox, k.oy, 0.6), "-": () => zoomEm(k.ox, k.oy, 1 / 0.6),
        "0": () => voar(vistaInicial()),
      };
      if (acoes[e.key] && e.target === svg) { e.preventDefault(); acoes[e.key](); }
    });

    // ───── botões ─────
    if (ctr) {
      ctr.hidden = false;
      ctr.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b) return;
        const k = camera();
        if (b.dataset.acao === "mais") zoomEm(k.ox, k.oy, 0.5);
        else if (b.dataset.acao === "menos") zoomEm(k.ox, k.oy, 2);
        else if (b.dataset.acao === "tudo") voar(enquadrar([], { esq: 0, dir: 0, vert: 0 }));
        else if (b.dataset.acao === "voltar") voar(vistaInicial());
        else if (b.dataset.acao === "ver") abrirVer(!!cartao.hidden);
        else if (b.dataset.acao === "aqui") estouAqui();
      });
    }

    // ───── a folha e o mapa acendem-se um ao outro ─────
    const porId = (id) => lugares.find((l) => l.dataset.id === id);
    for (const c of document.querySelectorAll("[data-lugar]")) {
      const a = porId(c.dataset.lugar);
      if (!a) continue;
      c.addEventListener("pointerenter", () => a.classList.add("aceso"));
      c.addEventListener("pointerleave", () => a.classList.remove("aceso"));
      c.addEventListener("focus", () => a.classList.add("aceso"));
      c.addEventListener("blur", () => a.classList.remove("aceso"));
    }
    for (const a of lugares) {
      const c = document.querySelector(`[data-lugar="${a.dataset.id}"]`);
      if (!c) continue;
      a.addEventListener("pointerenter", () => c.classList.add("aceso"));
      a.addEventListener("pointerleave", () => c.classList.remove("aceso"));
    }
    const subir = () => { if (!LADO.matches) window.scrollTo({ top: 0, behavior: RM ? "auto" : "smooth" }); };
    for (const b of document.querySelectorAll("[data-ver-no-mapa]")) {
      b.addEventListener("click", (e) => {
        const a = porId(b.dataset.verNoMapa);
        if (!a) return;
        e.preventDefault();
        voar(enquadrar([caixa(a)], { dir: 220, minimo: 1400 }));
        subir();
      });
    }
    for (const b of document.querySelectorAll("[data-ver-jornada]")) {
      b.addEventListener("click", (e) => {
        e.preventDefault();
        abrirJornada(b.dataset.verJornada);
        subir();
      });
    }

    // ───── jeitos de ver: modos, vista, camadas, filtros e jornadas ─────
    // Pouco de propósito. Um modo é só um ponto de partida para as camadas; os
    // filtros escondem, nunca apagam. Tudo fica neste aparelho (localStorage).
    const CAMADAS = ["relevo", "nomes", "convites", "gente", "jornadas"];
    const tudo = () => Object.fromEntries(CAMADAS.map((k) => [k, true]));
    const PRESETS = {
      sossego: { ...tudo(), relevo: false, convites: false, jornadas: false },
      passeio: tudo(),
      explorador: tudo(),
    };
    const padrao = () => ({ modo: "passeio", vista: "cima", camadas: tudo(), sem: [] });
    let ver = padrao();
    try {
      const g = JSON.parse(localStorage.getItem("uai:ver") || "null");
      if (g && PRESETS[g.modo]) ver = { ...padrao(), ...g, camadas: { ...tudo(), ...g.camadas } };
    } catch { /* sem memória: vale só agora */ }
    if (!["cima", "inclinada"].includes(ver.vista)) ver.vista = "cima";
    const guardar = () => { try { localStorage.setItem("uai:ver", JSON.stringify(ver)); } catch { /* idem */ } };
    v.inc = ver.vista === "inclinada" ? 1 : 0;

    function aplicarVer() {
      cena.dataset.modo = ver.modo;
      explorar = ver.modo === "explorador";
      const relevoAntes = camadas.relevo;
      camadas = { ...ver.camadas };
      if (camadas.relevo && !sombra) pedirRelevo();
      if (relevoAntes !== camadas.relevo && sombra) colorir();
      for (const k of CAMADAS) cena.classList.toggle("sem-" + k, !camadas[k]);
      const sem = new Set(ver.sem);
      for (const a of lugares) a.classList.toggle("filtrado", sem.has("e:" + a.dataset.estado));
      for (const a of marcos) a.classList.toggle("filtrado", sem.has("c:" + a.dataset.cat));
      if (!camadas.jornadas) fecharJornada();
      if (cartao) {
        for (const b of cartao.querySelectorAll("[data-modo]")) {
          const sim = b.dataset.modo === ver.modo;
          b.setAttribute("aria-checked", sim);
          b.tabIndex = sim ? 0 : -1;
          if (sim) cartao.querySelector(".ver-dica").textContent = b.dataset.dica;
        }
        for (const b of cartao.querySelectorAll("[data-vista]")) {
          const sim = b.dataset.vista === ver.vista;
          b.setAttribute("aria-checked", sim);
          b.tabIndex = sim ? 0 : -1;
        }
        for (const i of cartao.querySelectorAll("[data-camada]")) i.checked = !!camadas[i.dataset.camada];
        for (const b of cartao.querySelectorAll(".ver-chips [data-estado]")) b.setAttribute("aria-pressed", !sem.has("e:" + b.dataset.estado));
        for (const b of cartao.querySelectorAll(".ver-chips [data-cat]")) b.setAttribute("aria-pressed", !sem.has("c:" + b.dataset.cat));
        cartao.querySelector(".ver-perto").hidden = !explorar;
      }
      aplicar();
    }

    if (cartao && botaoVer) {
      // só os filtros que têm alguma coisa para filtrar, e quantas
      const contar = (sel, lista, campo) => {
        for (const b of cartao.querySelectorAll(sel)) {
          const n = lista.filter((a) => a.dataset[campo] === b.dataset[campo]).length;
          b.hidden = !n;
          b.insertAdjacentHTML("beforeend", ` <small>${n}</small>`);
        }
      };
      contar(".ver-chips [data-estado]", lugares, "estado");
      contar(".ver-chips [data-cat]", marcos, "cat");
      for (const grupo of cartao.querySelectorAll(".ver-chips")) {
        const vazio = ![...grupo.children].some((b) => !b.hidden);
        grupo.hidden = vazio;
        grupo.previousElementSibling.hidden = vazio;
      }
      cartao.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b) return;
        if (b.dataset.modo) {
          ver.modo = b.dataset.modo;
          ver.camadas = { ...PRESETS[ver.modo] };
        } else if (b.dataset.vista) {
          ver.vista = b.dataset.vista;
          voar({ inc: ver.vista === "inclinada" ? 1 : 0 }, 700);
        } else if (b.dataset.jornada) {
          if (jornadaAtiva === b.dataset.jornada) fecharJornada();
          else abrirJornada(b.dataset.jornada);
          return;
        } else if (b.dataset.parada) {
          irParada(+b.dataset.parada);
          return;
        } else if (b.dataset.estado || b.dataset.cat) {
          const chave = b.dataset.estado ? "e:" + b.dataset.estado : "c:" + b.dataset.cat;
          ver.sem = ver.sem.includes(chave) ? ver.sem.filter((x) => x !== chave) : [...ver.sem, chave];
        } else if (b.dataset.ver === "repor") {
          ver = padrao();
          voar({ inc: 0 }, 500);
        } else if (b.dataset.ver === "fechar") return abrirVer(false);
        else if (b.dataset.ver === "aqui") return estouAqui();
        else return;
        guardar();
        aplicarVer();
      });
      cartao.addEventListener("change", (e) => {
        const k = e.target.dataset.camada;
        if (!k) return;
        ver.camadas[k] = e.target.checked;
        guardar();
        aplicarVer();
      });
      // os grupos de rádio: as setas andam entre as opções
      for (const grupo of cartao.querySelectorAll('[role="radiogroup"]')) {
        grupo.addEventListener("keydown", (e) => {
          const passo = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
          if (!passo) return;
          e.preventDefault();
          const bs = [...grupo.querySelectorAll('[role="radio"]')];
          const i = (bs.findIndex((b) => b.getAttribute("aria-checked") === "true") + passo + bs.length) % bs.length;
          bs[i].click();
          bs[i].focus();
        });
      }
      cartao.addEventListener("keydown", (e) => { if (e.key === "Escape") abrirVer(false); });
    }

    function abrirVer(abrir) {
      if (!cartao || !botaoVer) return;
      cartao.hidden = !abrir;
      botaoVer.setAttribute("aria-expanded", abrir);
      aplicar();
      if (abrir) { perto(); cartao.querySelector('[data-modo][aria-checked="true"]')?.focus(); }
      else botaoVer.focus();
    }

    // ───── jornadas: uma caminhada pelas ruas, parada a parada ─────
    const G = { oeste: +d.oeste, norte: +d.norte, kx: +d.kx, ky: +d.ky };
    const temGeo = G.kx > 0 && G.ky > 0;
    const grau = (x, y) => ({ lat: G.norte - y / G.ky, lon: G.oeste + x / G.kx });
    const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
    const osm = (x, y) => {
      if (!temGeo) return "";
      const g = grau(x, y), la = g.lat.toFixed(5), lo = g.lon.toFixed(5);
      return `<a class="ver-link" href="https://www.openstreetmap.org/?mlat=${la}&amp;mlon=${lo}#map=18/${la}/${lo}" rel="noopener" target="_blank" title="abrir no OpenStreetMap para traçar o caminho">caminho ↗</a>`;
    };
    // a barrinha da jornada: parada a parada, para quem está a andar
    const barra = cena.querySelector(".jornada-barra");
    let paradaAtual = -1;
    const paradasDe = (id) => paradas.filter((p) => p.dataset.jornada === id);
    function mostrarBarra() {
      if (!barra) return;
      const j = jornadas.find((x) => x.id === jornadaAtiva);
      barra.hidden = !j;
      if (!j) return;
      const ps = paradasDe(j.id);
      const [b, s] = barra.querySelectorAll("p > *");
      if (paradaAtual < 0) { b.textContent = j.g.dataset.nome; s.textContent = j.g.dataset.resumo; }
      else { b.textContent = ps[paradaAtual].dataset.nome; s.textContent = `parada ${paradaAtual + 1} de ${ps.length} · ${j.g.dataset.nome}`; }
      barra.querySelector('[data-j="antes"]').disabled = paradaAtual <= 0;
      barra.querySelector('[data-j="depois"]').disabled = paradaAtual >= ps.length - 1;
    }
    function irParada(n) {
      const ps = paradasDe(jornadaAtiva);
      if (!ps[n]) return;
      paradaAtual = n;
      voar(enquadrar([{ ...pos(ps[n]), r: 90 }], { dir: 200, minimo: 500 }));
      mostrarBarra();
    }
    barra?.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.j === "fechar") fecharJornada();
      else irParada(paradaAtual + (b.dataset.j === "depois" ? 1 : -1));
    });

    function abrirJornada(id) {
      const j = jornadas.find((x) => x.id === id);
      if (!j) return;
      jornadaAtiva = id;
      paradaAtual = -1;
      if (!ver.camadas.jornadas) { ver.camadas.jornadas = true; guardar(); aplicarVer(); }
      if (cartao) {
        if (cartao.hidden) abrirVer(true);
        for (const b of cartao.querySelectorAll("[data-jornada]")) b.setAttribute("aria-pressed", b.dataset.jornada === id);
        for (const p of cartao.querySelectorAll("[data-convite]")) p.hidden = p.dataset.convite !== id;
        const lista = cartao.querySelector(".ver-paradas");
        lista.hidden = false;
        lista.innerHTML = paradas.filter((p) => p.dataset.jornada === id).map((p) =>
          `<li><button type="button" data-parada="${p.dataset.n - 1}"><b><i>${p.dataset.n}</i>${esc(p.dataset.nome)}</b><span>${esc(p.dataset.tipo)}</span></button>${osm(+p.dataset.x, +p.dataset.y)}</li>`).join("");
      }
      // no telefone o cartão tapava a jornada: fecha-se, e fica a barrinha
      if (!LADO.matches && cartao && !cartao.hidden) { cartao.hidden = true; botaoVer?.setAttribute("aria-expanded", "false"); }
      mostrarBarra();
      voar(enquadrar(j.pontos.map(([x, y]) => ({ x, y, r: 60 })), { dir: 60, minimo: 600 }));
    }
    function fecharJornada() {
      jornadaAtiva = null;
      paradaAtual = -1;
      mostrarBarra();
      if (!cartao) return;
      for (const b of cartao.querySelectorAll("[data-jornada]")) b.setAttribute("aria-pressed", "false");
      for (const p of cartao.querySelectorAll("[data-convite]")) p.hidden = true;
      const lista = cartao.querySelector(".ver-paradas");
      if (lista) { lista.hidden = true; lista.innerHTML = ""; }
      aplicar();
    }

    // ───── perto daqui: o que fica à volta, e quanto se anda a pé ─────
    const rotuloCat = (cat) => cartao?.querySelector(`.ver-chips [data-cat="${cat}"]`)?.firstChild?.nextSibling?.textContent?.trim() || "";
    const distancia = (m) => (m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1).replace(".", ",")} km`);
    function aPe(m) {
      const min = Math.max(1, Math.round((m * 1.3) / 75));  // as ruas não vão em linha reta; ~4,5 km/h
      if (min > 90) return "longe para ir a pé";
      return min < 60 ? `uns ${min} min a pé` : "uma hora e pouco a pé";
    }
    let pertoPedido = 0;
    function perto() {
      if (!cartao || cartao.hidden || !explorar) return;
      const de = aqui || { x: v.x, y: v.y };
      const cands = [
        ...lugares.filter((a) => !a.classList.contains("filtrado")).map((a) => ({ a, ...pos(a.querySelector(".pino")), nome: a.dataset.nome, tipo: "lugar da UAI", uai: true })),
        ...(camadas.convites ? marcos.filter((a) => !a.classList.contains("filtrado")).map((a) => ({ a, ...pos(a.querySelector(".icone")), nome: a.dataset.nome, tipo: rotuloCat(a.dataset.cat) })) : []),
      ].map((c) => ({ ...c, d: Math.hypot(c.x - de.x, c.y - de.y) })).sort((p, q) => p.d - q.d).slice(0, 4);
      const lista = cartao.querySelector(".ver-perto .ver-lista");
      cartao.querySelector(".ver-onde").textContent = aqui
        ? "a partir de onde você está"
        : "a partir do meio do mapa — arraste para mudar, ou diga onde está";
      lista.innerHTML = cands.map((c, i) =>
        `<li${c.uai ? ' class="uai"' : ""}><button type="button" data-i="${i}"><b>${esc(c.nome)}</b><span>${esc(c.tipo)} · ${c.d < 40 ? "aqui mesmo" : `${distancia(c.d)} · ${aPe(c.d)}`}</span></button>${osm(c.x, c.y)}</li>`,
      ).join("") || '<li class="ver-nota">nada à vista com estes filtros</li>';
      for (const b of lista.querySelectorAll("button[data-i]")) {
        const c = cands[+b.dataset.i];
        b.addEventListener("click", () => {
          voar(enquadrar([{ x: c.x, y: c.y, r: 120 }], { dir: 220, minimo: 700 }));
          c.a.classList.add("aceso");
          setTimeout(() => c.a.classList.remove("aceso"), 2400);
        });
      }
    }
    aoMover = () => { clearTimeout(pertoPedido); pertoPedido = setTimeout(perto, 220); };

    // ───── estou aqui: a posição é pedida, usada aqui e esquecida ─────
    function estouAqui() {
      const dizer = (t) => { if (cartao) cartao.querySelector(".ver-onde").textContent = t; };
      if (!temGeo || !navigator.geolocation) return dizer("este aparelho não sabe dizer onde está");
      dizer("a perguntar ao aparelho onde você está…");
      navigator.geolocation.getCurrentPosition((p) => {
        const x = (p.coords.longitude - G.oeste) * G.kx, y = (G.norte - p.coords.latitude) * G.ky;
        if (x < 0 || y < 0 || x > W || y > H) { aqui = null; perto(); return dizer("você está fora do mapa de Passos — a lista conta a partir do meio do mapa"); }
        aqui = { x, y };
        if (!marcaAqui) {
          marcaAqui = document.createElementNS(NS, "g");
          marcaAqui.setAttribute("class", "aqui");
          marcaAqui.setAttribute("aria-hidden", "true");
          marcaAqui.innerHTML = '<rect class="aqui-halo" x="-14" y="-14" width="28" height="28"/><rect class="aqui-miolo" x="-6" y="-6" width="12" height="12"/>';
          svg.append(marcaAqui);
        }
        voar({ x, y, m: Math.min(v.m, 2.4) });
        perto();
      }, () => dizer("não deu para saber onde você está — tudo bem: a lista conta a partir do meio do mapa"),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
    }

    // ───── o tema muda, as cores mudam ─────
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", colorir);
    // o contraste e o fundo (botão «fundo») mudam as cores: repinta-se
    let temaAntes = "";
    const tema = () => raiz.classList.contains("contraste") + "|" + (raiz.dataset.fundo || "");
    temaAntes = tema();
    new MutationObserver(() => {
      const t = tema();
      if (t !== temaAntes) { temaAntes = t; colorir(); }
    }).observe(raiz, { attributes: true, attributeFilter: ["class", "data-fundo"] });

    aplicarVer();
    colorir();
    requestAnimationFrame(() => { svg.classList.add("pronto"); tela.classList.add("pronto"); });

    // ───── lá fora: o mapa não é para prender ninguém ─────
    // Depois de uns bons minutos a mexer no mapa, um lembrete só, uma vez por visita.
    const laFora = cena.querySelector(".la-fora");
    let ativo = 0, ultimo = 0;
    const jaLembrou = () => { try { return sessionStorage.getItem("uai:la-fora") === "1"; } catch { return false; } };
    function mexeu() {
      const agora = Date.now();
      if (agora - ultimo < 60000) ativo += agora - ultimo;
      ultimo = agora;
      if (laFora && laFora.hidden && ativo > 12 * 60000 && !jaLembrou()) {
        laFora.hidden = false;
        try { sessionStorage.setItem("uai:la-fora", "1"); } catch { /* vale só agora */ }
      }
    }
    for (const ev of ["pointerdown", "wheel", "keydown"]) svg.addEventListener(ev, mexeu, { passive: true });
    laFora?.querySelector("button").addEventListener("click", () => { laFora.hidden = true; });
  }
})();
