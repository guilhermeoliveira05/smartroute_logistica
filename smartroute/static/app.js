/* SmartRoute Logística - dashboard (JavaScript puro + Leaflet/OpenStreetMap) */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const CORES = ["#2563eb", "#f97316", "#9333ea", "#0891b2", "#dc2626", "#ca8a04", "#db2777", "#4d7c0f"];
const PRIORIDADE = { 1: "Urgente", 2: "Normal", 3: "Baixa" };

const estado = { mapa: null, entregas: [], rotas: [], veiculos: [], vias: [], kpis: null, rotaSel: null };
let map, camadaVias, camadaRotas, camadaPontos, camadaVeiculos, nosPorId = {};

const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, c = 2) => (n === null || n === undefined ? "-" : Number(n).toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }));
const reais = (n) => (n === null || n === undefined ? "-" : "R$ " + fmt(n));
const corRota = (r) => CORES[(r.veiculo_id - 1) % CORES.length];

async function api(url, opts = {}) {
  const resp = await fetch(url, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let dados = null;
  try { dados = await resp.json(); } catch (e) { /* sem corpo JSON */ }
  if (!resp.ok) throw new Error((dados && dados.erro) || resp.statusText);
  return dados;
}

let toastTimer;
function aviso(msg, erro = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (erro ? " erro" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("oculta"), 4200);
}

async function acao(botao, fn) {
  if (botao) botao.disabled = true;
  try { await fn(); } catch (e) { aviso(e.message, true); }
  finally { if (botao) botao.disabled = false; }
}

/* ------------------------------------------------------------------ dados */
async function carregarTudo() {
  const [mapa, entregas, rotas, veiculos, vias, kpis] = await Promise.all([
    api("/api/mapa"), api("/api/entregas"), api("/api/rotas"),
    api("/api/veiculos"), api("/api/vias/bloqueadas"), api("/api/kpis"),
  ]);
  Object.assign(estado, { mapa, entregas, rotas, veiculos, vias, kpis });
  nosPorId = Object.fromEntries(mapa.nos.map((n) => [n.id, n]));
  if (estado.rotaSel && !rotas.some((r) => r.id === estado.rotaSel)) estado.rotaSel = null;
  renderizar();
}

function renderizar() {
  renderKpis(); renderMapa(); renderEntregas(); renderRotas(); renderVias();
}

/* ------------------------------------------------------------------- KPIs */
function renderKpis() {
  const k = estado.kpis;
  const cards = [
    ["Custo médio / entrega", reais(k.custo_medio_por_entrega_rs), `${k.entregas_planejadas} de ${k.total_entregas} planejadas`],
    ["Km hoje", fmt(k.km_hoje) + " km", `${fmt(k.km_semana)} km em 7 dias`],
    ["Entregas no prazo", k.taxa_no_prazo_pct === null ? "-" : fmt(k.taxa_no_prazo_pct, 1) + "%", "previsão pelo ETA das rotas"],
    ["Eficiência", k.eficiencia_km_por_l === null ? "-" : fmt(k.eficiencia_km_por_l) + " km/L", `${fmt(k.litros_total)} L · ${reais(k.custo_total_rs)}`],
    ["Economia de combustível", k.economia_combustivel_pct === null ? "-" : fmt(k.economia_combustivel_pct, 1) + "%", `${reais(k.economia_custo_rs)} vs. rota empírica`, true],
  ];
  $("#kpis").innerHTML = cards.map(([r, v, s, d]) =>
    `<div class="kpi${d ? " destaque" : ""}"><div class="rot">${esc(r)}</div><div class="val">${esc(v)}</div><div class="sub">${esc(s)}</div></div>`).join("");
}

/* ------------------------------------------------------------------- mapa */
function iniciarMapa() {
  map = L.map("map", { zoomControl: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap",
  }).addTo(map);
  camadaVias = L.layerGroup().addTo(map);
  camadaRotas = L.layerGroup().addTo(map);
  camadaPontos = L.layerGroup().addTo(map);
  camadaVeiculos = L.layerGroup().addTo(map);
}

const ll = (id) => [nosPorId[id].lat, nosPorId[id].lon];
const pin = (txt, cor, tam = 22) => L.divIcon({
  className: "", iconSize: [tam, tam], iconAnchor: [tam / 2, tam / 2],
  html: `<div class="pin" style="width:${tam}px;height:${tam}px;background:${cor}">${esc(txt)}</div>`,
});
const emoji = (e) => L.divIcon({ className: "", iconSize: [28, 28], iconAnchor: [14, 14], html: `<div class="emoji">${e}</div>` });

let primeiroAjuste = true;
function renderMapa() {
  camadaVias.clearLayers(); camadaRotas.clearLayers(); camadaPontos.clearLayers(); camadaVeiculos.clearLayers();

  // malha viária (clique = bloquear/liberar)
  estado.mapa.arestas.forEach((a) => {
    const linha = L.polyline([ll(a.u), ll(a.v)], {
      color: a.bloqueada ? "#dc2626" : "#cbd5e1", weight: a.bloqueada ? 6 : 4,
      dashArray: a.bloqueada ? "8 8" : null, opacity: a.bloqueada ? 0.95 : 0.9,
    }).addTo(camadaVias);
    linha.bindTooltip(`${nosPorId[a.u].nome} ↔ ${nosPorId[a.v].nome}<br>${fmt(a.dist_km * 1000, 0)} m · ${a.vel_kmh} km/h${a.bloqueada ? " · BLOQUEADA" : ""}`, { sticky: true });
    linha.on("click", () => alternarVia(a));
  });

  // rotas
  estado.rotas.forEach((r) => {
    if (r.caminho.length < 2) return;
    const sel = estado.rotaSel === r.id;
    const apagada = estado.rotaSel !== null && !sel;
    L.polyline(r.caminho.map(ll), {
      color: corRota(r), weight: sel ? 7 : 4, opacity: apagada ? 0.1 : sel ? 0.95 : 0.6, interactive: false,
    }).addTo(camadaRotas);
  });

  // depósito
  const dep = nosPorId[estado.mapa.deposito];
  L.marker([dep.lat, dep.lon], { icon: emoji("🏭"), zIndexOffset: 500 }).bindTooltip("Construlog (depósito)").addTo(camadaPontos);

  // entregas
  const rotasPorId = Object.fromEntries(estado.rotas.map((r) => [r.id, r]));
  estado.entregas.forEach((e) => {
    const r = e.rota_id ? rotasPorId[e.rota_id] : null;
    if (estado.rotaSel !== null && e.rota_id !== estado.rotaSel) return;
    const cor = e.estado >= 2 ? "#16a34a" : e.estado === 1 ? "#1d4ed8" : "#94a3b8";
    const rot = r ? e.ordem : "•";
    L.marker(ll(e.no_id), { icon: pin(rot, cor, r ? 24 : 16), zIndexOffset: 100 })
      .bindTooltip(`<b>${esc(e.cliente)}</b><br>${esc(e.endereco)}<br>${fmt(e.peso_kg, 1)} kg · ${PRIORIDADE[e.prioridade]}` +
        `${e.eta_min !== null ? `<br>ETA ${fmt(e.eta_min, 0)} min` : ""}${e.inviavel ? `<br><b>Inviável:</b> ${esc(e.inviavel)}` : ""}`)
      .addTo(camadaPontos);
  });

  // veículos
  estado.veiculos.forEach((v) => {
    if (!nosPorId[v.posicao_no]) return;
    L.marker(ll(v.posicao_no), { icon: emoji(v.tipo === "moto" ? "🏍️" : "🚚"), zIndexOffset: 900 })
      .bindTooltip(`${esc(v.nome)} · ${esc(nosPorId[v.posicao_no].nome)}`).addTo(camadaVeiculos);
  });

  if (primeiroAjuste) {
    map.fitBounds(L.latLngBounds(estado.mapa.nos.map((n) => [n.lat, n.lon])).pad(0.05));
    primeiroAjuste = false;
  }
}

async function alternarVia(a) {
  const rotulo = `${nosPorId[a.u].nome} ↔ ${nosPorId[a.v].nome}`;
  await acao(null, async () => {
    const r = await api(a.bloqueada ? "/api/vias/desbloquear" : "/api/vias/bloquear", { method: "POST", body: { u: a.u, v: a.v } });
    const p = r.replanejamento;
    let msg = `${r.bloqueada ? "Via bloqueada" : "Via liberada"}: ${rotulo}. Rotas recalculadas: ${p.viagens + p.rotas_em_andamento_recalculadas}.`;
    if (p.inviaveis.length) msg += ` ${p.inviaveis.length} entrega(s) ficaram sem caminho.`;
    aviso(msg);
    await carregarTudo();
  });
}

/* --------------------------------------------------------------- entregas */
function renderEntregas() {
  const linhas = estado.entregas.map((e) => {
    const prio = e.prioridade === 1 ? `<span class="chip urg">Urgente</span>` : esc(PRIORIDADE[e.prioridade]);
    const status = e.inviavel ? `<span class="chip inv" title="${esc(e.inviavel)}">Inviável</span>`
      : `<span class="chip s${e.estado}">${esc(e.estado_nome)}</span>`;
    const prazo = e.prazo_min === null ? "-" : fmt(e.prazo_min, 0);
    const eta = e.eta_min === null ? "-" : `${fmt(e.eta_min, 0)}${e.no_prazo === 0 ? " ⚠" : ""}`;
    const rem = e.estado === 0 ? `<button class="x" title="Remover" data-rem="${e.id}">×</button>` : "";
    return `<tr><td>${e.id}</td><td>${esc(e.cliente)}</td><td>${esc(e.endereco)}</td><td>${fmt(e.peso_kg, 1)}</td>` +
      `<td>${prio}</td><td>${prazo}</td><td>${eta}</td><td>${status}</td><td>${e.rota_id ?? "-"}</td><td>${rem}</td></tr>`;
  }).join("");
  $("#tab-entregas").innerHTML =
    `<thead><tr><th>#</th><th>Cliente</th><th>Endereço</th><th>kg</th><th>Prior.</th><th>Prazo</th><th>ETA</th><th>Estado</th><th>Rota</th><th></th></tr></thead>` +
    `<tbody>${linhas || `<tr><td colspan="10">Nenhuma entrega. Cadastre uma ou carregue a demo.</td></tr>`}</tbody>`;
  document.querySelectorAll("[data-rem]").forEach((b) => b.addEventListener("click", () =>
    acao(b, async () => { await api(`/api/entregas/${b.dataset.rem}`, { method: "DELETE" }); await carregarTudo(); })));
}

/* ------------------------------------------------------------------ rotas */
function renderRotas() {
  if (!estado.rotas.length) {
    $("#lista-rotas").innerHTML = `<p class="ajuda">Nenhuma rota ainda. Cadastre entregas e clique em <b>Planejar rotas</b>.</p>`;
    return;
  }
  $("#lista-rotas").innerHTML = estado.rotas.map((r) => {
    const eco = r.base_litros ? (1 - r.litros / r.base_litros) * 100 : null;
    const concluida = r.paradas.every((p) => p.estado === 3);
    const paradas = r.paradas.map((p) => {
      const atraso = p.no_prazo === 0 ? " atraso" : "";
      return `<li class="${atraso.trim()}">${esc(p.cliente)} · ${esc(p.endereco)} · ${fmt(p.peso_kg, 1)} kg · ETA ${fmt(p.eta_min, 0)} min ` +
        `<span class="chip s${p.estado}">${esc(p.estado_nome)}</span></li>`;
    }).join("");
    return `<div class="rota${estado.rotaSel === r.id ? " sel" : ""}" data-rota="${r.id}" style="border-left-color:${corRota(r)}">
      <h4><span>${esc(r.veiculo_nome)} · viagem ${r.viagem}</span><span class="eco">${eco === null ? "" : "−" + fmt(eco, 1) + "% comb."}</span></h4>
      <div class="met"><span><b>${fmt(r.dist_km)}</b> km</span><span><b>${fmt(r.tempo_min, 0)}</b> min</span>
        <span><b>${fmt(r.litros)}</b> L</span><span><b>${reais(r.custo_rs)}</b></span>
        <span>empírica: ${fmt(r.base_dist_km)} km · ${fmt(r.base_litros)} L</span></div>
      <ol>${paradas}</ol>
      <button class="sec" data-avancar="${r.id}" ${concluida ? "disabled" : ""}>${concluida ? "Concluída ✓" : "Avançar simulação ▶"}</button>
    </div>`;
  }).join("");

  document.querySelectorAll("[data-rota]").forEach((el) => el.addEventListener("click", (ev) => {
    if (ev.target.closest("button")) return;
    const id = Number(el.dataset.rota);
    estado.rotaSel = estado.rotaSel === id ? null : id;
    renderMapa(); renderRotas();
  }));
  document.querySelectorAll("[data-avancar]").forEach((b) => b.addEventListener("click", () =>
    acao(b, async () => { await api(`/api/rotas/${b.dataset.avancar}/avancar`, { method: "POST" }); await carregarTudo(); })));
}

/* ------------------------------------------------------------------- vias */
function renderVias() {
  $("#lista-vias").innerHTML = estado.vias.length
    ? estado.vias.map((v) => `<div class="vias-item"><span>${esc(v.nome_u)} ↔ ${esc(v.nome_v)}</span>
        <button class="sec" data-lib="${v.u}|${v.v}">Liberar</button></div>`).join("")
    : `<p class="ajuda">Nenhuma via bloqueada.</p>`;
  document.querySelectorAll("[data-lib]").forEach((b) => b.addEventListener("click", () => {
    const [u, v] = b.dataset.lib.split("|");
    const a = estado.mapa.arestas.find((x) => x.u === u && x.v === v);
    if (a) alternarVia(a);
  }));
}

/* ------------------------------------------------------------------ início */
function ligarEventos() {
  document.querySelectorAll(".abas button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".abas button").forEach((x) => x.classList.toggle("ativa", x === b));
    document.querySelectorAll(".aba").forEach((a) => a.classList.toggle("oculta", a.id !== `aba-${b.dataset.aba}`));
  }));

  $("#btn-demo").addEventListener("click", (ev) => acao(ev.currentTarget, async () => {
    await api("/api/demo", { method: "POST", body: { n: 35 } });
    const r = await api("/api/rotas/planejar", { method: "POST", body: {} });
    aviso(`Demo carregada: ${r.entregas_planejadas} entregas em ${r.viagens} viagens (−${fmt(r.economia_combustivel_pct, 1)}% de combustível vs. rota empírica).`);
    await carregarTudo();
  }));

  $("#btn-planejar").addEventListener("click", (ev) => acao(ev.currentTarget, async () => {
    const r = await api("/api/rotas/planejar", { method: "POST", body: {} });
    aviso(r.entregas_planejadas
      ? `${r.entregas_planejadas} entregas planejadas em ${r.viagens} viagens.` + (r.inviaveis.length ? ` ${r.inviaveis.length} inviável(is).` : "")
      : "Não há entregas pendentes para planejar.");
    await carregarTudo();
  }));

  $("#btn-reset").addEventListener("click", (ev) => {
    if (!confirm("Apagar todas as entregas, rotas e bloqueios?")) return;
    acao(ev.currentTarget, async () => { await api("/api/reset", { method: "POST" }); estado.rotaSel = null; await carregarTudo(); aviso("Sistema reiniciado."); });
  });

  $("#form-entrega").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const d = Object.fromEntries(new FormData(f));
    acao($("button[type=submit]", f), async () => {
      await api("/api/entregas", { method: "POST", body: d });
      f.cliente.value = ""; f.endereco.value = "";
      aviso("Entrega cadastrada. Clique em Planejar rotas para incluí-la.");
      await carregarTudo();
    });
  });

  // autocomplete de endereços (índice em árvore Trie no servidor)
  let tAuto;
  $("#form-entrega").endereco.addEventListener("input", (ev) => {
    clearTimeout(tAuto);
    const q = ev.target.value.trim();
    if (!q) return;
    tAuto = setTimeout(async () => {
      try {
        const r = await api("/api/enderecos?q=" + encodeURIComponent(q));
        $("#lista-enderecos").innerHTML = r.map((x) => `<option value="${esc(x.nome)}"></option>`).join("");
      } catch (e) { /* autocomplete é opcional */ }
    }, 150);
  });
}

(async function iniciar() {
  iniciarMapa();
  ligarEventos();
  try { await carregarTudo(); } catch (e) { aviso("Falha ao carregar dados: " + e.message, true); }
})();
