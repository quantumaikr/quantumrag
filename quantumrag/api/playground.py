"""Web playground — browser-based UI for testing QuantumRAG.

Serves a single-page app at ``/playground`` that lets users:
- Upload or paste text documents for ingest
- Query the knowledge base with live streaming
- View sources, confidence, and engine status
- Inspect the RAG pipeline trace (retrieval, reranking, generation steps)
- Submit feedback on answers

No extra dependencies — pure HTML/CSS/JS served via FastAPI.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

_PLAYGROUND_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QuantumRAG Playground</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2: #242736;
    --border: #2e3144; --text: #e4e4e7; --muted: #8b8fa3;
    --primary: #6366f1; --primary-hover: #818cf8;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --blue: #3b82f6; --cyan: #06b6d4; --orange: #f97316;
    --radius: 10px; --font: 'Inter', -apple-system, sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: var(--font); background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }

  /* Layout */
  .app { display: flex; flex-direction: column; height: 100vh; }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 24px; border-bottom: 1px solid var(--border); background: var(--surface);
  }
  .header-left { display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 18px; font-weight: 600; }
  header h1 span { color: var(--primary); }
  .header-actions { display: flex; align-items: center; gap: 8px; }
  .status-badge {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--muted); padding: 4px 12px;
    background: var(--surface2); border-radius: 20px;
  }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); }
  .status-dot.error { background: var(--red); }

  main { flex: 1; display: flex; gap: 0; overflow: hidden; min-height: 0; }

  /* Sidebar */
  .sidebar {
    width: 340px; min-width: 300px; border-right: 1px solid var(--border);
    display: flex; flex-direction: column; background: var(--surface);
  }
  .sidebar-header { padding: 12px 16px; border-bottom: 1px solid var(--border); }
  .sidebar-body { flex: 1; overflow-y: auto; padding: 16px; }

  /* Tabs */
  .tabs { display: flex; gap: 4px; }
  .tab {
    flex: 1; padding: 7px; font-size: 12px; font-weight: 500; text-align: center;
    background: var(--surface2); border: 1px solid var(--border); border-radius: 6px;
    cursor: pointer; color: var(--muted); transition: all 0.15s;
  }
  .tab.active { background: var(--primary); color: white; border-color: var(--primary); }
  .tab:hover:not(.active) { color: var(--text); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* Forms */
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; font-weight: 500; }
  input[type="text"], textarea, select {
    width: 100%; padding: 10px 12px; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 6px; color: var(--text);
    font-size: 14px; font-family: var(--font); resize: vertical;
    transition: border-color 0.15s;
  }
  input:focus, textarea:focus, select:focus { outline: none; border-color: var(--primary); }
  textarea { min-height: 100px; }
  .form-group { margin-bottom: 14px; }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 9px 14px; font-size: 13px; font-weight: 500; border: none;
    border-radius: 6px; cursor: pointer; transition: all 0.15s; width: 100%;
    font-family: var(--font);
  }
  .btn-primary { background: var(--primary); color: white; }
  .btn-primary:hover { background: var(--primary-hover); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { background: var(--border); }
  .btn-sm { padding: 5px 10px; font-size: 12px; width: auto; }
  .btn-danger { background: rgba(239,68,68,0.1); color: var(--red); border: 1px solid rgba(239,68,68,0.2); }
  .btn-danger:hover { background: rgba(239,68,68,0.2); }

  /* File upload */
  .upload-area {
    border: 2px dashed var(--border); border-radius: var(--radius);
    padding: 20px; text-align: center; cursor: pointer;
    transition: all 0.15s; margin-bottom: 8px;
  }
  .upload-area:hover, .upload-area.drag-over { border-color: var(--primary); background: rgba(99,102,241,0.05); }
  .upload-area p { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .upload-area .icon { font-size: 24px; }
  .upload-area.has-files { border-color: var(--primary); border-style: solid; background: rgba(99,102,241,0.04); }
  .file-input { display: none; }

  /* File list */
  .file-list { margin-bottom: 10px; }
  .file-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 10px; margin-bottom: 3px; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 6px; font-size: 12px;
  }
  .file-item .file-info { display: flex; align-items: center; gap: 6px; overflow: hidden; }
  .file-item .file-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px; }
  .file-item .file-size { color: var(--muted); font-size: 11px; white-space: nowrap; }
  .file-item .file-status { font-size: 11px; font-weight: 600; white-space: nowrap; }
  .file-item .file-status.pending { color: var(--muted); }
  .file-item .file-status.uploading { color: var(--blue); }
  .file-item .file-status.processing { color: var(--yellow); }
  .file-item .file-status.done { color: var(--green); }
  .file-item .file-status.error { color: var(--red); }
  .file-item .file-remove {
    background: none; border: none; color: var(--muted); cursor: pointer;
    font-size: 16px; padding: 0 4px; line-height: 1; transition: color 0.15s;
  }
  .file-item .file-remove:hover { color: var(--red); }

  /* Progress bar */
  .progress-bar {
    width: 100%; height: 4px; background: var(--surface2);
    border-radius: 2px; margin-top: 8px; overflow: hidden; display: none;
  }
  .progress-bar.active { display: block; }
  .progress-bar .progress-fill {
    height: 100%; background: var(--primary); border-radius: 2px;
    transition: width 0.3s ease; width: 0%;
  }
  .progress-bar .progress-fill.done { background: var(--green); }
  .progress-bar .progress-fill.error { background: var(--red); }

  /* Ingest result */
  .ingest-result {
    margin-top: 8px; padding: 8px 12px; border-radius: 8px;
    font-size: 12px; display: none;
  }
  .ingest-result.success { display: block; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2); color: var(--green); }
  .ingest-result.error { display: block; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); color: var(--red); }

  /* Section divider */
  .section-divider {
    display: flex; align-items: center; gap: 10px; margin: 10px 0 8px;
    font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;
  }
  .section-divider::before, .section-divider::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
  }

  /* Chat area */
  .chat-area { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 24px; min-height: 0; }
  .chat-input-area { flex-shrink: 0; padding: 12px 24px; border-top: 1px solid var(--border); background: var(--surface); }
  .chat-input-row { display: flex; gap: 8px; }
  .chat-input-row input { flex: 1; }

  /* Messages */
  .message { margin-bottom: 24px; max-width: 860px; }
  .message-user { margin-left: auto; }
  .message-header { font-size: 12px; color: var(--muted); margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
  .message-body { padding: 16px 20px; border-radius: var(--radius); font-size: 14px; line-height: 1.7; }
  .message-user .message-body {
    background: var(--primary); color: white; border-bottom-right-radius: 2px;
    white-space: pre-wrap; word-break: break-word;
  }
  .message-assistant .message-body {
    background: var(--surface2); border-bottom-left-radius: 2px;
  }

  /* ===== Markdown rendered content ===== */
  .md-content { word-break: break-word; }
  .md-content p { margin-bottom: 12px; }
  .md-content p:last-child { margin-bottom: 0; }
  .md-content strong { color: #f1f5f9; font-weight: 600; }
  .md-content em { color: var(--cyan); font-style: italic; }
  .md-content h1, .md-content h2, .md-content h3, .md-content h4 {
    color: #f1f5f9; font-weight: 700; margin: 20px 0 10px 0;
    padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }
  .md-content h1 { font-size: 20px; }
  .md-content h2 { font-size: 17px; }
  .md-content h3 { font-size: 15px; border-bottom: none; }
  .md-content h4 { font-size: 14px; border-bottom: none; color: var(--muted); }
  .md-content code {
    font-family: var(--mono); font-size: 12.5px;
    background: rgba(99,102,241,0.15); color: var(--primary-hover);
    padding: 2px 6px; border-radius: 4px;
  }
  .md-content pre {
    background: #0d0f14; border: 1px solid var(--border); border-radius: 8px;
    padding: 14px 16px; margin: 12px 0; overflow-x: auto;
  }
  .md-content pre code {
    background: none; color: var(--text); padding: 0;
    font-size: 12.5px; line-height: 1.6;
  }
  .md-content ul, .md-content ol {
    margin: 8px 0 12px 0; padding-left: 24px;
  }
  .md-content li { margin-bottom: 6px; line-height: 1.6; }
  .md-content li::marker { color: var(--primary); }
  .md-content blockquote {
    border-left: 3px solid var(--primary);
    padding: 10px 16px; margin: 12px 0;
    background: rgba(99,102,241,0.06); border-radius: 0 6px 6px 0;
    color: var(--muted); font-style: italic;
  }
  .md-content hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
  .md-content table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }
  .md-content th {
    background: var(--surface); padding: 8px 12px; text-align: left;
    border-bottom: 2px solid var(--border); font-weight: 600; color: #f1f5f9;
  }
  .md-content td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
  .md-content tr:hover td { background: rgba(99,102,241,0.04); }

  /* Citation references [1] [2] */
  .cite-ref {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 20px; height: 20px; padding: 0 5px;
    background: rgba(99,102,241,0.2); color: var(--primary-hover);
    font-size: 11px; font-weight: 700; border-radius: 4px;
    cursor: default; vertical-align: middle; margin: 0 1px;
    transition: background 0.15s;
  }
  .cite-ref:hover { background: rgba(99,102,241,0.35); }

  /* Confidence line */
  .md-content .confidence-line {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 8px; padding: 6px 12px;
    border-radius: 6px; font-size: 13px; font-weight: 600;
  }
  .confidence-line.high { background: rgba(34,197,94,0.1); color: var(--green); }
  .confidence-line.medium { background: rgba(234,179,8,0.1); color: var(--yellow); }
  .confidence-line.low { background: rgba(239,68,68,0.1); color: var(--red); }

  /* Sources */
  .sources-section { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 12px; }
  .sources-toggle {
    display: flex; align-items: center; gap: 6px; cursor: pointer;
    font-size: 11px; color: var(--muted); text-transform: uppercase; font-weight: 600;
    letter-spacing: 0.5px; margin-bottom: 8px; user-select: none;
  }
  .sources-toggle:hover { color: var(--text); }
  .sources-toggle .arrow { transition: transform 0.2s; display: inline-block; font-size: 10px; }
  .sources-toggle .arrow.open { transform: rotate(90deg); }
  .source-card {
    padding: 10px 14px; margin-top: 6px; background: var(--surface);
    border: 1px solid var(--border); border-radius: 8px; font-size: 12px;
    transition: border-color 0.15s;
  }
  .source-card:hover { border-color: rgba(99,102,241,0.4); }
  .source-card .source-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
  .source-card .source-title { font-weight: 600; color: var(--primary-hover); }
  .source-card .source-meta { color: var(--muted); font-size: 11px; }
  .source-card .source-score {
    font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
  }
  .source-card .source-score.high { background: rgba(34,197,94,0.12); color: var(--green); }
  .source-card .source-score.mid { background: rgba(234,179,8,0.12); color: var(--yellow); }
  .source-card .source-score.low { background: rgba(239,68,68,0.12); color: var(--red); }
  .source-card .source-excerpt {
    color: var(--muted); line-height: 1.5; margin-top: 4px;
    max-height: 0; overflow: hidden; transition: max-height 0.3s ease;
  }
  .source-card.expanded .source-excerpt { max-height: 300px; }
  .source-card .expand-btn {
    background: none; border: none; color: var(--primary); cursor: pointer;
    font-size: 11px; padding: 2px 0; margin-top: 2px;
  }

  /* Confidence badge (header) */
  .confidence {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  }
  .confidence.high { background: rgba(34,197,94,0.15); color: var(--green); }
  .confidence.medium { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .confidence.low { background: rgba(239,68,68,0.15); color: var(--red); }

  /* ===== RAG Pipeline Trace ===== */
  .trace-section {
    margin-top: 12px; border-top: 1px solid var(--border); padding-top: 10px;
  }
  .trace-toggle {
    display: flex; align-items: center; gap: 6px; cursor: pointer;
    font-size: 11px; color: var(--muted); text-transform: uppercase; font-weight: 600;
    letter-spacing: 0.5px; margin-bottom: 8px; user-select: none;
  }
  .trace-toggle:hover { color: var(--text); }
  .trace-toggle .arrow { transition: transform 0.2s; display: inline-block; font-size: 10px; }
  .trace-toggle .arrow.open { transform: rotate(90deg); }
  .trace-body { display: none; }
  .trace-body.open { display: block; }
  .trace-pipeline {
    position: relative; padding-left: 20px;
  }
  .trace-pipeline::before {
    content: ''; position: absolute; left: 7px; top: 4px; bottom: 4px;
    width: 2px; background: var(--border);
  }
  .trace-step {
    position: relative; margin-bottom: 8px; padding: 8px 12px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    font-size: 12px; transition: border-color 0.15s;
  }
  .trace-step:hover { border-color: rgba(99,102,241,0.3); }
  .trace-step::before {
    content: ''; position: absolute; left: -17px; top: 12px;
    width: 10px; height: 10px; border-radius: 50%;
    border: 2px solid var(--primary); background: var(--bg);
  }
  .trace-step-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 2px;
  }
  .trace-step-name { font-weight: 600; color: var(--text); text-transform: capitalize; }
  .trace-step-latency {
    font-size: 11px; font-family: var(--mono); padding: 1px 6px;
    border-radius: 4px; font-weight: 600;
  }
  .trace-step-latency.fast { background: rgba(34,197,94,0.1); color: var(--green); }
  .trace-step-latency.normal { background: rgba(234,179,8,0.1); color: var(--yellow); }
  .trace-step-latency.slow { background: rgba(239,68,68,0.1); color: var(--red); }
  .trace-step-result {
    color: var(--muted); font-size: 11px; line-height: 1.5;
    white-space: pre-wrap; word-break: break-word;
  }
  .trace-step-details {
    margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--border);
    font-size: 11px; color: var(--muted); font-family: var(--mono);
  }
  .trace-summary {
    display: flex; gap: 12px; margin-bottom: 10px; flex-wrap: wrap;
  }
  .trace-summary-item {
    display: flex; align-items: center; gap: 4px;
    font-size: 11px; padding: 4px 10px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  }
  .trace-summary-item .label { color: var(--muted); }
  .trace-summary-item .value { font-weight: 600; font-family: var(--mono); }

  /* Feedback */
  .feedback-row { display: flex; align-items: center; gap: 4px; margin-top: 10px; }
  .feedback-btn {
    width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
    font-size: 12px; background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; cursor: pointer; color: var(--muted); transition: all 0.15s;
  }
  .feedback-btn:hover { border-color: var(--primary); color: var(--primary); }
  .feedback-btn.selected { background: var(--primary); color: white; border-color: var(--primary); }

  /* Status cards */
  .status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
  .stat-card {
    padding: 12px; background: var(--surface2); border-radius: 6px;
    border: 1px solid var(--border);
  }
  .stat-card .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; }
  .stat-card .stat-value { font-size: 18px; font-weight: 700; margin-top: 4px; }

  /* Doc list */
  .doc-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 0; border-bottom: 1px solid var(--border);
  }
  .doc-item-info { flex: 1; overflow: hidden; }
  .doc-item-title { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .doc-item-meta { font-size: 11px; color: var(--muted); }
  .doc-item-delete {
    background: none; border: none; color: var(--muted); cursor: pointer;
    font-size: 14px; padding: 4px 6px; border-radius: 4px; transition: all 0.15s;
  }
  .doc-item-delete:hover { color: var(--red); background: rgba(239,68,68,0.1); }

  /* Query options */
  .query-options {
    display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
    padding: 6px 0; font-size: 12px;
  }
  .query-options label { margin-bottom: 0; display: flex; align-items: center; gap: 4px; }
  .query-options input[type="range"] { width: 80px; accent-color: var(--primary); }
  .query-options .toggle-label { display: flex; align-items: center; gap: 4px; cursor: pointer; }
  .toggle-switch {
    position: relative; width: 32px; height: 18px; background: var(--border);
    border-radius: 9px; cursor: pointer; transition: background 0.2s;
  }
  .toggle-switch.on { background: var(--primary); }
  .toggle-switch::after {
    content: ''; position: absolute; top: 2px; left: 2px;
    width: 14px; height: 14px; background: white; border-radius: 50%;
    transition: transform 0.2s;
  }
  .toggle-switch.on::after { transform: translateX(14px); }

  /* Empty state */
  .empty-state { text-align: center; padding: 40px 24px; color: var(--muted); }
  .empty-state .icon { font-size: 40px; margin-bottom: 12px; }
  .empty-state h3 { font-size: 16px; color: var(--text); margin-bottom: 8px; }
  .empty-state p { font-size: 13px; line-height: 1.6; margin-bottom: 20px; }

  /* Example queries */
  .example-queries { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
  .example-query {
    padding: 8px 14px; font-size: 12px; color: var(--primary-hover);
    background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.2);
    border-radius: 20px; cursor: pointer; transition: all 0.15s;
    max-width: 280px; text-align: center;
  }
  .example-query:hover { background: rgba(99,102,241,0.15); border-color: var(--primary); }

  /* Latency badge in header */
  .latency-badge {
    font-size: 11px; font-family: var(--mono); color: var(--muted);
    padding: 2px 6px; background: var(--bg); border-radius: 4px;
  }

  /* Spinner */
  .spinner {
    display: inline-block; width: 14px; height: 14px;
    border: 2px solid var(--border); border-top-color: var(--primary);
    border-radius: 50%; animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  @media (max-width: 768px) {
    main { flex-direction: column; }
    .sidebar { width: 100%; min-width: unset; border-right: none; border-bottom: 1px solid var(--border); max-height: 45vh; }
    .chat-messages { padding: 16px; }
    .chat-input-area { padding: 10px 16px; }
  }
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="header-left">
      <h1><span>Quantum</span>RAG Playground</h1>
      <div class="status-badge" id="statusBadge">
        <div class="status-dot" id="statusDot"></div>
        <span id="statusText">Connecting...</span>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn btn-secondary btn-sm" onclick="clearChat()" title="Clear chat">Clear</button>
    </div>
  </header>
  <main>
    <div class="sidebar">
      <div class="sidebar-header">
        <div class="tabs">
          <div class="tab active" data-tab="ingest">Ingest</div>
          <div class="tab" data-tab="settings">Options</div>
          <div class="tab" data-tab="status">Status</div>
        </div>
      </div>
      <div class="sidebar-body">
        <!-- Ingest Tab -->
        <div class="tab-content active" id="tab-ingest">
          <div class="form-group">
            <label>Upload Files</label>
            <div class="upload-area" id="uploadArea">
              <div class="icon">&#128195;</div>
              <p>Drop files here or click to browse<br><small>.txt .md .pdf .csv .html .hwp .hwpx (max 100MB)</small></p>
            </div>
            <input type="file" class="file-input" id="fileInput" multiple
                   accept=".txt,.md,.pdf,.csv,.json,.html,.hwp,.hwpx,.docx,.pptx,.xlsx">
            <div class="file-list" id="fileList"></div>
          </div>
          <div class="section-divider">or</div>
          <div class="form-group">
            <label>Paste text directly</label>
            <textarea id="textInput" placeholder="Paste document content here..."></textarea>
          </div>
          <div class="section-divider">or</div>
          <div class="form-group">
            <label>Server file/directory path</label>
            <input type="text" id="pathInput" placeholder="./docs or /path/to/file.txt">
          </div>
          <div class="form-group" style="margin-bottom:10px">
            <label>Ingest mode</label>
            <select id="ingestMode">
              <option value="full">Full — all enrichment (best quality)</option>
              <option value="fast">Fast — skip HyPE/preambles</option>
              <option value="minimal">Minimal — embed + BM25 only (fastest)</option>
            </select>
          </div>
          <button class="btn btn-primary" id="ingestBtn" onclick="doIngest()">Ingest Documents</button>
          <div class="progress-bar" id="progressBar"><div class="progress-fill" id="progressFill"></div></div>
          <div class="ingest-result" id="ingestResult"></div>
        </div>

        <!-- Settings Tab -->
        <div class="tab-content" id="tab-settings">
          <div class="form-group">
            <label>Top-K (retrieved chunks): <strong id="topKValue">7</strong></label>
            <input type="range" id="topKSlider" min="1" max="20" value="7"
                   style="width:100%" oninput="document.getElementById('topKValue').textContent=this.value">
          </div>
          <div class="form-group">
            <div class="toggle-label" onclick="toggleRerank()">
              <div class="toggle-switch on" id="rerankToggle"></div>
              <label style="cursor:pointer;margin-bottom:0">Reranking</label>
            </div>
            <p style="font-size:11px;color:var(--muted);margin-top:4px">FlashRank reranker for better precision</p>
          </div>
          <div class="form-group">
            <div class="toggle-label" onclick="toggleTrace()">
              <div class="toggle-switch on" id="traceToggle"></div>
              <label style="cursor:pointer;margin-bottom:0">Show Pipeline Trace</label>
            </div>
            <p style="font-size:11px;color:var(--muted);margin-top:4px">Display RAG pipeline steps and latency</p>
          </div>
          <div class="form-group">
            <div class="toggle-label" onclick="toggleStream()">
              <div class="toggle-switch" id="streamToggle"></div>
              <label style="cursor:pointer;margin-bottom:0">Streaming Mode</label>
            </div>
            <p style="font-size:11px;color:var(--muted);margin-top:4px">Stream tokens in real-time (disables trace)</p>
          </div>
        </div>

        <!-- Status Tab -->
        <div class="tab-content" id="tab-status">
          <div class="status-grid">
            <div class="stat-card"><div class="stat-label">Documents</div><div class="stat-value" id="statDocs">-</div></div>
            <div class="stat-card"><div class="stat-label">Chunks</div><div class="stat-value" id="statChunks">-</div></div>
            <div class="stat-card"><div class="stat-label">Embedding</div><div class="stat-value" id="statEmbed" style="font-size:12px">-</div></div>
            <div class="stat-card"><div class="stat-label">Language</div><div class="stat-value" id="statLang">-</div></div>
          </div>
          <div style="margin-top:14px"><button class="btn btn-secondary" onclick="loadStatus()">Refresh</button></div>
          <div style="margin-top:16px">
            <label>Documents</label>
            <div id="docList" style="margin-top:8px; font-size:13px; color:var(--muted)">Loading...</div>
          </div>
        </div>
      </div>
    </div>
    <div class="chat-area">
      <div class="chat-messages" id="chatMessages">
        <div class="empty-state" id="emptyState">
          <div class="icon">&#128269;</div>
          <h3>Ask anything about your documents</h3>
          <p>Ingest documents using the sidebar, then ask questions here.<br>
          Answers include source citations, confidence scores, and pipeline trace.</p>
          <div class="example-queries" id="exampleQueries">
            <div class="example-query" onclick="runExample(this)">What are the main topics in the documents?</div>
            <div class="example-query" onclick="runExample(this)">Summarize the key findings</div>
            <div class="example-query" onclick="runExample(this)">Compare the different approaches mentioned</div>
          </div>
        </div>
      </div>
      <div class="chat-input-area">
        <div class="query-options">
          <span style="color:var(--muted)">top_k: <strong id="topKDisplay">7</strong></span>
          <span style="color:var(--muted)">rerank: <strong id="rerankDisplay">on</strong></span>
          <span style="color:var(--muted)">mode: <strong id="modeDisplay">detailed</strong></span>
        </div>
        <div class="chat-input-row">
          <input type="text" id="queryInput" placeholder="Ask a question about your documents..."
                 onkeydown="if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing)doQuery()"
                 oncompositionend="if(event.data&&event.target===document.activeElement){}">
          <button class="btn btn-primary" style="width:auto; padding:10px 20px" id="queryBtn" onclick="doQuery()">Send</button>
        </div>
      </div>
    </div>
  </main>
</div>

<script>
const API = window.location.origin;

// ===================== Settings State =====================
let settings = { topK: 7, rerank: true, showTrace: true, streaming: false };

function toggleRerank() {
  settings.rerank = !settings.rerank;
  document.getElementById('rerankToggle').classList.toggle('on', settings.rerank);
  document.getElementById('rerankDisplay').textContent = settings.rerank ? 'on' : 'off';
}
function toggleTrace() {
  settings.showTrace = !settings.showTrace;
  document.getElementById('traceToggle').classList.toggle('on', settings.showTrace);
}
function toggleStream() {
  settings.streaming = !settings.streaming;
  document.getElementById('streamToggle').classList.toggle('on', settings.streaming);
  document.getElementById('modeDisplay').textContent = settings.streaming ? 'stream' : 'detailed';
}

// Sync top_k slider with display
const topKSlider = document.getElementById('topKSlider');
if (topKSlider) {
  topKSlider.addEventListener('input', () => {
    settings.topK = parseInt(topKSlider.value);
    document.getElementById('topKDisplay').textContent = settings.topK;
  });
}

// ===================== Markdown Renderer =====================
function renderMarkdown(text) {
  let md = text.replace(/\\r\\n/g, '\\n');

  // Extract fenced code blocks FIRST — handle ```lang\\n...``` and ```lang ...```
  // Also handle ``` with optional space before newline, or no newline at all
  const codeBlocks = [];
  md = md.replace(/```(\\w*)[^\\S\\n]*\\n([\\s\\S]*?)```/g, (_, lang, code) => {
    const placeholder = '%%CODEBLOCK_' + codeBlocks.length + '%%';
    const escaped = escHtml(code.trimEnd());
    const langLabel = lang ? `<span style="position:absolute;top:6px;right:10px;font-size:10px;color:var(--muted);text-transform:uppercase">${lang}</span>` : '';
    codeBlocks.push(`<pre style="position:relative">${langLabel}<code>${escaped}</code></pre>`);
    return placeholder;
  });
  // Also catch inline-style code blocks: `code here` that span single backtick lines
  // (already handled by renderInline)

  const blocks = [];
  let current = '';
  for (const line of md.split('\\n')) {
    if (line.trim() === '' && current.trim()) {
      blocks.push(current);
      current = '';
    } else {
      current += (current ? '\\n' : '') + line;
    }
  }
  if (current.trim()) blocks.push(current);

  let result = blocks.map(block => renderBlock(block.trim())).join('');

  // Restore code blocks from placeholders
  for (let i = 0; i < codeBlocks.length; i++) {
    result = result.replace('%%CODEBLOCK_' + i + '%%', codeBlocks[i]);
    // Also handle if placeholder got wrapped in <p> tags
    result = result.replace('<p>%%CODEBLOCK_' + i + '%%</p>', codeBlocks[i]);
  }

  return result;
}

function renderBlock(block) {
  // Code block placeholders pass through untouched
  if (block.startsWith('%%CODEBLOCK_')) return block;
  if (block.startsWith('<pre')) return block;
  const headingMatch = block.match(/^(#{1,4})\\s+(.+)$/m);
  if (headingMatch && block.split('\\n').length === 1) {
    const level = headingMatch[1].length;
    return `<h${level}>${renderInline(headingMatch[2])}</h${level}>`;
  }
  if (block.startsWith('>')) {
    const content = block.split('\\n').map(l => l.replace(/^>\\s?/, '')).join('\\n');
    return `<blockquote>${renderInline(content)}</blockquote>`;
  }
  if (/^[-*_]{3,}$/.test(block.trim())) return '<hr>';
  const lines = block.split('\\n');
  if (lines.length >= 2 && lines[0].includes('|') && /^[\\s|:-]+$/.test(lines[1])) {
    return renderTable(lines);
  }
  if (/^\\s*[-*+]\\s+/.test(lines[0])) {
    const items = [];
    let currentItem = '';
    for (const line of lines) {
      if (/^\\s*[-*+]\\s+/.test(line)) {
        if (currentItem) items.push(currentItem);
        currentItem = line.replace(/^\\s*[-*+]\\s+/, '');
      } else { currentItem += ' ' + line.trim(); }
    }
    if (currentItem) items.push(currentItem);
    return '<ul>' + items.map(i => `<li>${renderInline(i)}</li>`).join('') + '</ul>';
  }
  if (/^\\s*\\d+[.)\\s]/.test(lines[0])) {
    const items = [];
    let currentItem = '';
    for (const line of lines) {
      if (/^\\s*\\d+[.)\\s]/.test(line)) {
        if (currentItem) items.push(currentItem);
        currentItem = line.replace(/^\\s*\\d+[.)\\s]+/, '');
      } else { currentItem += ' ' + line.trim(); }
    }
    if (currentItem) items.push(currentItem);
    return '<ol>' + items.map(i => `<li>${renderInline(i)}</li>`).join('') + '</ol>';
  }
  const confMatch = block.match(/^(?:신뢰도|Confidence)[:\\s]*\\*{0,2}(STRONGLY_SUPPORTED|PARTIALLY_SUPPORTED|INSUFFICIENT_EVIDENCE)\\*{0,2}$/i);
  if (confMatch) {
    const level = confMatch[1].toUpperCase();
    const cls = level === 'STRONGLY_SUPPORTED' ? 'high' : level === 'PARTIALLY_SUPPORTED' ? 'medium' : 'low';
    return `<div class="confidence-line ${cls}">${level.replace(/_/g, ' ')}</div>`;
  }
  return `<p>${renderInline(block.replace(/\\n/g, '<br>'))}</p>`;
}

function renderInline(text) {
  let out = escHtml(text);
  out = out.replace(/&lt;br&gt;/g, '<br>');
  out = out.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
  out = out.replace(/(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)/g, '<em>$1</em>');
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  out = out.replace(/\\[(\\d+)\\]/g, '<span class="cite-ref">$1</span>');
  return out;
}

function renderTable(lines) {
  const headers = lines[0].split('|').map(c => c.trim()).filter(Boolean);
  const rows = lines.slice(2).filter(l => l.includes('|'));
  let html = '<table><thead><tr>';
  headers.forEach(h => { html += `<th>${renderInline(h)}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    const cells = row.split('|').map(c => c.trim()).filter(Boolean);
    html += '<tr>';
    cells.forEach(c => { html += `<td>${renderInline(c)}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table>';
  return html;
}

// ===================== Tabs =====================
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'status') loadStatus();
  });
});

// ===================== File Upload =====================
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const MAX_FILE_SIZE = 100 * 1024 * 1024;
let selectedFiles = [];

uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
uploadArea.addEventListener('drop', e => {
  e.preventDefault(); uploadArea.classList.remove('drag-over');
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function addFiles(fileListObj) {
  for (const f of fileListObj) {
    if (f.size > MAX_FILE_SIZE) { alert(f.name + ' exceeds 100 MB limit'); continue; }
    if (!selectedFiles.some(s => s.name === f.name && s.size === f.size)) selectedFiles.push(f);
  }
  renderFileList();
}
function removeFile(index) { selectedFiles.splice(index, 1); renderFileList(); }

function renderFileList() {
  const container = document.getElementById('fileList');
  if (selectedFiles.length === 0) {
    container.innerHTML = '';
    uploadArea.classList.remove('has-files');
    uploadArea.querySelector('p').innerHTML = 'Drop files here or click to browse<br><small>.txt .md .pdf .csv .html .hwp .hwpx (max 100MB)</small>';
    return;
  }
  uploadArea.classList.add('has-files');
  uploadArea.querySelector('p').innerHTML = '<strong>' + selectedFiles.length + ' file(s) selected</strong><br><small>Click to add more</small>';
  container.innerHTML = selectedFiles.map((f, i) =>
    '<div class="file-item" id="file-item-' + i + '">' +
      '<div class="file-info"><span class="file-name" title="' + escHtml(f.name) + '">' + escHtml(f.name) + '</span>' +
        '<span class="file-size">' + formatSize(f.size) + '</span></div>' +
      '<div style="display:flex;align-items:center;gap:6px">' +
        '<span class="file-status pending" id="file-status-' + i + '">Ready</span>' +
        '<button class="file-remove" onclick="removeFile(' + i + ')" title="Remove">&times;</button>' +
      '</div></div>'
  ).join('');
}

function setFileStatus(index, status, text) {
  const el = document.getElementById('file-status-' + index);
  if (!el) return;
  el.className = 'file-status ' + status;
  el.textContent = text;
  const removeBtn = el.parentElement.querySelector('.file-remove');
  if (removeBtn) removeBtn.style.display = (status === 'pending') ? '' : 'none';
}

// ===================== Ingest =====================
async function doIngest() {
  const btn = document.getElementById('ingestBtn');
  const result = document.getElementById('ingestResult');
  const progressBar = document.getElementById('progressBar');
  const progressFill = document.getElementById('progressFill');
  const textInput = document.getElementById('textInput').value.trim();
  const pathInput = document.getElementById('pathInput').value.trim();
  const ingestMode = document.getElementById('ingestMode').value;

  if (!textInput && selectedFiles.length === 0 && !pathInput) {
    result.className = 'ingest-result error';
    result.textContent = 'Please provide at least one input: upload files, paste text, or enter a path.';
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Ingesting...';
  result.className = 'ingest-result'; result.style.display = 'none';
  progressBar.classList.add('active');
  progressFill.className = 'progress-fill'; progressFill.style.width = '0%';

  const tasks = [];
  if (textInput) tasks.push({ type: 'text' });
  selectedFiles.forEach((f, i) => tasks.push({ type: 'file', file: f, index: i }));
  if (pathInput) tasks.push({ type: 'path' });
  const totalTasks = tasks.length;

  let completed = 0, totalDocs = 0, totalChunks = 0, errors = [], totalElapsed = 0;
  function updateProgress() {
    completed++;
    progressFill.style.width = Math.round((completed / totalTasks) * 100) + '%';
  }

  try {
    for (const task of tasks) {
      if (task.type === 'text') {
        try {
          const resp = await fetch(API + '/v1/ingest/text', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ content: textInput, title: 'Pasted Text', mode: ingestMode })
          });
          const data = await resp.json();
          if (resp.ok) {
            totalDocs += data.documents || 0; totalChunks += data.chunks || 0;
            totalElapsed += data.elapsed_seconds || 0;
            if (data.errors?.length > 0) errors.push(...data.errors.map(e => 'Text: ' + e));
          } else { errors.push('Text: ' + (data.detail || 'Unknown error')); }
        } catch (e) { errors.push('Text: ' + e.message); }
        updateProgress();
      }
      else if (task.type === 'file') {
        setFileStatus(task.index, 'uploading', 'Uploading...');
        try {
          const fd = new FormData(); fd.append('file', task.file); fd.append('mode', ingestMode);
          const resp = await fetch(API + '/v1/ingest/upload', { method: 'POST', body: fd });
          setFileStatus(task.index, 'processing', 'Processing...');
          const data = await resp.json();
          if (resp.ok) {
            totalDocs += data.documents || 0; totalChunks += data.chunks || 0;
            totalElapsed += data.elapsed_seconds || 0;
            if (data.errors?.length > 0) errors.push(...data.errors.map(e => task.file.name + ': ' + e));
            if ((data.chunks || 0) === 0) {
              setFileStatus(task.index, 'error', (data.errors?.[0]) || 'No text extracted');
            } else { setFileStatus(task.index, 'done', data.chunks + ' chunks'); }
          } else {
            errors.push(task.file.name + ': ' + (data.detail || 'Error'));
            setFileStatus(task.index, 'error', data.detail || 'Error');
          }
        } catch (e) { errors.push(task.file.name + ': ' + e.message); setFileStatus(task.index, 'error', 'Error'); }
        updateProgress();
      }
      else if (task.type === 'path') {
        try {
          const resp = await fetch(API + '/v1/ingest', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ path: pathInput, recursive: true, mode: ingestMode })
          });
          const data = await resp.json();
          if (resp.ok) {
            totalDocs += data.documents || 0; totalChunks += data.chunks || 0;
            totalElapsed += data.elapsed_seconds || 0;
            if (data.errors?.length > 0) errors.push(...data.errors.map(e => 'Path: ' + e));
          } else { errors.push('Path: ' + (data.detail || 'Unknown error')); }
        } catch (e) { errors.push('Path: ' + e.message); }
        updateProgress();
      }
    }

    if (errors.length === 0) {
      progressFill.classList.add('done');
      result.className = 'ingest-result success';
      result.innerHTML = '<strong>' + totalDocs + ' document(s)</strong>, <strong>' + totalChunks + ' chunks</strong> ingested in ' + totalElapsed.toFixed(1) + 's';
      document.getElementById('textInput').value = '';
      document.getElementById('pathInput').value = '';
      setTimeout(() => { selectedFiles = []; }, 0);
    } else if (errors.length < totalTasks) {
      progressFill.style.width = '100%';
      result.className = 'ingest-result error';
      result.innerHTML = 'Partial: ' + totalDocs + ' doc(s), ' + totalChunks + ' chunks.<br>' + errors.map(e => '&bull; ' + escHtml(e)).join('<br>');
    } else {
      progressFill.classList.add('error'); progressFill.style.width = '100%';
      result.className = 'ingest-result error';
      result.innerHTML = 'Failed:<br>' + errors.map(e => '&bull; ' + escHtml(e)).join('<br>');
    }
  } catch (e) {
    progressFill.classList.add('error'); progressFill.style.width = '100%';
    result.className = 'ingest-result error';
    result.textContent = 'Error: ' + e.message;
  }
  btn.disabled = false; btn.innerHTML = 'Ingest Documents'; loadStatus();
}

// ===================== Query =====================
let queryCounter = 0;
async function doQuery() {
  const input = document.getElementById('queryInput');
  const query = input.value.trim();
  if (!query) return;
  input.value = '';

  const emptyState = document.getElementById('emptyState');
  if (emptyState) emptyState.remove();

  const messages = document.getElementById('chatMessages');
  const qid = ++queryCounter;

  // User message
  const userDiv = document.createElement('div');
  userDiv.className = 'message message-user';
  userDiv.innerHTML = `<div class="message-header">You</div><div class="message-body">${escHtml(query)}</div>`;
  messages.appendChild(userDiv);

  // Assistant placeholder
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message message-assistant';
  msgDiv.id = 'msg-' + qid;
  msgDiv.innerHTML = `<div class="message-header"><span class="spinner"></span> Thinking...</div><div class="message-body"><div class="md-content" id="answer-${qid}"></div></div>`;
  messages.appendChild(msgDiv);
  messages.scrollTop = messages.scrollHeight;

  const btn = document.getElementById('queryBtn');
  btn.disabled = true;
  const answerEl = document.getElementById('answer-' + qid);

  try {
    if (settings.streaming) {
      await doStreamQuery(query, qid, msgDiv, answerEl, messages);
    } else {
      await doSyncQuery(query, qid, msgDiv, answerEl, messages);
    }
  } catch (e) {
    answerEl.textContent = 'Connection error: ' + e.message;
    msgDiv.querySelector('.message-header').innerHTML = 'QuantumRAG <span class="confidence low">error</span>';
  }

  btn.disabled = false;
  messages.scrollTop = messages.scrollHeight;
}

async function doSyncQuery(query, qid, msgDiv, answerEl, messages) {
  const resp = await fetch(API + '/v1/query', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      query,
      top_k: settings.topK,
      rerank: settings.rerank
    })
  });
  const data = await resp.json();

  if (!resp.ok) {
    answerEl.textContent = 'Error: ' + (data.detail || JSON.stringify(data));
    msgDiv.querySelector('.message-header').innerHTML = 'QuantumRAG <span class="confidence low">error</span>';
    return;
  }

  // Render answer
  answerEl.innerHTML = renderMarkdown(data.answer);

  // Confidence + latency
  const confClass = data.confidence === 'strongly_supported' ? 'high' : data.confidence === 'partially_supported' ? 'medium' : 'low';
  const latencyMs = data.metadata?.total_latency_ms;
  const pathLabel = data.metadata?.path;
  let headerHtml = `QuantumRAG <span class="confidence ${confClass}">${data.confidence.replace(/_/g, ' ')}</span>`;
  if (latencyMs) headerHtml += ` <span class="latency-badge">${(latencyMs/1000).toFixed(1)}s</span>`;
  if (pathLabel) headerHtml += ` <span class="latency-badge">${pathLabel}</span>`;
  msgDiv.querySelector('.message-header').innerHTML = headerHtml;

  // Sources
  if (data.sources?.length > 0) {
    const srcDiv = document.createElement('div');
    srcDiv.className = 'sources-section';
    let srcHtml = `<div class="sources-toggle" onclick="toggleSources(this)"><span class="arrow open">&#9654;</span> Sources (${data.sources.length})</div>`;
    srcHtml += '<div class="sources-body">';
    srcHtml += data.sources.map((s, idx) => {
      const title = escHtml(s.document_title || s.chunk_id.substring(0, 12));
      const section = s.section ? ' &mdash; ' + escHtml(s.section) : '';
      const page = s.page ? ' (p.' + s.page + ')' : '';
      const score = s.relevance_score || 0;
      const scoreCls = score > 0.7 ? 'high' : score > 0.4 ? 'mid' : 'low';
      const excerpt = escHtml((s.excerpt || '').substring(0, 500));
      return `<div class="source-card" onclick="this.classList.toggle('expanded')">
        <div class="source-header">
          <span class="source-title">[${idx + 1}] ${title}${section}${page}</span>
          <span class="source-score ${scoreCls}">${score.toFixed(3)}</span>
        </div>
        ${excerpt ? '<div class="source-excerpt">' + excerpt + '</div>' : ''}
      </div>`;
    }).join('');
    srcHtml += '</div>';
    srcDiv.innerHTML = srcHtml;
    msgDiv.querySelector('.message-body').appendChild(srcDiv);
  }

  // Pipeline trace
  if (settings.showTrace && data.trace?.length > 0) {
    const traceDiv = document.createElement('div');
    traceDiv.className = 'trace-section';
    traceDiv.innerHTML = renderTrace(data.trace, data.metadata);
    msgDiv.querySelector('.message-body').appendChild(traceDiv);
  }

  appendFeedback(msgDiv, query, data.answer);
}

async function doStreamQuery(query, qid, msgDiv, answerEl, messages) {
  const resp = await fetch(API + '/v1/query/stream', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ query, top_k: settings.topK })
  });

  if (resp.ok && resp.headers.get('content-type')?.includes('text/event-stream')) {
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', fullText = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') continue;
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) fullText += parsed.token;
          } catch { fullText += data; }
          answerEl.innerHTML = renderMarkdown(fullText);
          messages.scrollTop = messages.scrollHeight;
        }
      }
    }
    answerEl.innerHTML = renderMarkdown(fullText);
    msgDiv.querySelector('.message-header').innerHTML = 'QuantumRAG <span class="confidence medium">streamed</span>';
    appendFeedback(msgDiv, query, fullText);
  } else {
    // Fallback to sync
    await doSyncQuery(query, qid, msgDiv, answerEl, messages);
  }
}

// ===================== Trace Renderer =====================
function renderTrace(trace, metadata) {
  const totalMs = metadata?.total_latency_ms || trace.reduce((sum, t) => sum + t.latency_ms, 0);
  const stepNames = {
    rewrite: 'Query Rewrite', query_expansion: 'Query Expansion',
    classify: 'Complexity Classification', decompose: 'Query Decomposition',
    topic_augment: 'Topic Augment', pipeline_signal: 'Pipeline Signal',
    entity_injection: 'Entity Injection', fact_first_injection: 'Fact-First Injection',
    retrieve: 'Triple Index Retrieval', rerank: 'Reranking',
    generate: 'Answer Generation', map_reduce: 'Map-Reduce',
    fact_verify: 'Fact Verification', self_correct: 'Self-Correction',
    completeness_check: 'Completeness Check', retrieval_retry: 'Retrieval Retry',
    constellation_expansion: 'Constellation Expansion',
    post_correction: 'Post-Correction',
  };

  let html = `<div class="trace-toggle" onclick="toggleTraceBody(this)"><span class="arrow">&#9654;</span> Pipeline Trace (${trace.length} steps, ${(totalMs/1000).toFixed(2)}s)</div>`;
  html += '<div class="trace-body">';

  // Summary bar
  html += '<div class="trace-summary">';
  html += `<div class="trace-summary-item"><span class="label">Total</span><span class="value">${(totalMs/1000).toFixed(2)}s</span></div>`;
  if (metadata?.path) html += `<div class="trace-summary-item"><span class="label">Path</span><span class="value">${escHtml(metadata.path)}</span></div>`;
  const retrieveStep = trace.find(t => t.step === 'retrieve');
  if (retrieveStep?.details?.total_candidates) {
    html += `<div class="trace-summary-item"><span class="label">Candidates</span><span class="value">${retrieveStep.details.total_candidates}</span></div>`;
  }
  html += '</div>';

  // Steps
  html += '<div class="trace-pipeline">';
  for (const step of trace) {
    const name = stepNames[step.step] || step.step;
    const ms = step.latency_ms;
    const latCls = ms < 100 ? 'fast' : ms < 1000 ? 'normal' : 'slow';
    const latLabel = ms < 1000 ? ms.toFixed(0) + 'ms' : (ms / 1000).toFixed(2) + 's';

    html += `<div class="trace-step">`;
    html += `<div class="trace-step-header">`;
    html += `<span class="trace-step-name">${escHtml(name)}</span>`;
    html += `<span class="trace-step-latency ${latCls}">${latLabel}</span>`;
    html += `</div>`;

    if (step.result) {
      const truncated = step.result.length > 200 ? step.result.substring(0, 200) + '...' : step.result;
      html += `<div class="trace-step-result">${escHtml(truncated)}</div>`;
    }

    // Show key details
    const dets = step.details;
    if (dets && Object.keys(dets).length > 0) {
      const interesting = [];
      if (dets.complexity) interesting.push('complexity: ' + dets.complexity);
      if (dets.fusion_weights) interesting.push('weights: ' + JSON.stringify(dets.fusion_weights));
      if (dets.total_candidates != null) interesting.push('candidates: ' + dets.total_candidates);
      if (dets.reranked != null) interesting.push('reranked: ' + dets.reranked);
      if (dets.sub_queries) interesting.push('sub-queries: ' + JSON.stringify(dets.sub_queries));
      if (dets.entity) interesting.push('entity: ' + dets.entity);
      if (dets.verdict) interesting.push('verdict: ' + dets.verdict);
      if (dets.model) interesting.push('model: ' + dets.model);
      if (dets.tokens_used) interesting.push('tokens: ' + dets.tokens_used);
      if (interesting.length > 0) {
        html += `<div class="trace-step-details">${escHtml(interesting.join(' | '))}</div>`;
      }
    }
    html += `</div>`;
  }
  html += '</div></div>';
  return html;
}

function toggleTraceBody(el) {
  const arrow = el.querySelector('.arrow');
  const body = el.nextElementSibling;
  if (body.classList.contains('open')) {
    body.classList.remove('open');
    arrow.classList.remove('open');
  } else {
    body.classList.add('open');
    arrow.classList.add('open');
  }
}

function toggleSources(el) {
  const arrow = el.querySelector('.arrow');
  const body = el.nextElementSibling;
  arrow.classList.toggle('open');
  body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

// ===================== Feedback =====================
function appendFeedback(msgDiv, query, answer) {
  const fb = document.createElement('div');
  fb.className = 'feedback-row';
  const safeQ = query.replace(/'/g, "\\\\'").replace(/\\n/g, ' ').substring(0, 200);
  const safeA = answer.replace(/'/g, "\\\\'").replace(/\\n/g, ' ').substring(0, 200);
  fb.innerHTML = '<span style="font-size:11px;color:var(--muted);margin-right:6px">Rate:</span>' +
    [1,2,3,4,5].map(n => `<button class="feedback-btn" onclick="sendFeedback(this,${n},'${safeQ}','${safeA}')">${n}</button>`).join('');
  msgDiv.appendChild(fb);
}

async function sendFeedback(btn, rating, query, answer) {
  btn.parentElement.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  try {
    await fetch(API + '/v1/feedback', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ query, answer, rating, comment: '' })
    });
  } catch {}
}

// ===================== Status =====================
async function loadStatus() {
  try {
    const resp = await fetch(API + '/v1/status');
    const data = await resp.json();
    document.getElementById('statDocs').textContent = data.documents;
    document.getElementById('statChunks').textContent = data.chunks;
    document.getElementById('statEmbed').textContent = data.embedding_model || '-';
    document.getElementById('statLang').textContent = data.language || '-';
    document.getElementById('statusText').textContent = data.documents + ' docs / ' + data.chunks + ' chunks';
    document.getElementById('statusDot').className = 'status-dot';
  } catch {
    document.getElementById('statusText').textContent = 'Disconnected';
    document.getElementById('statusDot').className = 'status-dot error';
  }
  try {
    const resp = await fetch(API + '/v1/documents?limit=50');
    const data = await resp.json();
    const list = document.getElementById('docList');
    if (data.documents?.length > 0) {
      list.innerHTML = data.documents.map(d =>
        `<div class="doc-item">
          <div class="doc-item-info">
            <div class="doc-item-title" title="${escHtml(d.title || d.id)}">${escHtml(d.title || d.id.substring(0, 16))}</div>
            <div class="doc-item-meta">${d.chunk_count} chunks</div>
          </div>
          <button class="doc-item-delete" onclick="deleteDoc('${escHtml(d.id)}')" title="Delete document">&#128465;</button>
        </div>`
      ).join('');
    } else {
      list.innerHTML = '<span style="color:var(--muted)">No documents yet</span>';
    }
  } catch {}
}

// ===================== Document Management =====================
async function deleteDoc(docId) {
  if (!confirm('Delete this document and all its chunks?')) return;
  try {
    const resp = await fetch(API + '/v1/documents/' + encodeURIComponent(docId), { method: 'DELETE' });
    if (resp.ok) loadStatus();
    else alert('Delete failed: ' + (await resp.text()));
  } catch (e) { alert('Delete error: ' + e.message); }
}

// ===================== Chat Management =====================
function clearChat() {
  const messages = document.getElementById('chatMessages');
  messages.innerHTML = `<div class="empty-state" id="emptyState">
    <div class="icon">&#128269;</div>
    <h3>Ask anything about your documents</h3>
    <p>Ingest documents using the sidebar, then ask questions here.<br>
    Answers include source citations, confidence scores, and pipeline trace.</p>
    <div class="example-queries" id="exampleQueries">
      <div class="example-query" onclick="runExample(this)">What are the main topics in the documents?</div>
      <div class="example-query" onclick="runExample(this)">Summarize the key findings</div>
      <div class="example-query" onclick="runExample(this)">Compare the different approaches mentioned</div>
    </div>
  </div>`;
  queryCounter = 0;
}

function runExample(el) {
  document.getElementById('queryInput').value = el.textContent;
  doQuery();
}

// ===================== Helpers =====================
function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ===================== Init =====================
loadStatus();
</script>
</body>
</html>
"""


def mount_playground(app: FastAPI) -> None:
    """Mount the playground UI on the FastAPI app."""

    @app.get("/playground", response_class=HTMLResponse, include_in_schema=False)
    async def playground_page() -> str:
        return _PLAYGROUND_HTML

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root_redirect() -> str:
        return _PLAYGROUND_HTML
