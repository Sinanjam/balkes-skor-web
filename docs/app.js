const BASE = "data/";
const GOATCOUNTER_TOTAL_URL = "https://balkesskor.goatcounter.com/counter/TOTAL.json";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (m) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
const norm = (s) => String(s ?? "")
  .toLocaleLowerCase("tr")
  .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
  .replace(/[ıİ]/g,"i").replace(/[ğĞ]/g,"g").replace(/[üÜ]/g,"u")
  .replace(/[şŞ]/g,"s").replace(/[öÖ]/g,"o").replace(/[çÇ]/g,"c")
  .replace(/[^a-z0-9\s-]/g," ").replace(/\s+/g," ").trim();

let manifest = null;
let report = null;
let seasons = [];
let players = [];
let opponents = [];
let selectedSeason = null;
let seasonData = null;
let matches = [];
let standingsByWeek = [];
let matchDetails = new Map();
let lastMatchId = null;
let openPlayerName = "";

async function getJson(path) {
  const res = await fetch(BASE + path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path} yüklenemedi: ${res.status}`);
  return res.json();
}

function resultLabel(r) {
  if (r === "W") return ["G", "win", "Galibiyet"];
  if (r === "D") return ["B", "draw", "Beraberlik"];
  if (r === "L") return ["M", "loss", "Mağlubiyet"];
  return ["?", "", "Bilinmiyor"];
}
function gd(v) { return typeof v === "number" && v > 0 ? `+${v}` : (v ?? "—"); }
function n(v) { return Number(v || 0).toLocaleString("tr-TR"); }
function setStatus(text, source="") {
  $("#data-status").textContent = text;
  if (source) $("#data-source").textContent = source;
}
function matchHaystack(m) {
  return norm([m.stage, m.dateDisplay, m.homeTeam, m.awayTeam, m.score?.display, m.balkes?.opponent, m.roundType, m.venue].join(" "));
}

function renderVisitorTotal() {
  const el = $("#metric-visitors");
  if (!el) return;
  fetch(GOATCOUNTER_TOTAL_URL, { cache: "no-cache", mode: "cors" })
    .then((res) => {
      if (!res.ok) throw new Error(`GoatCounter sayaç yanıtı: ${res.status}`);
      return res.json();
    })
    .then((data) => {
      el.textContent = data?.count || "—";
      el.closest(".metric-card")?.classList.add("counter-loaded");
    })
    .catch(() => {
      el.textContent = "—";
    });
}

function renderMetrics() {
  const totalMatches = seasons.reduce((a,s)=>a + Number(s.matchCount || s.summary?.matches || 0),0);
  $("#metric-seasons").textContent = n(seasons.length);
  $("#metric-matches").textContent = n(report?.totalAppMatches || totalMatches);
  $("#metric-players").textContent = n(players.length || report?.playersIndexed || 0);
  $("#metric-opponents").textContent = n(opponents.length || report?.opponentsIndexed || 0);
}

function renderSeasonRail() {
  const rail = $("#season-rail");
  rail.innerHTML = seasons.map((s) => {
    const sum = s.summary || {};
    const active = selectedSeason?.id === s.id ? " active" : "";
    return `<button class="season-card${active}" type="button" data-season="${esc(s.id)}">
      <div class="season-title">${esc(s.name || s.id)}</div>
      <div class="season-meta">${esc(s.competition || "Lig")} ${s.group ? "· " + esc(s.group) : ""}</div>
      <div class="season-bars">
        <span><b>${n(sum.matches || s.matchCount || 0)}</b>Maç</span>
        <span><b>${n(sum.points ?? "—")}</b>Puan</span>
        <span><b>${gd(sum.goalDifference)}</b>Averaj</span>
      </div>
    </button>`;
  }).join("");
  $$(".season-card").forEach(btn => btn.addEventListener("click", () => loadSeason(btn.dataset.season)));
}

function renderSeasonOptions() {
  const sel = $("#season-select");
  sel.innerHTML = seasons.map((s) => `<option value="${esc(s.id)}">${esc(s.name || s.id)}</option>`).join("");
  sel.value = selectedSeason.id;
}

function renderSeasonSummary() {
  const s = seasonData.summary || selectedSeason.summary || {};
  $("#selected-season-title").textContent = `${seasonData.name || selectedSeason.id} · ${seasonData.competition || selectedSeason.competition || ""}`;
  const items = [
    ["Maç", s.matches], ["G", s.wins], ["B", s.draws], ["M", s.losses],
    ["Gol", `${s.goalsFor ?? "—"}-${s.goalsAgainst ?? "—"}`], ["AV", gd(s.goalDifference)],
    ["Puan", s.points ?? "—"], ["Sıra", s.finalRank ?? "—"]
  ];
  $("#season-stats").innerHTML = items.map(([k,v]) => `<div class="stat-pill"><span>${k}</span><b>${esc(v)}</b></div>`).join("");
}

function renderLastMatch() {
  const played = matches.filter(m => m.score?.played);
  const last = played[played.length - 1];
  if (!last) { $("#last-match").innerHTML = `<div class="empty">Oynanmış maç bulunamadı.</div>`; return; }
  lastMatchId = last.id;
  const [short, cls, long] = resultLabel(last.balkes?.result);
  $("#last-match").innerHTML = `
    <div class="score-line"><span>${esc(last.homeTeam)}</span><span class="score">${esc(last.score?.display || "-")}</span><span>${esc(last.awayTeam)}</span></div>
    <div class="meta-line"><span class="badge ${cls}">${short}</span>${esc(long)} · ${esc(last.stage || "")} · ${esc(last.dateDisplay || "")}</div>
    <div class="meta-line">Rakip: <b>${esc(last.balkes?.opponent || "—")}</b></div>`;
}

function renderMatches() {
  const tokens = norm($("#search").value).split(" ").filter(Boolean);
  const rf = $("#result-filter").value;
  const round = $("#round-filter").value;
  const arr = matches.filter((m) => {
    if (rf && m.balkes?.result !== rf) return false;
    if (round && m.roundType !== round) return false;
    if (!tokens.length) return true;
    const hay = matchHaystack(m);
    return tokens.every(t => hay.includes(t));
  });
  $("#match-count").textContent = `${arr.length} maç`;
  $("#matches").innerHTML = arr.length ? arr.map(matchCard).join("") : `<div class="empty">Bu filtreye uygun maç bulunamadı.</div>`;
  $$(".match-card").forEach(btn => btn.addEventListener("click", () => openMatch(btn.dataset.id)));
}
function matchCard(m) {
  const [short, cls, long] = resultLabel(m.balkes?.result);
  return `<button class="match-card" type="button" data-id="${esc(m.id)}">
    <div class="match-top"><span>${esc(m.stage || m.competition || "")}</span><span>${esc(m.dateDisplay || "")}</span></div>
    <div class="match-main"><div class="team home">${esc(m.homeTeam)}</div><div class="match-score">${esc(m.score?.display || "-")}</div><div class="team away">${esc(m.awayTeam)}</div></div>
    <div class="match-bottom"><span><span class="badge ${cls}">${short}</span>${esc(long)} · ${esc(typeLabel(m.roundType))}</span><span>Rakip: ${esc(m.balkes?.opponent || "—")}</span></div>
  </button>`;
}
function typeLabel(t) { return t === "playoff" ? "Play-off" : t === "cup" ? "Kupa" : "Lig"; }

async function openMatch(id) {
  let m = matchDetails.get(id);
  if (!m) {
    const idx = matches.find(x => x.id === id);
    if (!idx) return;
    m = await getJson(idx.detailUrl);
    matchDetails.set(id, m);
  }
  const [short, cls, long] = resultLabel(m.balkes?.result);
  const refs = (m.referees || []).map(r => `<li><b>${esc(r.role_tr || "Hakem")}</b>: ${esc(r.name)}</li>`).join("");
  $("#detail").hidden = false;
  $("#detail").innerHTML = `
    <div class="detail-head">
      <div><div><span class="badge ${cls}">${short}</span>${esc(long)} · ${esc(m.stage || "")} · ${esc(m.dateDisplay || "")}</div><h2>${esc(m.homeTeam)} - ${esc(m.awayTeam)}</h2><div class="meta-line">${esc(m.venue || "Stat bilgisi yok")}</div></div>
      <div class="big-score">${esc(m.score?.display || "-")}</div>
    </div>
    <div class="detail-grid">
      <div class="info-box"><h3>Hakemler</h3><ul class="list">${refs || "<li>Hakem bilgisi yok.</li>"}</ul></div>
      <div class="info-box"><h3>Maç olayları</h3><ul class="list">${renderEvents(m.events || []) || "<li>Olay bilgisi yok.</li>"}</ul></div>
      <div class="info-box"><h3>${esc(m.lineups?.home?.team || m.homeTeam)} İlk 11</h3><ol class="list">${playerLines(m.lineups?.home?.starting11) || "<li>İlk 11 bilgisi yok.</li>"}</ol></div>
      <div class="info-box"><h3>${esc(m.lineups?.away?.team || m.awayTeam)} İlk 11</h3><ol class="list">${playerLines(m.lineups?.away?.starting11) || "<li>İlk 11 bilgisi yok.</li>"}</ol></div>
    </div>
    <p class="meta-line" style="margin-top:14px">Kaynak: <a href="${esc(m.source?.url || "#")}" target="_blank" rel="noopener">TFF maç detayı</a></p>`;
  $("#detail").scrollIntoView({ behavior: "smooth", block: "start" });
}
function playerLines(list) { return (list || []).map(p => `<li>${esc(p.shirt_no || p.shirtNo || "")} ${esc(p.name || p.player || "")}</li>`).join(""); }
function renderEvents(events) {
  return [...events].sort((a,b)=>Number(a.minute || 999)-Number(b.minute || 999)).map((e) => {
    const minute = e.minute ? `${e.minute}'` : "—";
    const player = e.player || e.name || e.playerName || e.raw || "";
    const team = e.team || "";
    return `<li class="event"><span class="minute">${esc(minute)}</span><span>${esc(eventIcon(e.type || e.event_type || e.kind || "") + " " + [player, team && `(${team})`].filter(Boolean).join(" "))}</span></li>`;
  }).join("");
}
function eventIcon(t) {
  const s = norm(t);
  if (s.includes("goal") || s.includes("gol")) return "⚽";
  if (s.includes("yellow") || s.includes("sari")) return "🟨";
  if (s.includes("red") || s.includes("kirmizi")) return "🟥";
  if (s.includes("sub") || s.includes("degis")) return "🔁";
  return "•";
}

function renderStandings() {
  const weekSelect = $("#week-select");
  weekSelect.innerHTML = standingsByWeek.map(w => `<option value="${w.week}">${w.week}. hafta</option>`).join("");
  if (standingsByWeek.length) weekSelect.value = standingsByWeek[standingsByWeek.length - 1].week;
  drawStandings();
}
function drawStandings() {
  const body = $("#standings-table tbody");
  const week = Number($("#week-select").value || standingsByWeek[standingsByWeek.length - 1]?.week);
  const snap = standingsByWeek.find(x => Number(x.week) === week) || standingsByWeek[standingsByWeek.length - 1];
  if (!snap) { body.innerHTML = `<tr><td colspan="8">Bu sezon için haftalık puan durumu bulunamadı.</td></tr>`; return; }
  body.innerHTML = snap.standings.map(r => `<tr class="${r.isBalkes ? "balkes" : ""}"><td>${r.rank}</td><td>${esc(r.team)}</td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${gd(r.goalDifference)}</td><td>${r.points}</td></tr>`).join("");
}

function renderPlayers() {
  const tokens = norm($("#player-search").value).split(" ").filter(Boolean);
  const arr = players.filter(p => !tokens.length || tokens.every(t => norm(p.name).includes(t))).slice(0, 90);
  $("#players").innerHTML = arr.length ? arr.map((p,i)=>playerCard(p,i+1)).join("") : `<div class="empty">Oyuncu bulunamadı.</div>`;
  $$(".player-card").forEach(card => card.addEventListener("click", () => {
    openPlayerName = card.dataset.name === openPlayerName ? "" : card.dataset.name;
    renderPlayers();
  }));
}
function playerCard(p, rank) {
  const open = p.name === openPlayerName ? " open" : "";
  const recent = (p.recentMatches || []).slice(0,5).map(m => `<div class="recent-line"><span>${esc(m.season)}</span><span>${esc(m.opponent || "—")}</span><b>${esc(m.score || "-")}</b></div>`).join("");
  return `<article class="player-card${open}" data-name="${esc(p.name)}">
    <div class="player-top"><div><div class="player-name">${esc(p.name)}</div><div class="meta-line">${n(p.appearances)} maç · ${n(p.starts)} ilk 11</div></div><div class="player-rank">#${rank}</div></div>
    <div class="player-quick"><span><b>${n(p.goals)}</b>Gol</span><span><b>${n(p.cards ?? (p.yellowCards+p.redCards))}</b>Kart</span><span><b>${n(p.yellowCards)}</b>Sarı</span><span><b>${n(p.redCards)}</b>Kırmızı</span></div>
    <div class="player-more">
      <div class="player-quick"><span><b>${n(p.subs)}</b>Yedek</span><span><b>${n(p.subbedIn)}</b>Girdi</span><span><b>${n(p.subbedOut)}</b>Çıktı</span><span><b>${n(p.ownGoals)}</b>KK</span></div>
      <div class="recent-list">${recent || "<div class='meta-line'>Son maç bilgisi yok.</div>"}</div>
    </div>
  </article>`;
}

function renderOpponents() {
  const tokens = norm($("#opponent-search").value).split(" ").filter(Boolean);
  const arr = opponents.filter(o => !tokens.length || tokens.every(t => norm(o.name).includes(t))).slice(0, 70);
  $("#opponents").innerHTML = arr.map(o => `<article class="opponent-card"><strong>${esc(o.name)}</strong><div class="opponent-stats"><span><b>${n(o.matches)}</b>Maç</span><span><b>${n(o.wins)}</b>G</span><span><b>${n(o.draws)}</b>B</span><span><b>${n(o.losses)}</b>M</span></div><div class="meta-line">Gol: ${n(o.goalsFor)}-${n(o.goalsAgainst)} · Son maç: ${esc(o.lastMatchDate || "—")}</div></article>`).join("") || `<div class="empty">Rakip bulunamadı.</div>`;
}

async function loadSeason(id) {
  selectedSeason = seasons.find(s => s.id === id) || seasons[0];
  seasonData = await getJson(selectedSeason.seasonUrl || `seasons/${selectedSeason.id}/season.json`);
  matches = await getJson(selectedSeason.matchesIndexUrl || seasonData.files?.matchesIndex);
  standingsByWeek = await getJson(selectedSeason.standingsUrl || seasonData.files?.standingsByWeek);
  matchDetails.clear();
  renderSeasonRail();
  renderSeasonOptions();
  renderSeasonSummary();
  renderLastMatch();
  renderMatches();
  renderStandings();
  setStatus(`${n(matches.length)} maç yüklendi`, `Veri üretimi: ${manifest.generatedAt || "—"}`);
}

async function init() {
  try {
    [manifest, report, players, opponents] = await Promise.all([
      getJson("manifest.json"),
      getJson("data_report.json").catch(()=>null),
      getJson("players_index.json").catch(()=>[]),
      getJson("opponents_index.json").catch(()=>[])
    ]);
    seasons = [...(manifest.availableSeasons || [])].sort((a,b)=>String(b.id).localeCompare(String(a.id)));
    if (!seasons.length) throw new Error("Manifest içinde sezon bulunamadı.");
    renderMetrics();
    renderVisitorTotal();
    renderPlayers();
    renderOpponents();
    await loadSeason(seasons[0].id);
  } catch (err) {
    console.error(err);
    setStatus("Veri yüklenemedi", err.message);
    $("#matches").innerHTML = `<div class="empty">${esc(err.message)}</div>`;
  }
}

$("#season-select").addEventListener("change", (e) => loadSeason(e.target.value));
$("#search").addEventListener("input", renderMatches);
$("#result-filter").addEventListener("change", renderMatches);
$("#round-filter").addEventListener("change", renderMatches);
$("#week-select").addEventListener("change", drawStandings);
$("#player-search").addEventListener("input", () => { openPlayerName = ""; renderPlayers(); });
$("#opponent-search").addEventListener("input", renderOpponents);
$("#last-detail").addEventListener("click", () => lastMatchId && openMatch(lastMatchId));

init();
