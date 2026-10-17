from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .board import BLACK, KO_RULES, WHITE, IllegalMove, parse_vertex
from .game import Game, GameOver
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
  .message { min-height: 18px; margin: 10px 0 0; font-size: 13px; text-align: center; color: var(--danger); }
  .message:not(:empty) {
    background: #fff2ef; border: 1px solid #f1c7c0; border-radius: 10px; padding: 8px 12px;
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
        <button id="b-pass">停一手</button>
        <button id="b-undo">悔棋</button>
        <button id="b-resign">认输</button>
        <button id="b-dead">标记死子: 关</button>
        <button id="b-finish">完成数子</button>
      </div>

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

function draw() {
  drawBoard();
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
  s += `提子 黑 ${state.captures['1']}  白 ${state.captures['2']}  贴目 ${state.komi}  劫 ${state.ko}`;
  return s;
}

function render() {
  draw();
  document.getElementById('status').textContent = statusText();
  document.getElementById('msg').textContent = state.message || '';
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
  const dot = document.getElementById('turn-dot');
  dot.className = 'turn-dot ' + (state.over ? 'is-over' : (state.to_play === 1 ? 'is-black' : 'is-white'));
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
  if (!deadMode && state.over) return;
  const p = pointFromEvent(e);
  if (!p) return;
  const vertex = COLUMNS[p.x] + (p.y + 1);
  api(deadMode ? '/api/dead' : '/api/move', { vertex });
});

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
    def __init__(self, record_dir=None):
        self.record_dir = Path(record_dir) if record_dir else default_record_dir()
        self.game = Game()
        self.metadata: dict = {}
        self.finished = False
        self.message = ""
        self._lock = threading.Lock()

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
        }

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

    def _do_move(self, payload):
        if self.game.over:
            raise GameOver("game is already over")
        idx = self._vertex(payload)
        try:
            self.game.play(idx)
        except IllegalMove:
            self.message = f"illegal move: {payload['vertex']}"

    def _do_pass(self, payload):
        if self.game.over:
            raise GameOver("game is already over")
        self.game.pass_move()

    def _do_undo(self, payload):
        try:
            self.game.undo()
            self.finished = False
        except IllegalMove:
            self.message = "no move to undo"

    def _do_resign(self, payload):
        if not self.game.over:
            self.game.resign()

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
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            if not self.path.startswith("/api/"):
                self._send_json({"error": "not found"}, 404)
                return
            action = self.path[len("/api/") :]
            payload = self._read_payload()
            try:
                state = webgame.dispatch(action, payload)
                self._send_json(state)
            except (IllegalMove, GameOver, ValueError, OSError, SGFError) as error:
                with webgame._lock:
                    webgame.message = str(error)
                    self._send_json(webgame.to_state(), 400)

    return Handler


def run(host="127.0.0.1", port=8080, record_dir=None, open_browser=True):
    webgame = WebGame(record_dir=record_dir)
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
        server.server_close()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="goban web", description="在浏览器中打开围棋图形界面。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--record-dir", default=str(default_record_dir()))
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)
    return run(
        host=args.host,
        port=args.port,
        record_dir=args.record_dir,
        open_browser=not args.no_open,
    )


if __name__ == "__main__":
    sys.exit(main())
