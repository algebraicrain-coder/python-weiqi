from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .ai import (
    AIConfig,
    AnalysisService,
    EngineError,
    EngineUnavailable,
    KataGoAnalysis,
    KataGoGTP,
    Position,
    add_cli_arguments,
    discover_config,
    overrides_from_args,
)
from .board import BLACK, KO_RULES, PASS, WHITE, IllegalMove, format_vertex, parse_vertex
from .game import Game, GameOver
from .player import RESIGN
from .record import (
    DEFAULT_FORMAT,
    GameRecord,
    default_filename,
    default_record_dir,
    merge_record_metadata,
    resolve_read_path,
    resolve_write_path,
)
from .sgf import SGFError

META_FIELDS = (
    "PB",
    "PW",
    "BR",
    "WR",
    "DT",
    "EV",
    "RO",
    "PC",
    "RU",
    "RE",
    "HA",
    "GN",
    "GC",
)

PAGE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>围棋 · 本地对弈</title>
<style>
  :root {
    --ink: #2e2820;
    --muted: #8b7f6b;
    --line: #e4dac7;
    --card: #fffdf8;
    --accent: #1f6f5c;
    --accent-2: #2c8f76;
    --danger: #a33327;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body {
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", system-ui, sans-serif;
    background:
      radial-gradient(1100px 520px at 12% -8%, #fffaf0 0%, rgba(255,250,240,0) 60%),
      radial-gradient(900px 480px at 105% 2%, #e6efe9 0%, rgba(230,239,233,0) 58%),
      linear-gradient(180deg, #f5f0e6, #e9e1d2);
    -webkit-font-smoothing: antialiased;
  }
  .topbar {
    max-width: 1160px; margin: 0 auto; padding: 22px 22px 16px;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    justify-content: space-between;
  }
  .brand { display: flex; align-items: center; gap: 16px; }
  .brand-mark {
    position: relative; width: 38px; height: 38px; border-radius: 50%;
    background: radial-gradient(circle at 32% 28%, #717171, #0b0b0b 66%);
    box-shadow: inset -2px -3px 6px rgba(255,255,255,.22), 0 5px 12px rgba(0,0,0,.25);
  }
  .brand-mark::after {
    content: ""; position: absolute; right: -10px; bottom: -8px;
    width: 24px; height: 24px; border-radius: 50%;
    background: radial-gradient(circle at 33% 28%, #fff, #d5cdba 72%);
    border: 1px solid rgba(0,0,0,.08); box-shadow: 0 3px 8px rgba(0,0,0,.18);
  }
  .brand h1 { margin: 0; font-size: 21px; letter-spacing: .14em; font-weight: 700; }
  .brand p { margin: 3px 0 0; font-size: 12px; letter-spacing: .08em; color: var(--muted); }
  .status-card {
    display: flex; gap: 11px; align-items: flex-start;
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 10px 15px; box-shadow: 0 8px 24px rgba(90,66,20,.07);
    min-width: 270px; max-width: 100%;
  }
  .turn-dot {
    flex: 0 0 auto; width: 15px; height: 15px; margin-top: 2px; border-radius: 50%;
    background: radial-gradient(circle at 32% 30%, #6c6c6c, #0a0a0a 64%);
    box-shadow: inset -1px -2px 3px rgba(255,255,255,.25), 0 2px 4px rgba(0,0,0,.25);
  }
  .turn-dot.is-white {
    background: radial-gradient(circle at 32% 30%, #fff, #d2cab7 72%);
    border: 1px solid rgba(0,0,0,.12);
    box-shadow: inset -1px -2px 3px rgba(0,0,0,.06), 0 2px 4px rgba(0,0,0,.15);
  }
  .turn-dot.is-over {
    background: linear-gradient(90deg, #111 0 50%, #f4efe6 50% 100%);
    border: 1px solid rgba(0,0,0,.18);
    box-shadow: 0 2px 4px rgba(0,0,0,.18);
  }
  #status { white-space: pre-line; font-size: 13px; line-height: 1.55; }
  .layout {
    display: grid; grid-template-columns: minmax(0, 720px) 360px; gap: 26px;
    align-items: start; max-width: 1160px; margin: 0 auto; padding: 0 22px 42px;
  }
  .board-area { min-width: 0; }
  .board-frame {
    border-radius: 22px; padding: 10px;
    background: linear-gradient(155deg, #64492a, #3c2b16);
    box-shadow: 0 22px 46px rgba(60,40,10,.30), inset 0 1px 0 rgba(255,255,255,.16);
  }
  #board {
    display: block; width: 100%; height: auto; border-radius: 14px;
    cursor: pointer; touch-action: manipulation;
  }
  .board-caption {
    margin: 12px 2px 0; font-size: 12px; letter-spacing: .06em;
    color: var(--muted); text-align: center;
  }
  .message { min-height: 18px; margin: 10px 0 0; font-size: 13px; text-align: center; color: var(--accent); }
  .message:not(:empty) {
    background: #eef7f2; border: 1px solid #cfe3d8; border-radius: 10px; padding: 8px 12px;
  }
  .message.error { color: var(--danger); }
  .message.error:not(:empty) {
    background: #fff2ef; border-color: #f1c7c0;
  }
  .panel { display: flex; flex-direction: column; gap: 14px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .card {
    margin: 0; padding: 14px 16px 16px; border: 1px solid var(--line);
    border-radius: 16px; background: var(--card);
    box-shadow: 0 10px 26px rgba(90,66,20,.07);
  }
  .card legend {
    padding: 0 8px; font-size: 12px; font-weight: 700;
    letter-spacing: .12em; color: var(--muted);
  }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
  .field { display: flex; flex-direction: column; gap: 5px; min-width: 0; font-size: 12px; color: var(--muted); }
  .field > span { font-weight: 600; letter-spacing: .03em; }
  .btn-row { display: flex; gap: 8px; }
  .btn-row button { flex: 1; }
  button {
    appearance: none; border: 1px solid #d9cbb0; border-radius: 10px;
    padding: 8px 12px; font-size: 13px; font-family: inherit; color: var(--ink);
    background: linear-gradient(#fffdf9, #f3ecdd); cursor: pointer;
    transition: transform .08s ease, box-shadow .15s ease, border-color .15s ease;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.75), 0 1px 2px rgba(60,40,10,.08);
  }
  button:hover {
    border-color: #c9b58f;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.8), 0 4px 12px rgba(60,40,10,.12);
  }
  button:active { transform: translateY(1px); }
  button.primary {
    border-color: #1b6352; color: #fff;
    background: linear-gradient(#31967c, #1f6f5c);
    box-shadow: 0 4px 12px rgba(31,111,92,.28), inset 0 1px 0 rgba(255,255,255,.18);
  }
  button.primary:hover { background: linear-gradient(#37a488, #237965); }
  button.block { width: 100%; margin-top: 12px; }
  #b-resign:hover { color: var(--danger); border-color: #e2b8b1; }
  #b-dead.active {
    border-color: #7d2424; color: #fff;
    background: linear-gradient(#b8473f, #8e2a2a);
    box-shadow: 0 4px 12px rgba(142,42,42,.25);
  }
  input[type=text], input[type=number], select {
    width: 100%; padding: 8px 10px; border: 1px solid #d9cbb0;
    border-radius: 10px; background: #fffdf9; color: var(--ink);
    font-size: 13px; font-family: inherit;
  }
  input:focus, select:focus {
    outline: none; border-color: var(--accent-2);
    box-shadow: 0 0 0 3px rgba(44,143,118,.18);
  }
  .hint { margin-top: 10px; font-size: 11.5px; line-height: 1.5; color: var(--muted); word-break: break-all; }
  .analysis-row {
    display: flex; align-items: baseline; gap: 8px;
    padding: 4px 0; border-bottom: 1px dashed var(--line);
    font-size: 12px; font-variant-numeric: tabular-nums;
  }
  .analysis-row:last-child { border-bottom: 0; }
  .analysis-row .rank { width: 18px; color: var(--muted); }
  .analysis-row .mv { width: 38px; font-weight: 600; }
  .analysis-row .wr { width: 54px; text-align: right; }
  .analysis-row .sc { width: 46px; text-align: right; color: var(--muted); }
  .analysis-row .visits { width: 34px; text-align: right; color: var(--muted); }
  .analysis-row.head {
    color: var(--muted); font-size: 10.5px; font-weight: 400;
    border-bottom: 1px solid var(--line); padding-bottom: 5px;
  }
  .analysis-row.head .mv, .analysis-row.head .wr { font-weight: 400; color: var(--muted); }
  .analysis-row.best .mv, .analysis-row.best .wr { color: var(--accent); }
  .analysis-head { font-size: 12px; line-height: 1.6; margin-bottom: 4px; }
  .analysis-head b { color: var(--accent); }
  .winbar { height: 8px; border-radius: 999px; background: #e8dfcf; overflow: hidden; margin: 6px 0 8px; }
  .winbar span { display: block; height: 100%; width: 0; border-radius: inherit; background: linear-gradient(90deg, #111, #555); transition: width .25s ease; }
  @media (max-width: 1020px) {
    .layout { grid-template-columns: 1fr; }
    .panel { max-width: 720px; width: 100%; margin: 0 auto; }
  }
  @media (max-width: 560px) {
    .topbar { padding: 16px 14px 12px; }
    .layout { padding: 0 14px 28px; gap: 18px; }
    .grid2 { grid-template-columns: 1fr; }
    .status-card { min-width: 0; width: 100%; }
  }
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <div>
        <h1>围棋</h1>
        <p>本地对弈 · 标准规则</p>
      </div>
    </div>
    <div class="status-card">
      <span class="turn-dot is-black" id="turn-dot"></span>
      <div id="status">加载中…</div>
    </div>
  </header>

  <main class="layout">
    <section class="board-area">
      <div class="board-frame">
        <canvas id="board" width="720" height="720"></canvas>
      </div>
      <div class="message" id="msg"></div>
      <p class="board-caption">点击交叉点落子 · 连续两次「停一手」进入数子</p>
    </section>

    <aside class="panel">
      <div class="actions" id="actions">
        <button id="b-ai" disabled>AI 落子</button>
        <button id="b-pass">停一手</button>
        <button id="b-undo">悔棋</button>
        <button id="b-resign">认输</button>
        <button id="b-dead">标记死子: 关</button>
        <button id="b-finish">完成数子</button>
      </div>
      <div class="hint" id="ai-hint"></div>

      <fieldset class="card">
        <legend>AI 分析</legend>
        <button id="b-analysis" class="block">分析: 关</button>
        <div class="hint" id="analysis-hint"></div>
        <div class="analysis-head" id="analysis-summary"></div>
        <div class="winbar"><span id="winbar-black"></span></div>
        <div id="analysis-moves"></div>
      </fieldset>

      <fieldset class="card">
        <legend>新局</legend>
        <div class="grid2">
          <label class="field"><span>棋盘</span>
            <select id="n-size"><option>9</option><option>13</option><option selected>19</option></select>
          </label>
          <label class="field"><span>贴目</span>
            <input id="n-komi" type="number" step="0.5" value="7.5">
          </label>
        </div>
        <label class="field" style="margin-top:10px"><span>劫规则</span>
          <select id="n-ko">
            <option value="chinese" selected>中国（全局同形）</option>
            <option value="simple">简单劫</option>
            <option value="situational">情境超级劫</option>
            <option value="japanese">日本（循环无胜负）</option>
          </select>
        </label>
        <button id="b-new" class="primary block">开始新局</button>
      </fieldset>

      <fieldset class="card">
        <legend>棋谱</legend>
        <label class="field"><span>文件名（可留空）</span>
          <input id="file-name" type="text" placeholder="留空则自动命名">
        </label>
        <div class="grid2" style="margin-top:10px">
          <label class="field"><span>格式</span>
            <select id="file-format"><option value="sgf" selected>.sgf</option><option value="txt">.txt</option></select>
          </label>
          <div class="field"><span>操作</span>
            <div class="btn-row">
              <button id="b-save" class="primary">保存</button>
              <button id="b-load">载入</button>
            </div>
          </div>
        </div>
        <div class="hint" id="records-dir"></div>
      </fieldset>

      <fieldset class="card">
        <legend>设置 / 元信息</legend>
        <div class="grid2">
          <label class="field"><span>黑方</span><input id="m-PB" type="text" placeholder="黑方"></label>
          <label class="field"><span>白方</span><input id="m-PW" type="text" placeholder="白方"></label>
          <label class="field"><span>赛事</span><input id="m-EV" type="text" placeholder="赛事"></label>
          <label class="field"><span>日期</span><input id="m-DT" type="text" placeholder="YYYY-MM-DD"></label>
          <label class="field"><span>贴目</span><input id="m-komi" type="number" step="0.5"></label>
          <label class="field"><span>劫规则</span>
            <select id="m-ko">
              <option value="chinese">chinese</option>
              <option value="simple">simple</option>
              <option value="situational">situational</option>
              <option value="japanese">japanese</option>
            </select>
          </label>
        </div>
        <button id="b-apply" class="primary block">应用</button>
      </fieldset>
    </aside>
  </main>
</div>
<script>
const canvas = document.getElementById('board');
const ctx = canvas.getContext('2d');
const COLUMNS = 'ABCDEFGHJKLMNOPQRSTUVWXYZ';
const BOARD_PX = 720;
const DPR = Math.min(window.devicePixelRatio || 1, 2);
canvas.width = Math.round(BOARD_PX * DPR);
canvas.height = Math.round(BOARD_PX * DPR);

let state = null;
let deadMode = false;
let hover = null;
let hoverKey = '';
let aiBusy = false;
let analysisEnabled = false;
let analysis = null;
let analysisTimer = null;

async function api(path, payload = {}) {
  const res = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload),
  });
  state = await res.json();
  render();
}

async function loadState() {
  const res = await fetch('/api/state');
  state = await res.json();
  render();
  await loadAnalysisState();
}

async function loadAnalysisState() {
  try {
    const res = await fetch('/api/analysis');
    analysis = await res.json();
    analysisEnabled = !!analysis.enabled;
    if (analysisEnabled) startAnalysisPolling();
    renderAnalysis();
  } catch (error) {
    // 分析接口不可用时不影响对弈
  }
}

async function aiMove() {
  if (aiBusy || !state || !state.ai_available || state.over) return;
  aiBusy = true;
  const button = document.getElementById('b-ai');
  button.disabled = true;
  button.textContent = 'AI 思考中…';
  try {
    await api('/api/ai');
  } finally {
    aiBusy = false;
    render();
  }
}

async function toggleAnalysis() {
  const next = !analysisEnabled;
  try {
    await api('/api/analysis', { enabled: next });
  } catch (error) {
    // api() 已把错误写进 state.message
  }
  analysisEnabled = !!(state && state.analysis_enabled);
  if (analysisEnabled) {
    startAnalysisPolling();
  } else {
    stopAnalysisPolling();
    analysis = null;
    draw();
  }
  renderAnalysis();
}

function startAnalysisPolling() {
  if (analysisTimer) return;
  const tick = async () => {
    try {
      const res = await fetch('/api/analysis');
      analysis = await res.json();
      renderAnalysis();
      draw();
    } catch (error) {
      // 网络失败时保留上一次结果
    }
  };
  tick();
  analysisTimer = setInterval(tick, 250);
}

function stopAnalysisPolling() {
  if (analysisTimer) {
    clearInterval(analysisTimer);
    analysisTimer = null;
  }
}

function renderAnalysis() {
  const button = document.getElementById('b-analysis');
  const hint = document.getElementById('analysis-hint');
  const summary = document.getElementById('analysis-summary');
  const list = document.getElementById('analysis-moves');
  const bar = document.getElementById('winbar-black');
  if (!button || !hint || !summary || !list || !bar) return;
  const available = !!(state && state.analysis_available);
  bar.style.width = '0%';
  button.disabled = !available;
  button.textContent = '分析: ' + (analysisEnabled ? '开' : '关');
  button.classList.toggle('primary', analysisEnabled);
  if (!available) {
    hint.textContent = (state && state.analysis_hint) || '分析不可用';
    summary.textContent = '';
    list.innerHTML = '';
    return;
  }
  if (!analysisEnabled) {
    hint.textContent = '点击开启实时分析';
    summary.textContent = '';
    list.innerHTML = '';
    return;
  }
  const visitsText = analysis && typeof analysis.visits === 'number'
    ? (analysis.visits === 0 ? '；持续分析' : '；' + analysis.visits + ' visits')
    : '';
  hint.textContent = '胜率为黑方视角' + visitsText +
    '；棋盘色块为领地预测；正目差表示黑领先';
  if (!analysis || analysis.error) {
    hint.textContent = (analysis && analysis.error) || '分析中…';
    summary.textContent = '';
    list.innerHTML = '';
    return;
  }
  const currentKey = state.position_key || analysis.current_key;
  if (!analysis.analysis || analysis.analysis.key !== currentKey) {
    summary.textContent = '分析中…';
    list.innerHTML = '';
    return;
  }
  const a = analysis.analysis;
  const winrate = (a.root_winrate * 100).toFixed(1);
  const score = (a.root_score_lead >= 0 ? '+' : '') + a.root_score_lead.toFixed(1);
  const searching = a.during_search
    ? (analysis.visits === 0 ? ' · 持续分析' : ' · 搜索中')
    : '';
  summary.innerHTML = '黑胜率 <b>' + winrate + '%</b> · 目差 <b>' + score + '</b>' + searching;
  bar.style.width = (a.root_winrate * 100).toFixed(1) + '%';
  const allMoves = (a.moves || []).slice().sort((x, y) => x.order - y.order);
  const maxVisits = Math.max(1, ...allMoves.map(m => Number(m.visits || 0)));
  const visitThreshold = Math.max(5, maxVisits * 0.01);
  const filtered = allMoves.filter(
    m => m.order === 0 || Number(m.visits || 0) >= visitThreshold
  );
  const moves = (filtered.length ? filtered : allMoves).slice(0, 6);
  const rows = moves.map((m, i) => {
    const vertex = m.vertex === 'pass' ? 'pass' : m.vertex;
    const wr = (m.winrate * 100).toFixed(1) + '%';
    const sc = (m.score_lead >= 0 ? '+' : '') + m.score_lead.toFixed(1);
    const visits = Number(m.visits || 0);
    const visitLabel = visits >= 1000 ? (visits / 1000).toFixed(1) + 'k' : String(visits);
    return '<div class="analysis-row' + (i === 0 ? ' best' : '') + '">' +
      '<span class="rank">' + (i + 1) + '</span>' +
      '<span class="mv">' + vertex + '</span>' +
      '<span class="wr">' + wr + '</span>' +
      '<span class="sc">' + sc + '</span>' +
      '<span class="visits">' + visitLabel + '</span>' +
      '</div>';
  }).join('');
  list.innerHTML =
    '<div class="analysis-row head">' +
    '<span class="rank">#</span><span class="mv">点</span>' +
    '<span class="wr">黑胜率</span><span class="sc">目差</span>' +
    '<span class="visits">访问</span></div>' + rows;
}

function hoshiPoints(size) {
  const pts = [];
  if (size === 19) {
    [3,9,15].forEach(a => [3,9,15].forEach(b => pts.push([a,b])));
  } else if (size === 13) {
    [3,6,9].forEach(a => [3,6,9].forEach(b => pts.push([a,b])));
  } else if (size === 9) {
    [2,6].forEach(a => [2,6].forEach(b => pts.push([a,b])));
    pts.push([4,4]);
  }
  return pts;
}

function geom() {
  const size = state ? state.size : 19;
  const S = canvas.width;
  const pad = S * 0.078;
  const cell = (S - 2*pad) / (size - 1);
  return { size, pad, cell, S };
}

function toScreen(x, y, g) {
  return { cx: g.pad + x*g.cell, cy: g.pad + (g.size - 1 - y)*g.cell };
}

function drawBoard() {
  const g = geom();
  const { size, pad, cell, S } = g;

  const wood = ctx.createLinearGradient(0, 0, S, S);
  wood.addColorStop(0, '#f3d9a3');
  wood.addColorStop(0.52, '#e5bf76');
  wood.addColorStop(1, '#d2a252');
  ctx.fillStyle = wood;
  ctx.fillRect(0, 0, S, S);

  const glow = ctx.createRadialGradient(S*0.46, S*0.4, S*0.12, S*0.5, S*0.5, S*0.78);
  glow.addColorStop(0, 'rgba(255,255,255,0.20)');
  glow.addColorStop(1, 'rgba(110,72,16,0.12)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, S, S);

  ctx.save();
  ctx.globalAlpha = 0.055;
  ctx.strokeStyle = '#6b4610';
  ctx.lineWidth = Math.max(1, S*0.0014);
  for (let i = 0; i < 20; i++) {
    const base = (i + 0.5) / 20 * S;
    ctx.beginPath();
    for (let k = 0; k <= 24; k++) {
      const x = k / 24 * S;
      const y = base + Math.sin(i*1.3 + k*0.7) * S*0.004 + Math.sin(i*0.7) * S*0.006;
      if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.restore();

  ctx.strokeStyle = 'rgba(55,36,10,0.82)';
  ctx.lineWidth = Math.max(1, S*0.0014);
  for (let i = 0; i < size; i++) {
    const p = pad + i*cell;
    ctx.beginPath(); ctx.moveTo(pad, p); ctx.lineTo(pad + (size-1)*cell, p); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(p, pad); ctx.lineTo(p, pad + (size-1)*cell); ctx.stroke();
  }
  ctx.lineWidth = Math.max(1.6, S*0.0026);
  ctx.strokeRect(pad, pad, (size-1)*cell, (size-1)*cell);

  ctx.fillStyle = 'rgba(45,28,6,0.9)';
  const rr = Math.max(2, cell*0.10);
  hoshiPoints(size).forEach(([x, y]) => {
    const p = toScreen(x, y, g);
    ctx.beginPath(); ctx.arc(p.cx, p.cy, rr, 0, Math.PI*2); ctx.fill();
  });

  ctx.font = `600 ${Math.round(cell*0.4)}px -apple-system,"PingFang SC",system-ui,sans-serif`;
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(70,48,18,0.78)';
  ctx.textAlign = 'center';
  for (let i = 0; i < size; i++) {
    ctx.fillText(COLUMNS[i], pad + i*cell, pad*0.48);
  }
  ctx.fillStyle = 'rgba(70,48,18,0.45)';
  for (let i = 0; i < size; i++) {
    ctx.fillText(COLUMNS[i], pad + i*cell, S - pad*0.48);
  }
  ctx.fillStyle = 'rgba(70,48,18,0.78)';
  ctx.textAlign = 'right';
  for (let y = 0; y < size; y++) {
    const p = toScreen(0, y, g);
    ctx.fillText(String(y+1), pad*0.52, p.cy);
  }
  ctx.fillStyle = 'rgba(70,48,18,0.45)';
  ctx.textAlign = 'left';
  for (let y = 0; y < size; y++) {
    const p = toScreen(0, y, g);
    ctx.fillText(String(y+1), S - pad*0.52, p.cy);
  }
}

function drawStone(cx, cy, r, color) {
  ctx.save();
  ctx.shadowColor = 'rgba(35,22,6,0.38)';
  ctx.shadowBlur = r*0.55;
  ctx.shadowOffsetY = r*0.22;
  const g = ctx.createRadialGradient(cx - r*0.34, cy - r*0.38, r*0.08, cx, cy, r*1.12);
  if (color === 1) {
    g.addColorStop(0, '#7d7d7d');
    g.addColorStop(0.35, '#343434');
    g.addColorStop(1, '#050505');
  } else {
    g.addColorStop(0, '#ffffff');
    g.addColorStop(0.55, '#f7f3e9');
    g.addColorStop(1, '#d5ccb8');
  }
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI*2);
  ctx.fillStyle = g;
  ctx.fill();
  ctx.restore();

  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI*2);
  ctx.lineWidth = Math.max(1, r*0.05);
  ctx.strokeStyle = color === 1 ? 'rgba(0,0,0,0.55)' : 'rgba(120,108,86,0.55)';
  ctx.stroke();

  ctx.beginPath();
  ctx.ellipse(cx - r*0.32, cy - r*0.36, r*0.34, r*0.20, -0.6, 0, Math.PI*2);
  ctx.fillStyle = color === 1 ? 'rgba(255,255,255,0.30)' : 'rgba(255,255,255,0.85)';
  ctx.fill();
}

function drawStones() {
  const g = geom();
  const { size, cell } = g;
  const r = cell*0.47;
  const dead = new Set(state.dead || []);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = y*size + x;
      const c = state.grid[idx];
      if (!c) continue;
      const p = toScreen(x, y, g);
      const isDead = dead.has(idx);
      ctx.save();
      ctx.globalAlpha = isDead ? 0.34 : 1.0;
      drawStone(p.cx, p.cy, r, c);
      ctx.restore();
      if (isDead) {
        ctx.strokeStyle = c === 1 ? '#ffe3e3' : '#a3261e';
        ctx.lineWidth = Math.max(1.5, r*0.12);
        ctx.beginPath();
        ctx.moveTo(p.cx - r*0.5, p.cy - r*0.5); ctx.lineTo(p.cx + r*0.5, p.cy + r*0.5);
        ctx.moveTo(p.cx + r*0.5, p.cy - r*0.5); ctx.lineTo(p.cx - r*0.5, p.cy + r*0.5);
        ctx.stroke();
      }
    }
  }
  if (state.last_move !== null && state.last_move !== undefined && state.last_move >= 0) {
    const x = state.last_move % size;
    const y = Math.floor(state.last_move / size);
    const p = toScreen(x, y, g);
    ctx.beginPath();
    ctx.arc(p.cx, p.cy, r*0.24, 0, Math.PI*2);
    ctx.fillStyle = '#e5484d';
    ctx.fill();
    ctx.lineWidth = Math.max(1, r*0.09);
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.stroke();
  }
}

function drawHover() {
  if (!hover || !state || state.over) return;
  if (state.grid[hover.y*state.size + hover.x]) return;
  const g = geom();
  const p = toScreen(hover.x, hover.y, g);
  ctx.save();
  ctx.globalAlpha = 0.32;
  drawStone(p.cx, p.cy, g.cell*0.47, state.to_play);
  ctx.restore();
}

function drawOwnership() {
  if (!analysisEnabled || !analysis || !analysis.analysis || !state) return;
  const a = analysis.analysis;
  if (!a.ownership || a.key !== (state.position_key || analysis.current_key)) return;
  const stones = state.grid ? state.grid.filter(c => c !== 0).length : 0;
  if (stones < 4) return; // 空盘/开局前几手不铺领地，避免看起来像木纹污点
  const g = geom();
  if (a.ownership.length < g.size * g.size) return;
  const half = g.cell * 0.17;
  const radius = g.cell * 0.08;
  ctx.save();
  for (let row = 0; row < g.size; row++) {
    for (let col = 0; col < g.size; col++) {
      const value = a.ownership[row * g.size + col];
      if (Math.abs(value) < 0.35) continue;
      const point = toScreen(col, g.size - 1 - row, g);
      ctx.globalAlpha = Math.min(0.18, Math.abs(value) * 0.22);
      ctx.fillStyle = value > 0 ? '#0b0b0b' : '#fffdf8';
      if (typeof ctx.roundRect === 'function') {
        ctx.beginPath();
        ctx.roundRect(point.cx - half, point.cy - half, half * 2, half * 2, radius);
        ctx.fill();
      } else {
        ctx.fillRect(point.cx - half, point.cy - half, half * 2, half * 2);
      }
    }
  }
  ctx.restore();
}

function draw() {
  drawBoard();
  drawOwnership();
  drawStones();
  drawHover();
}

function statusText() {
  let s = '';
  if (state.over) {
    if (state.no_result) s += '局面循环：无胜负\n';
    else if (state.resigned_by) s += state.result_text + '\n';
    else if (state.finished) {
      if (state.score) s += `面积分  黑 ${state.score[0]}  白 ${state.score[1]}\n`;
      s += state.result_text + '\n';
    } else {
      s += '终局（两次 pass）：标记死子后点「完成数子」\n';
      if (state.score) s += `面积分  黑 ${state.score[0]}  白 ${state.score[1]}\n`;
    }
  } else {
    s += (state.to_play === 1 ? '黑方' : '白方') + ' 行棋\n';
  }
  const ko = { chinese: '中国', simple: '简单劫', situational: '情境劫', japanese: '日本' }[state.ko] || state.ko;
  s += `提子 黑 ${state.captures['1']}  白 ${state.captures['2']}  贴目 ${state.komi}  劫 ${ko}`;
  return s;
}

function render() {
  draw();
  document.getElementById('status').textContent = statusText();
  const msg = state.message || '';
  const msgEl = document.getElementById('msg');
  msgEl.textContent = msg;
  msgEl.classList.toggle(
    'error',
    /illegal|error|错误|非法|失败|超时|不可用|找不到|不存在|无法|已退出|unsupported|already over|no move/i.test(msg)
  );
  document.getElementById('records-dir').textContent = '棋谱目录：' + (state.records_dir || '');
  const counting = state.over && !state.no_result && !state.resigned_by;
  document.getElementById('b-dead').style.display = counting ? '' : 'none';
  document.getElementById('b-finish').style.display = counting ? '' : 'none';
  document.getElementById('b-dead').textContent = '标记死子: ' + (deadMode ? '开' : '关');
  document.getElementById('b-dead').classList.toggle('active', deadMode);
  const md = state.metadata || {};
  ['PB','PW','EV','DT'].forEach(k => { document.getElementById('m-'+k).value = md[k] || ''; });
  document.getElementById('m-komi').value = state.komi;
  document.getElementById('m-ko').value = state.ko;
  const aiButton = document.getElementById('b-ai');
  aiButton.disabled = !state.ai_available || state.ai_thinking || state.over;
  aiButton.textContent = state.ai_thinking ? 'AI 思考中…' : 'AI 落子';
  document.getElementById('ai-hint').textContent = state.ai_available
    ? (state.ai_name ? '引擎：' + state.ai_name : '')
    : (state.ai_hint || '');
  const dot = document.getElementById('turn-dot');
  dot.className = 'turn-dot ' + (state.over ? 'is-over' : (state.to_play === 1 ? 'is-black' : 'is-white'));
  renderAnalysis();
}

function pointFromEvent(e) {
  if (!state) return null;
  const g = geom();
  const rect = canvas.getBoundingClientRect();
  const px = (e.clientX - rect.left) * (canvas.width / rect.width);
  const py = (e.clientY - rect.top) * (canvas.height / rect.height);
  const sx = Math.round((px - g.pad) / g.cell);
  const sy = Math.round((py - g.pad) / g.cell);
  if (sx < 0 || sy < 0 || sx >= g.size || sy >= g.size) return null;
  return { x: sx, y: g.size - 1 - sy };
}

canvas.addEventListener('mousemove', e => {
  const p = pointFromEvent(e);
  const key = p ? p.x + ',' + p.y : '';
  if (key === hoverKey) return;
  hoverKey = key;
  hover = p;
  draw();
});

canvas.addEventListener('mouseleave', () => {
  if (hoverKey === '') return;
  hoverKey = '';
  hover = null;
  draw();
});

canvas.addEventListener('click', e => {
  if (!state) return;
  if (state.ai_thinking) return;
  if (!deadMode && state.over) return;
  const p = pointFromEvent(e);
  if (!p) return;
  const vertex = COLUMNS[p.x] + (p.y + 1);
  api(deadMode ? '/api/dead' : '/api/move', { vertex });
});

document.getElementById('b-ai').onclick = aiMove;
document.getElementById('b-analysis').onclick = toggleAnalysis;
document.getElementById('b-pass').onclick = () => api('/api/pass');
document.getElementById('b-undo').onclick = () => api('/api/undo');
document.getElementById('b-resign').onclick = () => api('/api/resign');
document.getElementById('b-dead').onclick = () => { deadMode = !deadMode; render(); };
document.getElementById('b-finish').onclick = () => { deadMode = false; api('/api/finish'); };
document.getElementById('b-new').onclick = () => api('/api/new', {
  size: parseInt(document.getElementById('n-size').value),
  komi: parseFloat(document.getElementById('n-komi').value),
  ko: document.getElementById('n-ko').value,
});
document.getElementById('b-save').onclick = () =>
  api('/api/save', { name: document.getElementById('file-name').value,
                     format: document.getElementById('file-format').value });
document.getElementById('b-load').onclick = () =>
  api('/api/load', { name: document.getElementById('file-name').value });
document.getElementById('b-apply').onclick = () => api('/api/settings', {
  PB: document.getElementById('m-PB').value,
  PW: document.getElementById('m-PW').value,
  EV: document.getElementById('m-EV').value,
  DT: document.getElementById('m-DT').value,
  komi: document.getElementById('m-komi').value,
  ko: document.getElementById('m-ko').value,
});

loadState();
</script>
</body>
</html>
"""


class WebGame:
    def __init__(
        self,
        record_dir=None,
        engine=None,
        ai_config=None,
        ai_overrides=None,
        ai_config_path=None,
        analyzer=None,
    ):
        self.record_dir = Path(record_dir) if record_dir else default_record_dir()
        self.game = Game()
        self.metadata: dict = {}
        self.finished = False
        self.message = ""
        self._lock = threading.Lock()
        self.engine = engine
        self.ai_thinking = False
        self.ai_hint = ""
        self.ai_config = None
        self.analysis_service = None
        self.analysis_hint = ""
        if self.engine is None and ai_config is not False:
            try:
                config = (
                    ai_config
                    if isinstance(ai_config, AIConfig)
                    else discover_config(ai_overrides, config_path=ai_config_path)
                )
            except ValueError as error:
                config = None
                self.ai_hint = str(error)
            self.ai_config = config
            if config is None:
                if not self.ai_hint:
                    self.ai_hint = "未检测到 KataGo；macOS 可运行 brew install katago"
            elif not config.available():
                self.ai_hint = config.missing_reason()
            else:
                self.engine = KataGoGTP(config)
        elif self.engine is None and ai_config is False:
            self.ai_hint = "AI 已禁用"
        elif isinstance(ai_config, AIConfig):
            self.ai_config = ai_config

        if analyzer is not None:
            self.analysis_service = AnalysisService(self, analyzer)
        elif self.ai_config is not None and self.ai_config.analysis_available():
            self.analysis_service = AnalysisService(
                self,
                KataGoAnalysis(self.ai_config),
            )
        elif ai_config is False:
            self.analysis_hint = "AI 已禁用"
        elif self.ai_config is not None:
            self.analysis_hint = self.ai_config.analysis_missing_reason()
        else:
            self.analysis_hint = self.ai_hint or "未检测到 KataGo"

    def to_state(self) -> dict:
        g = self.game
        score = None
        if g.over and g.resigned_by is None and not g.board.no_result:
            score = list(g.score())
        return {
            "size": g.board.size,
            "komi": g.board.komi,
            "ko": g.board.ko_rule,
            "to_play": g.board.to_play,
            "grid": list(g.board.grid),
            "captures": {str(BLACK): g.board.captures[BLACK], str(WHITE): g.board.captures[WHITE]},
            "last_move": g.last_move,
            "passes": g.passes,
            "over": g.over,
            "no_result": g.board.no_result,
            "resigned_by": g.resigned_by,
            "dead": sorted(g.dead),
            "counting": g.over and g.resigned_by is None and not g.board.no_result,
            "finished": self.finished,
            "score": score,
            "result_text": g.result_text() if g.over else "",
            "metadata": dict(self.metadata),
            "message": self.message,
            "records_dir": str(self.record_dir),
            "ko_rules": list(KO_RULES),
            "position_key": self._position_key(Position.from_game(g)),
            "ai_available": self._ai_available(),
            "ai_thinking": self.ai_thinking,
            "ai_hint": self.ai_hint,
            "ai_name": getattr(self.engine, "name", "") if self.engine is not None else "",
            "analysis_available": self._analysis_available(),
            "analysis_enabled": self.analysis_service.enabled if self.analysis_service else False,
            "analysis_hint": self.analysis_hint,
        }

    def _ai_available(self) -> bool:
        try:
            return bool(self.engine is not None and self.engine.available())
        except Exception:
            return False

    def _analysis_available(self) -> bool:
        try:
            return bool(
                self.analysis_service is not None
                and self.analysis_service.analyzer.available()
            )
        except Exception:
            return False

    def analysis_state(self) -> dict:
        with self._lock:
            current_key = self._position_key(Position.from_game(self.game))
        if self.analysis_service is None:
            return {
                "available": False,
                "enabled": False,
                "hint": self.analysis_hint,
                "analysis": None,
                "current_key": current_key,
                "error": "",
            }
        state = self.analysis_service.snapshot(current_key)
        if not state.get("hint"):
            state["hint"] = self.analysis_hint
        return state

    def set_analysis(self, enabled: bool) -> None:
        if enabled:
            if self.analysis_service is None:
                raise EngineUnavailable(self.analysis_hint or "分析不可用")
            if not self._analysis_available():
                reason = getattr(
                    self.analysis_service.analyzer,
                    "unavailable_reason",
                    lambda: self.analysis_hint,
                )()
                raise EngineUnavailable(reason or self.analysis_hint or "分析不可用")
        if self.analysis_service is not None:
            self.analysis_service.set_enabled(enabled)

    def _invalidate_analysis(self) -> None:
        if self.analysis_service is not None:
            self.analysis_service.invalidate()

    @staticmethod
    def _position_key(position: Position):
        return position.key()

    def request_ai_move(self) -> dict:
        if self.engine is None:
            raise EngineUnavailable(self.ai_hint or "AI 不可用")
        if not self._ai_available():
            reason = getattr(self.engine, "unavailable_reason", lambda: self.ai_hint)()
            raise EngineUnavailable(reason or self.ai_hint or "AI 不可用")
        with self._lock:
            if self.ai_thinking:
                raise EngineError("AI 正在思考，请稍候")
            if self.game.over:
                raise GameOver("game is already over")
            position = Position.from_game(self.game)
            key = self._position_key(position)
            self.ai_thinking = True
            self.ai_hint = ""
        try:
            move = self.engine.genmove(position)
        except EngineError as error:
            with self._lock:
                self.ai_thinking = False
                self.ai_hint = str(error)
            raise
        except Exception as error:
            with self._lock:
                self.ai_thinking = False
                self.ai_hint = str(error)
            raise EngineError(f"AI 调用失败：{error}") from error
        with self._lock:
            self.ai_thinking = False
            current = Position.from_game(self.game)
            if self._position_key(current) != key:
                self.message = "AI 落子已取消：局面已变化"
                return self.to_state()
            if move == RESIGN:
                self.game.resign()
            elif move == PASS:
                self.game.pass_move()
            else:
                try:
                    self.game.play(move)
                except IllegalMove:
                    self.message = f"AI 返回非法手：{format_vertex(move, self.game.board.size)}"
            self._invalidate_analysis()
            return self.to_state()

    def close(self) -> None:
        if self.analysis_service is not None:
            self.analysis_service.close()
        if self.engine is not None:
            self.engine.close()

    def dispatch(self, action: str, payload: dict) -> dict:
        with self._lock:
            self.message = ""
            handler = getattr(self, f"_do_{action}", None)
            if handler is None:
                raise ValueError(f"unknown action {action!r}")
            handler(payload or {})
            return self.to_state()

    def _vertex(self, payload):
        return parse_vertex(payload["vertex"], self.game.board.size)

    def _do_new(self, payload):
        size = int(payload.get("size") or 19)
        komi = float(payload.get("komi") if payload.get("komi") not in (None, "") else 7.5)
        ko = payload.get("ko") or "chinese"
        self.game = Game(size, komi, ko)
        self.metadata = {}
        self.finished = False
        self._invalidate_analysis()

    def _do_move(self, payload):
        if self.game.over:
            raise GameOver("game is already over")
        idx = self._vertex(payload)
        try:
            self.game.play(idx)
        except IllegalMove:
            self.message = f"illegal move: {payload['vertex']}"
        else:
            self._invalidate_analysis()

    def _do_pass(self, payload):
        if self.game.over:
            raise GameOver("game is already over")
        self.game.pass_move()
        self._invalidate_analysis()

    def _do_undo(self, payload):
        try:
            self.game.undo()
            self.finished = False
            self._invalidate_analysis()
        except IllegalMove:
            self.message = "no move to undo"

    def _do_resign(self, payload):
        if not self.game.over:
            self.game.resign()
            self._invalidate_analysis()

    def _do_dead(self, payload):
        idx = self._vertex(payload)
        count = self.game.toggle_dead(idx)
        self.message = f"toggled {count} stone(s)" if count else "no stone at that point"

    def _do_finish(self, payload):
        self.finished = True

    def _do_settings(self, payload):
        for key in META_FIELDS:
            if key in payload:
                value = str(payload[key]).strip()
                if value:
                    self.metadata[key] = value
                else:
                    self.metadata.pop(key, None)
        if payload.get("komi") not in (None, ""):
            self.game.board.komi = float(payload["komi"])
        if payload.get("ko") in KO_RULES:
            self.game.board.ko_rule = payload["ko"]
        self._invalidate_analysis()

    def _do_analysis(self, payload):
        self.set_analysis(bool(payload.get("enabled")))

    def _do_save(self, payload):
        fmt = str(payload.get("format") or DEFAULT_FORMAT).lower()
        name = (payload.get("name") or "").strip() or default_filename(self.metadata, fmt=fmt)
        path = resolve_write_path(name, self.record_dir, default_format=fmt)
        GameRecord.from_game(self.game, self.metadata).save(path)
        self.message = f"saved to {path}"

    def _do_load(self, payload):
        name = (payload.get("name") or "").strip()
        if not name:
            self.message = "usage: provide a file name"
            return
        record = GameRecord.load(resolve_read_path(name, self.record_dir))
        ko = self.game.board.ko_rule
        self.game = record.to_game()
        self.game.board.ko_rule = ko
        merge_record_metadata(self.metadata, record)
        self.finished = False
        self.message = f"loaded {name}"
        self._invalidate_analysis()


def make_handler(webgame: WebGame):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send_json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, text):
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_payload(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_html(PAGE)
            elif self.path == "/api/state":
                with webgame._lock:
                    self._send_json(webgame.to_state())
            elif self.path == "/api/analysis":
                self._send_json(webgame.analysis_state())
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            if not self.path.startswith("/api/"):
                self._send_json({"error": "not found"}, 404)
                return
            action = self.path[len("/api/") :]
            payload = self._read_payload()
            try:
                if action == "ai":
                    state = webgame.request_ai_move()
                else:
                    state = webgame.dispatch(action, payload)
                self._send_json(state)
            except (IllegalMove, GameOver, ValueError, OSError, SGFError, EngineError) as error:
                with webgame._lock:
                    webgame.message = str(error)
                    self._send_json(webgame.to_state(), 400)

    return Handler


def run(
    host="127.0.0.1",
    port=8080,
    record_dir=None,
    open_browser=True,
    ai_config=None,
    ai_overrides=None,
    ai_config_path=None,
):
    webgame = WebGame(
        record_dir=record_dir,
        ai_config=ai_config,
        ai_overrides=ai_overrides,
        ai_config_path=ai_config_path,
    )
    server = ThreadingHTTPServer((host, port), make_handler(webgame))
    url = f"http://{host}:{port}/"
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    print(f"围棋图形界面已启动： {url}   (Ctrl+C 退出)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        webgame.close()
        server.server_close()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="goban web", description="在浏览器中打开围棋图形界面。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--record-dir", default=str(default_record_dir()))
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--no-ai", action="store_true", help="不自动启用 KataGo")
    add_cli_arguments(parser)
    args = parser.parse_args(argv)
    return run(
        host=args.host,
        port=args.port,
        record_dir=args.record_dir,
        open_browser=not args.no_open,
        ai_config=False if args.no_ai else None,
        ai_overrides=overrides_from_args(args),
        ai_config_path=args.ai_config,
    )


if __name__ == "__main__":
    sys.exit(main())
