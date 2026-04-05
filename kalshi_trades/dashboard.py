#!/usr/bin/env python
"""Browser dashboard for watching multiple Kalshi markets simultaneously."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
import webbrowser
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from websockets.asyncio.server import ServerConnection, serve

from kalshi_trades.auth import KalshiAuth
from kalshi_trades.client import KalshiClient
from kalshi_trades.config import Config
from kalshi_trades.orderbook import OrderBook, SequenceGapError
from kalshi_trades.websocket import KalshiWebSocket

logger = logging.getLogger(__name__)


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kalshi Multi-Watch</title>
  <style>
    :root {
      --bg: #07121a;
      --bg-soft: rgba(16, 33, 45, 0.78);
      --panel: rgba(10, 23, 31, 0.82);
      --line: rgba(171, 202, 209, 0.18);
      --text: #eff7f3;
      --muted: #9ab6be;
      --accent: #f3b45a;
      --accent-soft: rgba(243, 180, 90, 0.16);
      --good: #9be7c4;
      --bad: #ff9b8f;
      --wall: #ffe3b5;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(243, 180, 90, 0.16), transparent 36%),
        radial-gradient(circle at top right, rgba(113, 190, 214, 0.13), transparent 28%),
        linear-gradient(180deg, #09131b 0%, #05090d 100%);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
      background-size: 40px 40px;
      mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.5), transparent 85%);
    }

    main {
      width: min(1500px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }

    .hero {
      display: grid;
      gap: 10px;
      margin-bottom: 24px;
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(14, 30, 40, 0.94), rgba(7, 17, 24, 0.82));
      box-shadow: var(--shadow);
      transform: translateY(8px);
      opacity: 0;
      animation: rise 480ms ease forwards;
    }

    .hero h1 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2rem, 5vw, 3.7rem);
      font-weight: 600;
      letter-spacing: -0.04em;
    }

    .hero p {
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
      max-width: 70ch;
    }

    .status-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      color: var(--muted);
      font-size: 0.95rem;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
    }

    .status-dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 18px rgba(243, 180, 90, 0.65);
    }

    .control-shell {
      display: grid;
      grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
      gap: 18px;
      margin-bottom: 22px;
    }

    .control-panel {
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: linear-gradient(180deg, rgba(11, 25, 33, 0.94), rgba(7, 17, 24, 0.88));
      box-shadow: var(--shadow);
    }

    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }

    .panel-title {
      margin: 0;
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }

    .panel-copy {
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.45;
    }

    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .tool-btn {
      appearance: none;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      padding: 8px 12px;
      border-radius: 999px;
      font: inherit;
      font-size: 0.84rem;
      cursor: pointer;
      transition: background 140ms ease, border-color 140ms ease, transform 140ms ease;
    }

    .tool-btn:hover {
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.18);
    }

    .tool-btn:active {
      transform: translateY(1px);
    }

    .tool-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .tool-btn.is-active {
      background: var(--accent-soft);
      border-color: rgba(243, 180, 90, 0.3);
      color: var(--wall);
    }

    .tool-btn-small {
      padding: 6px 10px;
      font-size: 0.78rem;
    }

    .watcher-list {
      display: grid;
      gap: 10px;
      max-height: 520px;
      overflow: auto;
      padding-right: 4px;
    }

    .watcher-row {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(255, 255, 255, 0.03);
    }

    .watcher-row.is-hidden {
      opacity: 0.52;
    }

    .watcher-check {
      width: 16px;
      height: 16px;
      accent-color: #f3b45a;
      cursor: pointer;
    }

    .watcher-meta {
      min-width: 0;
    }

    .watcher-name {
      font-size: 0.92rem;
      font-weight: 700;
      line-height: 1.2;
    }

    .watcher-sub {
      margin-top: 3px;
      color: var(--muted);
      font-size: 0.79rem;
      line-height: 1.35;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .watcher-controls {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 6px;
    }

    .control-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .control-stat {
      padding: 12px 13px;
      border-radius: 16px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      background: var(--bg-soft);
    }

    .control-stat-label {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }

    .control-stat-value {
      font-family: "SFMono-Regular", Menlo, monospace;
      font-size: 0.94rem;
      font-weight: 700;
    }

    .market-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 18px;
    }

    .market-card {
      border: 1px solid var(--line);
      border-radius: 22px;
      background: linear-gradient(180deg, rgba(12, 27, 36, 0.92), rgba(7, 17, 24, 0.88));
      box-shadow: var(--shadow);
      overflow: hidden;
      opacity: 1;
      transform: translateY(0) scale(1);
      transition: border-color 140ms ease, background 140ms ease;
    }

    .market-card.is-primary {
      border-color: rgba(243, 180, 90, 0.42);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34), 0 0 0 1px rgba(243, 180, 90, 0.18);
    }

    .market-card.has-alert {
      border-color: rgba(255, 155, 143, 0.4);
    }

    .market-card-entering {
      opacity: 0;
      transform: translateY(12px) scale(0.985);
      animation: rise 420ms ease forwards;
    }

    .card-head {
      padding: 18px 18px 12px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 8px;
      background: linear-gradient(180deg, rgba(243, 180, 90, 0.09), transparent);
    }

    .card-title-row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }

    .card-title {
      margin: 0;
      font-size: 1.05rem;
      font-weight: 700;
      line-height: 1.2;
    }

    .card-subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.4;
    }

    .card-badge {
      flex: none;
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid rgba(243, 180, 90, 0.26);
      background: var(--accent-soft);
      color: var(--wall);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.08em;
    }

    .card-tools {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 6px;
      flex: none;
    }

    .alert-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 0 18px 14px;
    }

    .alert-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid rgba(255, 155, 143, 0.24);
      background: rgba(255, 155, 143, 0.1);
      color: var(--bad);
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      padding: 16px 18px;
    }

    .metric {
      padding: 12px 13px;
      border-radius: 16px;
      background: var(--bg-soft);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .metric-label {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }

    .metric-value {
      font-family: "SFMono-Regular", Menlo, monospace;
      font-size: 1rem;
      font-weight: 700;
    }

    .metric-value.good {
      color: var(--good);
    }

    .metric-value.bad {
      color: var(--bad);
    }

    .metric-value.signal {
      color: var(--wall);
    }

    .wall-row {
      margin: 0 18px 16px;
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(243, 180, 90, 0.08);
      border: 1px solid rgba(243, 180, 90, 0.14);
      color: var(--wall);
      font-size: 0.88rem;
    }

    .comparison-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      padding: 16px 18px;
    }

    .dual-market {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      padding: 0 18px 18px;
    }

    .side-shell {
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(3, 10, 15, 0.64);
    }

    .side-shell-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 14px;
      background: rgba(255, 255, 255, 0.03);
    }

    .side-shell-title {
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }

    .side-shell-badge {
      padding: 5px 8px;
      border-radius: 999px;
      border: 1px solid rgba(243, 180, 90, 0.2);
      background: rgba(243, 180, 90, 0.08);
      color: var(--wall);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.1em;
    }

    .side-mini-metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }

    .side-mini-metric {
      padding: 10px 11px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .side-mini-label {
      display: block;
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }

    .side-mini-value {
      font-family: "SFMono-Regular", Menlo, monospace;
      font-size: 0.88rem;
      font-weight: 700;
    }

    .book {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      padding: 0 18px 18px;
    }

    .ladder {
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.05);
      background: rgba(3, 10, 15, 0.64);
    }

    .ladder h3 {
      margin: 0;
      padding: 12px 14px;
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      background: rgba(255, 255, 255, 0.03);
      color: var(--muted);
    }

    .ladder-unified table td:nth-child(2) {
      text-align: center;
    }

    .ladder-unified table td:last-child {
      text-align: right;
    }

    .ladder-side {
      font-size: 0.74rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .ladder-row-ask td {
      background: rgba(255, 155, 143, 0.04);
      color: #ffd6d0;
    }

    .ladder-row-bid td {
      background: rgba(155, 231, 196, 0.04);
      color: #d8fff0;
    }

    .spread-divider td {
      padding: 7px 14px;
      background: rgba(243, 180, 90, 0.12);
      color: var(--wall);
      font-size: 0.73rem;
      font-weight: 800;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      text-align: center;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-family: "SFMono-Regular", Menlo, monospace;
      font-size: 0.88rem;
    }

    td {
      padding: 9px 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.04);
    }

    td:last-child {
      text-align: right;
    }

    tr.wall td {
      color: var(--wall);
      background: rgba(243, 180, 90, 0.07);
    }

    .empty {
      padding: 14px;
      color: var(--muted);
      font-size: 0.9rem;
    }

    @media (max-width: 860px) {
      .control-shell,
      .comparison-grid,
      .dual-market,
      .book,
      .metrics {
        grid-template-columns: 1fr;
      }

      .control-stats {
        grid-template-columns: 1fr;
      }

      main {
        width: min(100vw - 20px, 1500px);
      }

      .hero,
      .market-card {
        border-radius: 18px;
      }
    }

    @keyframes rise {
      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    body.compact-mode .market-grid {
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }

    body.compact-mode .card-subtitle,
    body.compact-mode .panel-copy,
    body.compact-mode .meta,
    body.compact-mode .wall-row,
    body.compact-mode .alert-strip,
    body.compact-mode .book,
    body.compact-mode .dual-market,
    body.compact-mode .side-mini-metrics {
      display: none;
    }

    body.compact-mode .metrics,
    body.compact-mode .comparison-grid {
      padding: 12px 14px 14px;
      gap: 8px;
    }

    body.compact-mode .metric,
    body.compact-mode .control-stat {
      padding: 10px 11px;
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Kalshi Multi-Watch</h1>
      <p>One local dashboard, one stream layer, many markets. This page mirrors the order-book watcher logic without collapsing everything into a single terminal screen.</p>
      <div class="status-row">
        <span class="status-pill"><span class="status-dot"></span><span id="connection-status">Connecting to local stream...</span></span>
        <span class="status-pill">Markets: <strong id="market-count">0</strong></span>
        <span class="status-pill">Updated: <strong id="updated-at">Waiting</strong></span>
      </div>
    </section>
    <section class="control-shell">
      <section class="control-panel">
        <div class="panel-head">
          <h2 class="panel-title">Watchlist</h2>
          <div class="button-row">
            <button class="tool-btn tool-btn-small" data-action="show-all">Show all</button>
            <button class="tool-btn tool-btn-small" data-action="reset-order">Reset order</button>
          </div>
        </div>
        <p class="panel-copy">Toggle visibility, change a card between YES, NO, and BOTH, and reorder the sequence you scan before you fire.</p>
        <div id="watcher-list" class="watcher-list"></div>
      </section>
      <section class="control-panel">
        <div class="panel-head">
          <h2 class="panel-title">Quick Actions</h2>
          <div class="button-row">
            <button class="tool-btn tool-btn-small" data-action="set-all-side" data-side="yes">YES all</button>
            <button class="tool-btn tool-btn-small" data-action="set-all-side" data-side="no">NO all</button>
            <button class="tool-btn tool-btn-small" data-action="set-all-side" data-side="both">BOTH all</button>
            <button class="tool-btn tool-btn-small" data-action="hide-all">Hide all</button>
            <button class="tool-btn tool-btn-small" data-action="toggle-compact">Compact</button>
          </div>
        </div>
        <p class="panel-copy">Use the card controls for single-market adjustments. These buttons sweep the whole board at once.</p>
        <div class="button-row">
          <button class="tool-btn tool-btn-small" data-action="set-sort" data-sort="manual">Manual</button>
          <button class="tool-btn tool-btn-small" data-action="set-sort" data-sort="edge">Edge</button>
          <button class="tool-btn tool-btn-small" data-action="set-sort" data-sort="spread">Spread</button>
          <button class="tool-btn tool-btn-small" data-action="set-sort" data-sort="imbalance">Imbalance</button>
        </div>
        <div class="control-stats">
          <div class="control-stat">
            <span class="control-stat-label">Shown</span>
            <div id="visible-count" class="control-stat-value">0</div>
          </div>
          <div class="control-stat">
            <span class="control-stat-label">Hidden</span>
            <div id="hidden-count" class="control-stat-value">0</div>
          </div>
          <div class="control-stat">
            <span class="control-stat-label">Sides</span>
            <div id="side-mode" class="control-stat-value">--</div>
          </div>
          <div class="control-stat">
            <span class="control-stat-label">Primary</span>
            <div id="primary-name" class="control-stat-value">--</div>
          </div>
        </div>
      </section>
    </section>
    <section id="market-grid" class="market-grid"></section>
  </main>
  <script>
    const wsUrl = `ws://${location.hostname}:__WS_PORT__`;
    const marketGrid = document.getElementById("market-grid");
    const connectionStatus = document.getElementById("connection-status");
    const marketCount = document.getElementById("market-count");
    const updatedAt = document.getElementById("updated-at");
    const watcherList = document.getElementById("watcher-list");
    const visibleCount = document.getElementById("visible-count");
    const hiddenCount = document.getElementById("hidden-count");
    const sideMode = document.getElementById("side-mode");
    const primaryName = document.getElementById("primary-name");
    const markets = new Map();
    const cards = new Map();
    const alertsByTicker = new Map();
    const alertTimers = new Map();
    const pendingTickers = new Set();
    const storageKey = "kalshi-dashboard-ui-v1";
    let fullRenderPending = false;
    let drawScheduled = false;

    function loadUiState() {
      try {
        const parsed = JSON.parse(localStorage.getItem(storageKey) || "{}");
        return {
          hiddenTickers: Array.isArray(parsed.hiddenTickers) ? parsed.hiddenTickers : [],
          tickerOrder: Array.isArray(parsed.tickerOrder) ? parsed.tickerOrder : [],
          viewModeByTicker: parsed.viewModeByTicker && typeof parsed.viewModeByTicker === "object"
            ? parsed.viewModeByTicker
            : {},
          sortMode: ["manual", "edge", "spread", "imbalance"].includes(parsed.sortMode)
            ? parsed.sortMode
            : "manual",
          compactMode: Boolean(parsed.compactMode),
          primaryTicker: typeof parsed.primaryTicker === "string" ? parsed.primaryTicker : "",
        };
      } catch {
        return {
          hiddenTickers: [],
          tickerOrder: [],
          viewModeByTicker: {},
          sortMode: "manual",
          compactMode: false,
          primaryTicker: "",
        };
      }
    }

    const uiState = loadUiState();

    function persistUiState() {
      try {
        localStorage.setItem(storageKey, JSON.stringify(uiState));
      } catch {
        return;
      }
    }

    function syncUiState() {
      const liveTickers = [...markets.keys()].sort((left, right) => left.localeCompare(right));
      const liveSet = new Set(liveTickers);
      uiState.hiddenTickers = uiState.hiddenTickers.filter((ticker) => liveSet.has(ticker));

      const retainedOrder = uiState.tickerOrder.filter((ticker) => liveSet.has(ticker));
      const retainedSet = new Set(retainedOrder);
      liveTickers.forEach((ticker) => {
        if (!retainedSet.has(ticker)) {
          retainedOrder.push(ticker);
        }
      });
      uiState.tickerOrder = retainedOrder;

      Object.keys(uiState.viewModeByTicker).forEach((ticker) => {
        if (!liveSet.has(ticker)) {
          delete uiState.viewModeByTicker[ticker];
        }
      });

      if (uiState.primaryTicker && !liveSet.has(uiState.primaryTicker)) {
        uiState.primaryTicker = "";
      }

      persistUiState();
    }

    function classForImbalance(value) {
      if (value === "--") return "";
      const num = Number(value);
      if (Number.isNaN(num)) return "";
      if (num > 0) return "good";
      if (num < 0) return "bad";
      return "";
    }

    function classForEdge(value) {
      if (value === "--") return "";
      if (value.startsWith("+")) return "signal";
      if (value.startsWith("-")) return "bad";
      return "";
    }

    function isHidden(ticker) {
      return uiState.hiddenTickers.includes(ticker);
    }

    function normalizeMode(mode) {
      return ["yes", "no", "both"].includes(mode) ? mode : "both";
    }

    function getSelectedMode(market) {
      return normalizeMode(uiState.viewModeByTicker[market.market_ticker] || market.default_mode || "both");
    }

    function getSingleView(market, side) {
      return market.views[side] || market.views.yes;
    }

    function getActiveView(market) {
      const mode = getSelectedMode(market);
      if (mode === "both") {
        return getSingleView(market, "yes");
      }
      return getSingleView(market, mode);
    }

    function parsePriceCents(value) {
      if (!value || value === "--") {
        return null;
      }
      const cleaned = String(value).replace("¢", "").replace("+", "");
      const numeric = Number(cleaned);
      return Number.isNaN(numeric) ? null : numeric;
    }

    function parseSignedCents(value) {
      if (!value || value === "--") {
        return null;
      }
      const cleaned = String(value).replace("¢", "");
      const numeric = Number(cleaned);
      return Number.isNaN(numeric) ? null : numeric;
    }

    function parseSignedFloat(value) {
      if (!value || value === "--") {
        return null;
      }
      const numeric = Number(value);
      return Number.isNaN(numeric) ? null : numeric;
    }

    function setTickerHidden(ticker, hidden) {
      if (hidden) {
        if (!isHidden(ticker)) {
          uiState.hiddenTickers.push(ticker);
        }
      } else {
        uiState.hiddenTickers = uiState.hiddenTickers.filter((value) => value !== ticker);
      }
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function setAllVisible(visible) {
      uiState.hiddenTickers = visible
        ? []
        : uiState.tickerOrder.filter((ticker) => markets.has(ticker));
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function showOnlyTicker(ticker) {
      uiState.hiddenTickers = uiState.tickerOrder.filter(
        (value) => markets.has(value) && value !== ticker,
      );
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function moveTicker(ticker, delta) {
      const currentIndex = uiState.tickerOrder.indexOf(ticker);
      if (currentIndex === -1) {
        return;
      }
      const nextIndex = currentIndex + delta;
      if (nextIndex < 0 || nextIndex >= uiState.tickerOrder.length) {
        return;
      }
      const [moved] = uiState.tickerOrder.splice(currentIndex, 1);
      uiState.tickerOrder.splice(nextIndex, 0, moved);
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function resetOrder() {
      uiState.tickerOrder = [...markets.keys()].sort((left, right) => left.localeCompare(right));
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function setTickerMode(ticker, mode) {
      uiState.viewModeByTicker[ticker] = normalizeMode(mode);
      persistUiState();
      pendingTickers.add(ticker);
      scheduleDraw();
    }

    function cycleTickerMode(ticker) {
      const market = markets.get(ticker);
      if (!market) {
        return;
      }
      const current = getSelectedMode(market);
      const next = current === "yes" ? "no" : current === "no" ? "both" : "yes";
      setTickerMode(ticker, next);
    }

    function setAllModes(mode) {
      uiState.tickerOrder.forEach((ticker) => {
        if (markets.has(ticker)) {
          uiState.viewModeByTicker[ticker] = normalizeMode(mode);
          pendingTickers.add(ticker);
        }
      });
      persistUiState();
      scheduleDraw();
    }

    function setSortMode(mode) {
      if (!["manual", "edge", "spread", "imbalance"].includes(mode)) {
        return;
      }
      uiState.sortMode = mode;
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function toggleCompactMode() {
      uiState.compactMode = !uiState.compactMode;
      persistUiState();
      scheduleDraw();
    }

    function togglePrimaryTicker(ticker) {
      uiState.primaryTicker = uiState.primaryTicker === ticker ? "" : ticker;
      persistUiState();
      fullRenderPending = true;
      scheduleDraw();
    }

    function metricViewsForSort(market) {
      const mode = getSelectedMode(market);
      if (mode === "both") {
        return [getSingleView(market, "yes"), getSingleView(market, "no")];
      }
      return [getActiveView(market)];
    }

    function sortMetricForTicker(ticker) {
      const market = markets.get(ticker);
      if (!market) {
        return Number.NEGATIVE_INFINITY;
      }
      const views = metricViewsForSort(market);
      if (uiState.sortMode === "edge") {
        return Math.max(...views.map((view) => Math.abs(parseSignedCents(view.edge_vs_mid) ?? 0)));
      }
      if (uiState.sortMode === "imbalance") {
        return Math.max(...views.map((view) => Math.abs(parseSignedFloat(view.imbalance) ?? 0)));
      }
      if (uiState.sortMode === "spread") {
        const spreads = views
          .map((view) => parsePriceCents(view.spread))
          .filter((value) => value !== null);
        return spreads.length ? -Math.min(...spreads) : Number.NEGATIVE_INFINITY;
      }
      return 0;
    }

    function orderedTickers(includeHidden = true) {
      let ordered;
      if (uiState.sortMode === "manual") {
        ordered = uiState.tickerOrder.filter((ticker) => markets.has(ticker));
      } else {
        ordered = [...markets.keys()].sort((left, right) => {
          const delta = sortMetricForTicker(right) - sortMetricForTicker(left);
          if (delta !== 0) {
            return delta;
          }
          return left.localeCompare(right);
        });
      }

      if (uiState.primaryTicker && ordered.includes(uiState.primaryTicker)) {
        ordered = [
          uiState.primaryTicker,
          ...ordered.filter((ticker) => ticker !== uiState.primaryTicker),
        ];
      }

      if (!includeHidden) {
        return ordered.filter((ticker) => !isHidden(ticker));
      }
      return ordered;
    }

    function visibleTickersInOrder() {
      return orderedTickers(false);
    }

    function setTickerAlerts(ticker, items) {
      if (!items.length) {
        return;
      }
      alertsByTicker.set(ticker, items.slice(0, 3));
      if (alertTimers.has(ticker)) {
        clearTimeout(alertTimers.get(ticker));
      }
      alertTimers.set(ticker, setTimeout(() => {
        alertsByTicker.delete(ticker);
        alertTimers.delete(ticker);
        pendingTickers.add(ticker);
        scheduleDraw();
      }, 6000));
    }

    function updateAlerts(previousMarket, nextMarket) {
      if (!previousMarket) {
        return;
      }
      const items = [];
      ["yes", "no"].forEach((side) => {
        const prevView = previousMarket.views?.[side];
        const nextView = nextMarket.views?.[side];
        if (!prevView || !nextView) {
          return;
        }
        const prevSpread = parsePriceCents(prevView.spread);
        const nextSpread = parsePriceCents(nextView.spread);
        if (prevSpread !== null && nextSpread !== null && nextSpread - prevSpread >= 3) {
          items.push(`${side.toUpperCase()} spread +${nextSpread - prevSpread}¢`);
        }
        if (
          prevView.best_bid_wall &&
          nextView.best_bid_wall &&
          prevView.best_bid_wall !== nextView.best_bid_wall
        ) {
          items.push(`${side.toUpperCase()} bid wall shifted`);
        }
        if (
          prevView.best_ask_wall &&
          nextView.best_ask_wall &&
          prevView.best_ask_wall !== nextView.best_ask_wall
        ) {
          items.push(`${side.toUpperCase()} ask wall shifted`);
        }
      });
      setTickerAlerts(nextMarket.market_ticker, items);
    }

    function renderRows(rows) {
      if (!rows.length) {
        return '<div class="empty">No resting levels yet.</div>';
      }
      return `<table><tbody>${rows.map((row) => `
        <tr class="${row.is_wall ? "wall" : ""}">
          <td>${row.price}</td>
          <td>${row.qty}</td>
        </tr>`).join("")}</tbody></table>`;
    }

    function renderMetric(label, value, tone = "") {
      return `
        <div class="metric">
          <span class="metric-label">${label}</span>
          <div class="metric-value ${tone}">${value}</div>
        </div>`;
    }

    function renderMiniMetric(label, value, tone = "") {
      return `
        <div class="side-mini-metric">
          <span class="side-mini-label">${label}</span>
          <div class="side-mini-value ${tone}">${value}</div>
        </div>`;
    }

    function renderWallRow(view) {
      if (!view.wall_threshold) {
        return "";
      }
      return `
        <div class="wall-row">
          Threshold ${view.wall_threshold} | Best bid wall ${view.best_bid_wall || "--"} | Best ask wall ${view.best_ask_wall || "--"}
        </div>`;
    }

    function renderAlerts(ticker) {
      const items = alertsByTicker.get(ticker) || [];
      if (!items.length) {
        return "";
      }
      return `
        <div class="alert-strip">
          ${items.map((item) => `<span class="alert-chip">${item}</span>`).join("")}
        </div>`;
    }

    function renderModeButtons(ticker, mode) {
      return `
        <button class="tool-btn tool-btn-small ${mode === "yes" ? "is-active" : ""}" data-action="set-mode" data-ticker="${ticker}" data-mode="yes">YES</button>
        <button class="tool-btn tool-btn-small ${mode === "no" ? "is-active" : ""}" data-action="set-mode" data-ticker="${ticker}" data-mode="no">NO</button>
        <button class="tool-btn tool-btn-small ${mode === "both" ? "is-active" : ""}" data-action="set-mode" data-ticker="${ticker}" data-mode="both">BOTH</button>`;
    }

    function renderUnifiedRows(view) {
      const askRows = [...view.asks]
        .map((row) => ({ ...row, kind: "ask", sortValue: parsePriceCents(row.price) ?? 0 }))
        .sort((left, right) => right.sortValue - left.sortValue);
      const bidRows = [...view.bids]
        .map((row) => ({ ...row, kind: "bid", sortValue: parsePriceCents(row.price) ?? 0 }))
        .sort((left, right) => right.sortValue - left.sortValue);

      const askMarkup = askRows.map((row) => `
        <tr class="ladder-row-ask ${row.is_wall ? "wall" : ""}">
          <td class="ladder-side">ASK</td>
          <td>${row.price}</td>
          <td>${row.qty}</td>
        </tr>`).join("") || `
        <tr class="ladder-row-ask">
          <td class="ladder-side">ASK</td>
          <td colspan="2">--</td>
        </tr>`;

      const bidMarkup = bidRows.map((row) => `
        <tr class="ladder-row-bid ${row.is_wall ? "wall" : ""}">
          <td class="ladder-side">BID</td>
          <td>${row.price}</td>
          <td>${row.qty}</td>
        </tr>`).join("") || `
        <tr class="ladder-row-bid">
          <td class="ladder-side">BID</td>
          <td colspan="2">--</td>
        </tr>`;

      return `
        ${askMarkup}
        <tr class="spread-divider"><td colspan="3">${view.label} Ask / Bid Split</td></tr>
        ${bidMarkup}`;
    }

    function renderBook(view) {
      return `
        <section class="ladder ladder-unified">
          <h3>${view.label} Order Book</h3>
          <table>
            <tbody>
              ${renderUnifiedRows(view)}
            </tbody>
          </table>
        </section>`;
    }

    function renderCardHeader(market, mode) {
      const metaView = getSingleView(market, "yes");
      const canReorder = uiState.sortMode === "manual";
      const isPrimary = uiState.primaryTicker === market.market_ticker;
      return `
        <div class="card-head">
          <div class="card-title-row">
            <div>
              <h2 class="card-title">${market.title || market.market_ticker}</h2>
              <p class="card-subtitle">${market.subtitle || market.market_ticker}</p>
            </div>
            <div class="card-tools">
              ${renderModeButtons(market.market_ticker, mode)}
              <button class="tool-btn tool-btn-small ${isPrimary ? "is-active" : ""}" data-action="toggle-primary" data-ticker="${market.market_ticker}">${isPrimary ? "Primary" : "Pin"}</button>
              <button class="tool-btn tool-btn-small" data-action="move-up" data-ticker="${market.market_ticker}" ${canReorder ? "" : "disabled"}>Up</button>
              <button class="tool-btn tool-btn-small" data-action="move-down" data-ticker="${market.market_ticker}" ${canReorder ? "" : "disabled"}>Down</button>
              <button class="tool-btn tool-btn-small" data-action="show-only" data-ticker="${market.market_ticker}">Only</button>
              <button class="tool-btn tool-btn-small" data-action="hide-card" data-ticker="${market.market_ticker}">Hide</button>
            </div>
          </div>
          <div class="meta">
            <span>${market.market_ticker}</span>
            <span>${metaView.last_event}</span>
            <span>Seq ${metaView.last_seq ?? "--"}</span>
          </div>
        </div>`;
    }

    function renderSingleModeBody(market, view, mode) {
      return `
        ${renderCardHeader(market, mode)}
        ${renderAlerts(market.market_ticker)}
        <div class="metrics">
          ${renderMetric("Book", `${view.book_bid} / ${view.book_ask}`)}
          ${renderMetric("Spread", view.spread)}
          ${renderMetric("Mid", view.mid)}
          ${renderMetric("Ticker", view.ticker_last)}
          ${renderMetric("Edge Vs Mid", view.edge_vs_mid, classForEdge(view.edge_vs_mid))}
          ${renderMetric(`${view.label} Bid / Ask`, `${view.ticker_bid} / ${view.ticker_ask}`)}
          ${renderMetric("Depth 5¢", `${view.depth_5c_own} / ${view.depth_5c_other}`)}
          ${renderMetric("Volume / OI", `${view.volume} / ${view.open_interest}`)}
          ${renderMetric("Imbalance", view.imbalance, classForImbalance(view.imbalance))}
          ${renderMetric("Last Trade", `${view.last_trade_price} x ${view.last_trade_count}`)}
          ${renderMetric("Taker", view.last_trade_side)}
        </div>
        ${renderWallRow(view)}
        ${renderBook(view)}`;
    }

    function renderSideShell(view) {
      return `
        <section class="side-shell">
          <div class="side-shell-head">
            <span class="side-shell-title">${view.label} Book</span>
            <span class="side-shell-badge">${view.label}</span>
          </div>
          <div class="side-mini-metrics">
            ${renderMiniMetric("Spread", view.spread)}
            ${renderMiniMetric("Edge", view.edge_vs_mid, classForEdge(view.edge_vs_mid))}
            ${renderMiniMetric("Imbalance", view.imbalance, classForImbalance(view.imbalance))}
            ${renderMiniMetric("Depth 5¢", `${view.depth_5c_own} / ${view.depth_5c_other}`)}
          </div>
          ${renderWallRow(view)}
          ${renderBook(view)}
        </section>`;
    }

    function renderBothModeBody(market, yesView, noView) {
      return `
        ${renderCardHeader(market, "both")}
        ${renderAlerts(market.market_ticker)}
        <div class="comparison-grid">
          ${renderMetric("YES Book", `${yesView.book_bid} / ${yesView.book_ask}`)}
          ${renderMetric("NO Book", `${noView.book_bid} / ${noView.book_ask}`)}
          ${renderMetric("YES Spread", yesView.spread)}
          ${renderMetric("NO Spread", noView.spread)}
          ${renderMetric("YES Edge", yesView.edge_vs_mid, classForEdge(yesView.edge_vs_mid))}
          ${renderMetric("NO Edge", noView.edge_vs_mid, classForEdge(noView.edge_vs_mid))}
          ${renderMetric("Volume / OI", `${yesView.volume} / ${yesView.open_interest}`)}
          ${renderMetric("Trades Y/N", `${yesView.last_trade_price} / ${noView.last_trade_price}`)}
        </div>
        <div class="dual-market">
          ${renderSideShell(yesView)}
          ${renderSideShell(noView)}
        </div>`;
    }

    function renderMarketBody(market) {
      const mode = getSelectedMode(market);
      const yesView = getSingleView(market, "yes");
      const noView = getSingleView(market, "no");
      if (mode === "both") {
        return renderBothModeBody(market, yesView, noView);
      }
      return renderSingleModeBody(market, mode === "yes" ? yesView : noView, mode);
    }

    function renderWatchlist() {
      const canReorder = uiState.sortMode === "manual";
      const rows = orderedTickers(true)
        .filter((ticker) => markets.has(ticker))
        .map((ticker) => {
          const market = markets.get(ticker);
          const mode = getSelectedMode(market);
          const yesView = getSingleView(market, "yes");
          const noView = getSingleView(market, "no");
          const isPrimary = uiState.primaryTicker === ticker;
          const summary = mode === "both"
            ? `BOTH | yes ${yesView.spread} / ${yesView.edge_vs_mid} | no ${noView.spread} / ${noView.edge_vs_mid}`
            : `${mode.toUpperCase()} | spread ${getActiveView(market).spread} | edge ${getActiveView(market).edge_vs_mid}`;
          const hidden = isHidden(ticker);
          return `
            <div class="watcher-row ${hidden ? "is-hidden" : ""}">
              <input class="watcher-check" type="checkbox" data-ticker="${ticker}" ${hidden ? "" : "checked"}>
              <div class="watcher-meta">
                <div class="watcher-name">${market.title || ticker}</div>
                <div class="watcher-sub">${ticker} | ${summary}</div>
              </div>
              <div class="watcher-controls">
                ${renderModeButtons(ticker, mode)}
                <button class="tool-btn tool-btn-small ${isPrimary ? "is-active" : ""}" data-action="toggle-primary" data-ticker="${ticker}">${isPrimary ? "Primary" : "Pin"}</button>
                <button class="tool-btn tool-btn-small" data-action="move-up" data-ticker="${ticker}" ${canReorder ? "" : "disabled"}>Up</button>
                <button class="tool-btn tool-btn-small" data-action="move-down" data-ticker="${ticker}" ${canReorder ? "" : "disabled"}>Down</button>
                <button class="tool-btn tool-btn-small" data-action="show-only" data-ticker="${ticker}">Only</button>
              </div>
            </div>`;
        })
        .join("");

      watcherList.innerHTML = rows || '<div class="empty">No watchers loaded yet.</div>';
    }

    function createCard(market) {
      const card = document.createElement("article");
      card.className = "market-card market-card-entering";
      card.dataset.ticker = market.market_ticker;
      card.innerHTML = renderMarketBody(market);
      applyCardStateClasses(card, market.market_ticker);
      requestAnimationFrame(() => {
        card.classList.remove("market-card-entering");
      });
      return card;
    }

    function upsertCard(market) {
      let card = cards.get(market.market_ticker);
      if (!card) {
        card = createCard(market);
        cards.set(market.market_ticker, card);
        marketGrid.appendChild(card);
        return;
      }
      card.innerHTML = renderMarketBody(market);
      applyCardStateClasses(card, market.market_ticker);
    }

    function applyCardStateClasses(card, ticker) {
      card.classList.toggle("is-primary", uiState.primaryTicker === ticker);
      card.classList.toggle("has-alert", alertsByTicker.has(ticker));
    }

    function reorderVisibleCards() {
      visibleTickersInOrder().forEach((ticker) => {
        const card = cards.get(ticker);
        if (card) {
          marketGrid.appendChild(card);
        }
      });
    }

    function updateSummary() {
      const visible = visibleTickersInOrder().length;
      const total = markets.size;
      const selectedModes = [...markets.values()].map((market) => getSelectedMode(market));
      let sideLabel = "--";
      if (selectedModes.length) {
        sideLabel = selectedModes.every((mode) => mode === selectedModes[0])
          ? selectedModes[0].toUpperCase()
          : "MIXED";
      }
      marketCount.textContent = `${visible} / ${total}`;
      visibleCount.textContent = String(visible);
      hiddenCount.textContent = String(Math.max(total - visible, 0));
      sideMode.textContent = sideLabel;
      primaryName.textContent = uiState.primaryTicker
        ? (markets.get(uiState.primaryTicker)?.title || uiState.primaryTicker)
        : "--";
      updatedAt.textContent = new Date().toLocaleTimeString();
      document.body.classList.toggle("compact-mode", uiState.compactMode);
      document.querySelectorAll('[data-action="toggle-compact"]').forEach((button) => {
        button.classList.toggle("is-active", uiState.compactMode);
      });
      document.querySelectorAll('[data-action="set-sort"]').forEach((button) => {
        button.classList.toggle("is-active", button.dataset.sort === uiState.sortMode);
      });
    }

    function scheduleDraw() {
      if (drawScheduled) {
        return;
      }
      drawScheduled = true;
      requestAnimationFrame(flushDraw);
    }

    function flushDraw() {
      drawScheduled = false;
      syncUiState();

      if (fullRenderPending) {
        marketGrid.replaceChildren();
        cards.clear();
        visibleTickersInOrder().forEach((ticker) => {
          const market = markets.get(ticker);
          if (market) {
            upsertCard(market);
          }
        });
        fullRenderPending = false;
        pendingTickers.clear();
      } else {
        [...pendingTickers]
          .forEach((ticker) => {
            if (isHidden(ticker)) {
              const hiddenCard = cards.get(ticker);
              if (hiddenCard) {
                hiddenCard.remove();
                cards.delete(ticker);
              }
              return;
            }
            const market = markets.get(ticker);
            if (market) {
              upsertCard(market);
            }
          });
        pendingTickers.clear();
        reorderVisibleCards();
      }

      renderWatchlist();
      updateSummary();
    }

    function handleAction(button) {
      const ticker = button.dataset.ticker;
      switch (button.dataset.action) {
        case "show-all":
          setAllVisible(true);
          break;
        case "hide-all":
          setAllVisible(false);
          break;
        case "reset-order":
          resetOrder();
          break;
        case "set-all-side":
          setAllModes(button.dataset.side);
          break;
        case "set-sort":
          setSortMode(button.dataset.sort);
          break;
        case "toggle-compact":
          toggleCompactMode();
          break;
        case "toggle-primary":
          if (ticker) {
            togglePrimaryTicker(ticker);
          }
          break;
        case "set-mode":
          if (ticker) {
            setTickerMode(ticker, button.dataset.mode);
          }
          break;
        case "move-up":
          if (ticker) {
            moveTicker(ticker, -1);
          }
          break;
        case "move-down":
          if (ticker) {
            moveTicker(ticker, 1);
          }
          break;
        case "show-only":
          if (ticker) {
            showOnlyTicker(ticker);
          }
          break;
        case "hide-card":
          if (ticker) {
            setTickerHidden(ticker, true);
          }
          break;
      }
    }

    function attach() {
      const socket = new WebSocket(wsUrl);
      connectionStatus.textContent = "Connecting to local stream...";

      socket.addEventListener("open", () => {
        connectionStatus.textContent = "Connected to local stream";
      });

      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "bootstrap") {
          payload.markets.forEach((market) => markets.set(market.market_ticker, market));
          fullRenderPending = true;
          scheduleDraw();
          return;
        }
        if (payload.type === "market") {
          const previous = markets.get(payload.market.market_ticker);
          markets.set(payload.market.market_ticker, payload.market);
          updateAlerts(previous, payload.market);
          pendingTickers.add(payload.market.market_ticker);
          scheduleDraw();
        }
      });

      socket.addEventListener("close", () => {
        connectionStatus.textContent = "Disconnected. Retrying...";
        setTimeout(attach, 1000);
      });

      socket.addEventListener("error", () => {
        connectionStatus.textContent = "Local stream error";
      });
    }

    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) {
        return;
      }
      handleAction(button);
    });

    document.addEventListener("change", (event) => {
      const checkbox = event.target.closest(".watcher-check");
      if (!checkbox) {
        return;
      }
      setTickerHidden(checkbox.dataset.ticker, !checkbox.checked);
    });

    attach();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a local browser dashboard for multiple Kalshi markets.",
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Optional Kalshi market tickers. If omitted, the dashboard watches your current positions and resting orders.",
    )
    parser.add_argument(
        "--side",
        choices=["yes", "no", "both"],
        default="both",
        help="Default card mode: YES, NO, or BOTH (default: both)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=8,
        help="How many price levels to display per side (default: 8)",
    )
    parser.add_argument(
        "--env",
        choices=["prod", "demo"],
        default="demo",
        help="Environment to connect to (default: demo)",
    )
    parser.add_argument(
        "--wall-threshold",
        default="1000.00",
        help="Highlight price levels with at least this many contracts (default: 1000.00)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the local dashboard server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8765,
        help="HTTP port for the dashboard page (default: 8765)",
    )
    parser.add_argument(
        "--ws-port",
        type=int,
        default=8766,
        help="WebSocket port for browser updates (default: 8766)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the dashboard in the browser automatically",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def _extract_market_ticker(data: dict[str, Any]) -> str | None:
    msg = data.get("msg", {})
    return (
        msg.get("market_ticker")
        or msg.get("ticker")
        or data.get("market_ticker")
        or data.get("ticker")
    )


def _has_non_zero_position(position_fp: str | None) -> bool:
    if not position_fp:
        return False
    try:
        return Decimal(position_fp) != 0
    except InvalidOperation:
        return False


def _tickers_from_positions(client: KalshiClient) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()

    for position in client.paginate_positions(count_filter="position"):
        ticker = position.get("ticker")
        if not ticker or ticker in seen:
            continue
        if not _has_non_zero_position(position.get("position_fp")):
            continue
        seen.add(ticker)
        tickers.append(ticker)

    return tickers


def _tickers_from_resting_orders(client: KalshiClient) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()

    for order in client.paginate_orders(status="resting"):
        ticker = order.get("ticker")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)

    return tickers


def _resolve_tickers(args: argparse.Namespace, client: KalshiClient) -> list[str]:
    if args.tickers:
        return list(dict.fromkeys(args.tickers))

    tickers: list[str] = []
    seen: set[str] = set()

    for ticker in _tickers_from_positions(client):
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)

    for ticker in _tickers_from_resting_orders(client):
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)

    if tickers:
        return tickers

    if args.env == "demo":
        raise RuntimeError(
            "No tickers were provided and no active portfolio positions or resting orders were found in the demo environment. "
            "If your live Kalshi account has the open orders, rerun with --env prod."
        )

    raise RuntimeError(
        "No tickers were provided and no active portfolio positions or resting orders were found. "
        "Pass market tickers explicitly or open a position/order first."
    )


def _carry_market_context(source: OrderBook, target: OrderBook) -> None:
    """Preserve non-book fields when a market is re-seeded from REST."""
    target.ticker_price = source.ticker_price
    target.ticker_yes_bid = source.ticker_yes_bid
    target.ticker_yes_ask = source.ticker_yes_ask
    target.volume_fp = source.volume_fp
    target.open_interest_fp = source.open_interest_fp
    target.last_trade_yes_price = source.last_trade_yes_price
    target.last_trade_no_price = source.last_trade_no_price
    target.last_trade_count_fp = source.last_trade_count_fp
    target.last_trade_side = source.last_trade_side
    target.last_trade_ts = source.last_trade_ts


class DashboardHTTPServer:
    """Serve a single embedded dashboard page from a background thread."""

    def __init__(self, host: str, port: int, ws_port: int) -> None:
        page = DASHBOARD_HTML.replace("__WS_PORT__", str(ws_port)).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                if path not in ("/", "/index.html"):
                    # Embedded viewers may append query params or request a
                    # nested path; serve the app shell so the dashboard stays reachable.
                    path = "/"
                if path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(page)))
                    self.end_headers()
                    self.wfile.write(page)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="kalshi-dashboard-http",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


class DashboardHub:
    """Hold market state and broadcast updates to connected browser clients."""

    def __init__(
        self,
        books: dict[str, OrderBook],
        market_meta: dict[str, dict[str, str]],
        *,
        side: str,
        depth: int,
        wall_threshold: str | None,
    ) -> None:
        self._books = books
        self._market_meta = market_meta
        self._side = side
        self._depth = depth
        self._wall_threshold = wall_threshold
        self._clients: set[ServerConnection] = set()

    def _market_view(self, ticker: str) -> dict[str, Any]:
        meta = self._market_meta.get(ticker, {})
        return {
            "market_ticker": ticker,
            "title": meta.get("title", ticker),
            "subtitle": meta.get("subtitle", ticker),
            "default_mode": self._side,
            "views": {
                "yes": self._books[ticker].to_view(
                    side="yes",
                    depth=self._depth,
                    wall_threshold=self._wall_threshold,
                ),
                "no": self._books[ticker].to_view(
                    side="no",
                    depth=self._depth,
                    wall_threshold=self._wall_threshold,
                ),
            },
        }

    def bootstrap_payload(self) -> str:
        payload = {
            "type": "bootstrap",
            "markets": [self._market_view(ticker) for ticker in sorted(self._books)],
        }
        return json.dumps(payload)

    async def handle_browser(self, websocket: ServerConnection) -> None:
        self._clients.add(websocket)
        try:
            await websocket.send(self.bootstrap_payload())
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    async def publish(self, ticker: str) -> None:
        if ticker not in self._books or not self._clients:
            return
        message = json.dumps({
            "type": "market",
            "market": self._market_view(ticker),
        })
        await asyncio.gather(
            *(self._safe_send(client, message) for client in tuple(self._clients)),
            return_exceptions=True,
        )

    async def _safe_send(self, websocket: ServerConnection, message: str) -> None:
        try:
            await websocket.send(message)
        except Exception:
            self._clients.discard(websocket)


def _seed_books(
    client: KalshiClient,
    tickers: list[str],
) -> tuple[dict[str, OrderBook], dict[str, dict[str, str]]]:
    books: dict[str, OrderBook] = {}
    meta: dict[str, dict[str, str]] = {}

    for ticker in tickers:
        try:
            books[ticker] = OrderBook.from_rest(
                ticker,
                client.get_market_orderbook(ticker),
            )
        except Exception as exc:
            logger.warning("REST seed failed for %s: %s", ticker, exc)
            books[ticker] = OrderBook(ticker)

        try:
            market = client.get_market(ticker).get("market", {})
            meta[ticker] = {
                "title": market.get("title", ticker),
                "subtitle": market.get("subtitle", ticker),
            }
        except Exception as exc:
            logger.warning("Market metadata lookup failed for %s: %s", ticker, exc)
            meta[ticker] = {
                "title": ticker,
                "subtitle": ticker,
            }

    return books, meta


async def main() -> None:
    args = parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    config = Config(env=args.env)
    auth = KalshiAuth(
        api_key=config.get_api_key(),
        key_path=config.get_private_key_path(),
    )
    client = KalshiClient(config=config, auth=auth)
    tickers = _resolve_tickers(args, client)
    books, market_meta = _seed_books(client, tickers)
    hub = DashboardHub(
        books,
        market_meta,
        side=args.side,
        depth=args.depth,
        wall_threshold=args.wall_threshold,
    )

    http_server = DashboardHTTPServer(args.host, args.http_port, args.ws_port)
    http_server.start()

    url = f"http://{args.host}:{args.http_port}"
    print(f"Dashboard URL: {url}")
    print(f"Watching: {', '.join(tickers)}")
    if not args.no_open:
        with suppress(Exception):
            webbrowser.open(url)

    ws = KalshiWebSocket(config=config, auth=auth)

    async def resync_book(ticker: str, reason: Exception | None = None) -> None:
        previous = books.get(ticker, OrderBook(ticker))
        if reason is not None and args.debug:
            print(f"Resyncing {ticker} after {type(reason).__name__}.")
        try:
            orderbook_data = await asyncio.to_thread(client.get_market_orderbook, ticker)
        except Exception as exc:
            logger.warning("REST resync failed for %s: %s", ticker, exc)
            return

        refreshed = OrderBook.from_rest(ticker, orderbook_data)
        _carry_market_context(previous, refreshed)
        refreshed.last_event = "resync"
        books[ticker] = refreshed
        await hub.publish(ticker)

    async def publish_update(data: dict[str, Any], update_fn: Any) -> None:
        ticker = _extract_market_ticker(data)
        if ticker is None:
            return
        book = books.get(ticker)
        if book is None:
            book = OrderBook(ticker)
            books[ticker] = book
            market_meta.setdefault(ticker, {"title": ticker, "subtitle": ticker})
        try:
            update_fn(book, data)
        except SequenceGapError as exc:
            await resync_book(ticker, exc)
            return
        await hub.publish(ticker)

    async def on_snapshot(data: dict[str, Any]) -> None:
        await publish_update(
            data,
            lambda book, payload: book.apply_snapshot(
                payload["msg"],
                seq=payload.get("seq"),
            ),
        )

    async def on_delta(data: dict[str, Any]) -> None:
        await publish_update(
            data,
            lambda book, payload: book.apply_delta(
                payload["msg"],
                seq=payload.get("seq"),
            ),
        )

    async def on_ticker(data: dict[str, Any]) -> None:
        await publish_update(data, lambda book, payload: book.update_ticker(payload["msg"]))

    async def on_trade(data: dict[str, Any]) -> None:
        await publish_update(data, lambda book, payload: book.update_trade(payload["msg"]))

    def on_error(data: dict[str, Any]) -> None:
        raise RuntimeError(f"Kalshi WebSocket error: {data.get('msg')}")

    ws.on("orderbook_snapshot", on_snapshot)
    ws.on("orderbook_delta", on_delta)
    ws.on("ticker", on_ticker)
    ws.on("trade", on_trade)
    ws.on("error", on_error)

    async def subscribe_on_connect(ws_client: KalshiWebSocket) -> None:
        await ws_client.subscribe(
            channels=["orderbook_delta"],
            market_tickers=tickers,
        )
        await ws_client.subscribe(
            channels=["ticker"],
            market_tickers=tickers,
        )
        await ws_client.subscribe(
            channels=["trade"],
            market_tickers=tickers,
        )

    try:
        async with serve(hub.handle_browser, args.host, args.ws_port):
            await ws.run_forever(subscribe_on_connect=subscribe_on_connect)
    finally:
        http_server.stop()


def cli() -> None:
    """Sync entry point for the ``kalshi-view`` console script."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    cli()
