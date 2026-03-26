"""Web playground — browser-based UI for testing QuantumRAG.

Serves a single-page app at ``/playground`` that lets users:
- Upload or paste text documents for ingest
- Query the knowledge base with live streaming
- View sources, confidence, and engine status
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
    --blue: #3b82f6; --cyan: #06b6d4;
    --radius: 10px; --font: 'Inter', -apple-system, sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: var(--font); background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }

  /* Layout */
  .app { display: flex; flex-direction: column; height: 100vh; }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--surface);
  }
  header h1 { font-size: 18px; font-weight: 600; }
  header h1 span { color: var(--primary); }
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
  .sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); }
  .sidebar-body { flex: 1; overflow-y: auto; padding: 16px; }

  /* Tabs */
  .tabs { display: flex; gap: 4px; }
  .tab {
    flex: 1; padding: 8px; font-size: 13px; font-weight: 500; text-align: center;
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
  textarea { min-height: 120px; }
  .form-group { margin-bottom: 16px; }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 10px 16px; font-size: 14px; font-weight: 500; border: none;
    border-radius: 6px; cursor: pointer; transition: all 0.15s; width: 100%;
    font-family: var(--font);
  }
  .btn-primary { background: var(--primary); color: white; }
  .btn-primary:hover { background: var(--primary-hover); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { background: var(--border); }

  /* File upload */
  .upload-area {
    border: 2px dashed var(--border); border-radius: var(--radius);
    padding: 24px; text-align: center; cursor: pointer;
    transition: all 0.15s; margin-bottom: 8px;
  }
  .upload-area:hover, .upload-area.drag-over { border-color: var(--primary); background: rgba(99,102,241,0.05); }
  .upload-area p { font-size: 13px; color: var(--muted); margin-top: 8px; }
  .upload-area .icon { font-size: 28px; }
  .upload-area.has-files { border-color: var(--primary); border-style: solid; background: rgba(99,102,241,0.04); }
  .file-input { display: none; }

  /* File list */
  .file-list { margin-bottom: 12px; }
  .file-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 12px; margin-bottom: 4px; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 6px; font-size: 13px;
  }
  .file-item .file-info { display: flex; align-items: center; gap: 8px; overflow: hidden; }
  .file-item .file-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px; }
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
    margin-top: 10px; padding: 10px 14px; border-radius: 8px;
    font-size: 13px; display: none;
  }
  .ingest-result.success { display: block; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2); color: var(--green); }
  .ingest-result.error { display: block; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); color: var(--red); }

  /* Section divider */
  .section-divider {
    display: flex; align-items: center; gap: 10px; margin: 14px 0 10px;
    font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;
  }
  .section-divider::before, .section-divider::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
  }

  /* Chat area */
  .chat-area { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 24px; min-height: 0; }
  .chat-input-area { flex-shrink: 0; padding: 16px 24px; border-top: 1px solid var(--border); background: var(--surface); }
  .chat-input-row { display: flex; gap: 8px; }
  .chat-input-row input { flex: 1; }

  /* Messages */
  .message { margin-bottom: 24px; max-width: 820px; }
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
  .md-content li {
    margin-bottom: 6px; line-height: 1.6;
  }
  .md-content li::marker { color: var(--primary); }

  .md-content blockquote {
    border-left: 3px solid var(--primary);
    padding: 10px 16px; margin: 12px 0;
    background: rgba(99,102,241,0.06); border-radius: 0 6px 6px 0;
    color: var(--muted); font-style: italic;
  }

  .md-content hr {
    border: none; border-top: 1px solid var(--border);
    margin: 16px 0;
  }

  .md-content table {
    width: 100%; border-collapse: collapse; margin: 12px 0;
    font-size: 13px;
  }
  .md-content th {
    background: var(--surface); padding: 8px 12px; text-align: left;
    border-bottom: 2px solid var(--border); font-weight: 600; color: #f1f5f9;
  }
  .md-content td {
    padding: 8px 12px; border-bottom: 1px solid var(--border);
  }
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
  .sources-label { font-size: 11px; color: var(--muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 8px; }
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
    font-size: 11px; font-weight: 700; padding: 2px 8px;
    border-radius: 10px;
  }
  .source-card .source-score.high { background: rgba(34,197,94,0.12); color: var(--green); }
  .source-card .source-score.mid { background: rgba(234,179,8,0.12); color: var(--yellow); }
  .source-card .source-score.low { background: rgba(239,68,68,0.12); color: var(--red); }
  .source-card .source-excerpt { color: var(--muted); line-height: 1.5; margin-top: 4px; }

  /* Confidence badge (header) */
  .confidence {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
  }
  .confidence.high { background: rgba(34,197,94,0.15); color: var(--green); }
  .confidence.medium { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .confidence.low { background: rgba(239,68,68,0.15); color: var(--red); }

  /* Feedback */
  .feedback-row { display: flex; align-items: center; gap: 4px; margin-top: 10px; }
  .feedback-btn {
    width: 30px; height: 30px; display: flex; align-items: center; justify-content: center;
    font-size: 13px; background: var(--surface); border: 1px solid var(--border);
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
  .stat-card .stat-value { font-size: 20px; font-weight: 700; margin-top: 4px; }

  /* Log */
  .log-area {
    margin-top: 12px; padding: 10px; background: var(--bg);
    border-radius: 6px; font-size: 12px; font-family: var(--mono);
    color: var(--muted); max-height: 200px; overflow-y: auto;
    white-space: pre-wrap;
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

  /* Empty state */
  .empty-state { text-align: center; padding: 60px 24px; color: var(--muted); }
  .empty-state .icon { font-size: 48px; margin-bottom: 16px; }
  .empty-state h3 { font-size: 16px; color: var(--text); margin-bottom: 8px; }
  .empty-state p { font-size: 13px; line-height: 1.6; }

  @media (max-width: 768px) {
    main { flex-direction: column; }
    .sidebar { width: 100%; min-width: unset; border-right: none; border-bottom: 1px solid var(--border); max-height: 50vh; }
  }
</style>
</head>
<body>
<div class="app">
  <header>
    <h1><span>Quantum</span>RAG Playground</h1>
    <div class="status-badge" id="statusBadge">
      <div class="status-dot" id="statusDot"></div>
      <span id="statusText">Connecting...</span>
    </div>
  </header>
  <main>
    <div class="sidebar">
      <div class="sidebar-header">
        <div class="tabs">
          <div class="tab active" data-tab="ingest">Ingest</div>
          <div class="tab" data-tab="status">Status</div>
        </div>
      </div>
      <div class="sidebar-body">
        <div class="tab-content active" id="tab-ingest">
          <div class="form-group">
            <label>Upload Files</label>
            <div class="upload-area" id="uploadArea">
              <div class="icon">&#128195;</div>
              <p>Drop files here or click to browse<br><small>.txt .md .pdf .csv .json .html .hwp .hwpx (max 100MB)</small></p>
            </div>
            <input type="file" class="file-input" id="fileInput" multiple
                   accept=".txt,.md,.pdf,.csv,.json,.html,.hwp,.hwpx">
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

          <button class="btn btn-primary" id="ingestBtn" onclick="doIngest()">Ingest Documents</button>
          <div class="progress-bar" id="progressBar"><div class="progress-fill" id="progressFill"></div></div>
          <div class="ingest-result" id="ingestResult"></div>
        </div>
        <div class="tab-content" id="tab-status">
          <div class="status-grid">
            <div class="stat-card"><div class="stat-label">Documents</div><div class="stat-value" id="statDocs">-</div></div>
            <div class="stat-card"><div class="stat-label">Chunks</div><div class="stat-value" id="statChunks">-</div></div>
            <div class="stat-card"><div class="stat-label">Embedding</div><div class="stat-value" id="statEmbed" style="font-size:13px">-</div></div>
            <div class="stat-card"><div class="stat-label">Language</div><div class="stat-value" id="statLang">-</div></div>
          </div>
          <div style="margin-top:16px"><button class="btn btn-secondary" onclick="loadStatus()">Refresh Status</button></div>
          <div style="margin-top:20px">
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
          Answers include source citations and confidence scores.</p>
        </div>
      </div>
      <div class="chat-input-area">
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

// ===================== Markdown Renderer =====================
function renderMarkdown(text) {
  // Normalize line endings
  let md = text.replace(/\\r\\n/g, '\\n');

  // Fenced code blocks
  md = md.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, (_, lang, code) => {
    const escaped = escHtml(code.trimEnd());
    const langLabel = lang ? `<span style="position:absolute;top:6px;right:10px;font-size:10px;color:var(--muted);text-transform:uppercase">${lang}</span>` : '';
    return `<pre style="position:relative">${langLabel}<code>${escaped}</code></pre>`;
  });

  // Split into blocks by double newline (but not inside pre)
  const blocks = [];
  let current = '';
  let inPre = false;
  for (const line of md.split('\\n')) {
    if (line.includes('<pre')) inPre = true;
    if (line.includes('</pre>')) inPre = false;
    if (!inPre && line.trim() === '' && current.trim()) {
      blocks.push(current);
      current = '';
    } else {
      current += (current ? '\\n' : '') + line;
    }
  }
  if (current.trim()) blocks.push(current);

  return blocks.map(block => renderBlock(block.trim())).join('');
}

function renderBlock(block) {
  // Already HTML (pre blocks)
  if (block.startsWith('<pre')) return block;

  // Headings
  const headingMatch = block.match(/^(#{1,4})\\s+(.+)$/m);
  if (headingMatch && block.split('\\n').length === 1) {
    const level = headingMatch[1].length;
    return `<h${level}>${renderInline(headingMatch[2])}</h${level}>`;
  }

  // Blockquote
  if (block.startsWith('>')) {
    const content = block.split('\\n').map(l => l.replace(/^>\\s?/, '')).join('\\n');
    return `<blockquote>${renderInline(content)}</blockquote>`;
  }

  // Horizontal rule
  if (/^[-*_]{3,}$/.test(block.trim())) return '<hr>';

  // Table
  const lines = block.split('\\n');
  if (lines.length >= 2 && lines[0].includes('|') && /^[\\s|:-]+$/.test(lines[1])) {
    return renderTable(lines);
  }

  // Unordered list
  if (/^\\s*[-*+]\\s+/.test(lines[0])) {
    const items = [];
    let currentItem = '';
    for (const line of lines) {
      if (/^\\s*[-*+]\\s+/.test(line)) {
        if (currentItem) items.push(currentItem);
        currentItem = line.replace(/^\\s*[-*+]\\s+/, '');
      } else {
        currentItem += ' ' + line.trim();
      }
    }
    if (currentItem) items.push(currentItem);
    return '<ul>' + items.map(i => `<li>${renderInline(i)}</li>`).join('') + '</ul>';
  }

  // Ordered list
  if (/^\\s*\\d+[.)\\s]/.test(lines[0])) {
    const items = [];
    let currentItem = '';
    for (const line of lines) {
      if (/^\\s*\\d+[.)\\s]/.test(line)) {
        if (currentItem) items.push(currentItem);
        currentItem = line.replace(/^\\s*\\d+[.)\\s]+/, '');
      } else {
        currentItem += ' ' + line.trim();
      }
    }
    if (currentItem) items.push(currentItem);
    return '<ol>' + items.map(i => `<li>${renderInline(i)}</li>`).join('') + '</ol>';
  }

  // Confidence line detection
  const confMatch = block.match(/^(?:신뢰도|Confidence)[:\\s]*\\*{0,2}(STRONGLY_SUPPORTED|PARTIALLY_SUPPORTED|INSUFFICIENT_EVIDENCE)\\*{0,2}$/i);
  if (confMatch) {
    const level = confMatch[1].toUpperCase();
    const cls = level === 'STRONGLY_SUPPORTED' ? 'high' : level === 'PARTIALLY_SUPPORTED' ? 'medium' : 'low';
    const label = level.replace(/_/g, ' ');
    return `<div class="confidence-line ${cls}">${label}</div>`;
  }

  // Regular paragraph
  const rendered = renderInline(block.replace(/\\n/g, '<br>'));
  return `<p>${rendered}</p>`;
}

function renderInline(text) {
  let out = escHtml(text);

  // Restore <br> tags
  out = out.replace(/&lt;br&gt;/g, '<br>');

  // Bold: **text**
  out = out.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');

  // Italic: *text*
  out = out.replace(/(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)/g, '<em>$1</em>');

  // Inline code: `text`
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Citation references: [1], [2][3], [4][6][7]
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
const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100 MB
let selectedFiles = []; // managed list (allows individual removal)

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
    if (f.size > MAX_FILE_SIZE) {
      alert(f.name + ' exceeds 100 MB limit (' + formatSize(f.size) + ')');
      continue;
    }
    // avoid duplicates by name+size
    if (!selectedFiles.some(s => s.name === f.name && s.size === f.size)) {
      selectedFiles.push(f);
    }
  }
  renderFileList();
}

function removeFile(index) {
  selectedFiles.splice(index, 1);
  renderFileList();
}

function renderFileList() {
  const container = document.getElementById('fileList');
  if (selectedFiles.length === 0) {
    container.innerHTML = '';
    uploadArea.classList.remove('has-files');
    uploadArea.querySelector('p').innerHTML = 'Drop files here or click to browse<br><small>.txt .md .pdf .csv .json .html .hwp .hwpx (max 100MB)</small>';
    return;
  }
  uploadArea.classList.add('has-files');
  uploadArea.querySelector('p').innerHTML = '<strong>' + selectedFiles.length + ' file(s) selected</strong><br><small>Click to add more</small>';
  container.innerHTML = selectedFiles.map((f, i) =>
    '<div class="file-item" id="file-item-' + i + '">' +
      '<div class="file-info">' +
        '<span class="file-name" title="' + escHtml(f.name) + '">' + escHtml(f.name) + '</span>' +
        '<span class="file-size">' + formatSize(f.size) + '</span>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:6px">' +
        '<span class="file-status pending" id="file-status-' + i + '">Ready</span>' +
        '<button class="file-remove" onclick="removeFile(' + i + ')" title="Remove">&times;</button>' +
      '</div>' +
    '</div>'
  ).join('');
}

function setFileStatus(index, status, text) {
  const el = document.getElementById('file-status-' + index);
  if (!el) return;
  el.className = 'file-status ' + status;
  el.textContent = text;
  // hide remove button when processing
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

  // Count total tasks
  const tasks = [];
  if (textInput) tasks.push({ type: 'text' });
  selectedFiles.forEach((f, i) => tasks.push({ type: 'file', file: f, index: i }));
  if (pathInput) tasks.push({ type: 'path' });
  const totalTasks = tasks.length;

  let completed = 0;
  let totalDocs = 0, totalChunks = 0;
  let errors = [];
  let totalElapsed = 0;

  function updateProgress() {
    completed++;
    const pct = Math.round((completed / totalTasks) * 100);
    progressFill.style.width = pct + '%';
  }

  try {
    for (const task of tasks) {
      if (task.type === 'text') {
        try {
          const resp = await fetch(API + '/v1/ingest/text', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ content: textInput, title: 'Pasted Text' })
          });
          const data = await resp.json();
          if (resp.ok) {
            totalDocs += data.documents || 0; totalChunks += data.chunks || 0;
            totalElapsed += data.elapsed_seconds || 0;
            if (data.errors && data.errors.length > 0) errors.push(...data.errors.map(e => 'Text: ' + e));
          } else { errors.push('Text: ' + (data.detail || 'Unknown error')); }
        } catch (e) { errors.push('Text: ' + e.message); }
        updateProgress();
      }
      else if (task.type === 'file') {
        setFileStatus(task.index, 'uploading', 'Uploading...');
        try {
          const fd = new FormData(); fd.append('file', task.file);
          const resp = await fetch(API + '/v1/ingest/upload', { method: 'POST', body: fd });
          setFileStatus(task.index, 'processing', 'Processing...');
          const data = await resp.json();
          if (resp.ok) {
            totalDocs += data.documents || 0; totalChunks += data.chunks || 0;
            totalElapsed += data.elapsed_seconds || 0;
            // Collect server-side parse errors
            if (data.errors && data.errors.length > 0) {
              errors.push(...data.errors.map(e => task.file.name + ': ' + e));
            }
            if ((data.chunks || 0) === 0) {
              const reason = (data.errors && data.errors.length > 0) ? data.errors[0] : 'No text extracted';
              setFileStatus(task.index, 'error', reason);
            } else {
              setFileStatus(task.index, 'done', data.chunks + ' chunks');
            }
          } else {
            errors.push(task.file.name + ': ' + (data.detail || 'Unknown error'));
            setFileStatus(task.index, 'error', data.detail || 'Error');
          }
        } catch (e) {
          errors.push(task.file.name + ': ' + e.message);
          setFileStatus(task.index, 'error', 'Error');
        }
        updateProgress();
      }
      else if (task.type === 'path') {
        try {
          const resp = await fetch(API + '/v1/ingest', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ path: pathInput, recursive: true })
          });
          const data = await resp.json();
          if (resp.ok) {
            totalDocs += data.documents || 0; totalChunks += data.chunks || 0;
            totalElapsed += data.elapsed_seconds || 0;
            if (data.errors && data.errors.length > 0) errors.push(...data.errors.map(e => 'Path: ' + e));
          } else { errors.push('Path: ' + (data.detail || 'Unknown error')); }
        } catch (e) { errors.push('Path: ' + e.message); }
        updateProgress();
      }
    }

    // Show result
    if (errors.length === 0) {
      progressFill.classList.add('done');
      result.className = 'ingest-result success';
      result.innerHTML = '<strong>' + totalDocs + ' document(s)</strong>, <strong>' + totalChunks + ' chunks</strong> ingested in ' + totalElapsed.toFixed(1) + 's';
      // Clear inputs on full success
      document.getElementById('textInput').value = '';
      document.getElementById('pathInput').value = '';
      // Keep file list visible with green statuses, clear selectedFiles for next round
      setTimeout(() => { selectedFiles = []; }, 0);
    } else if (errors.length < totalTasks) {
      progressFill.style.width = '100%';
      result.className = 'ingest-result error';
      result.innerHTML = 'Partial success: ' + totalDocs + ' doc(s), ' + totalChunks + ' chunks.<br>Errors:<br>' + errors.map(e => '&bull; ' + escHtml(e)).join('<br>');
    } else {
      progressFill.classList.add('error'); progressFill.style.width = '100%';
      result.className = 'ingest-result error';
      result.innerHTML = 'All tasks failed:<br>' + errors.map(e => '&bull; ' + escHtml(e)).join('<br>');
    }
  } catch (e) {
    progressFill.classList.add('error'); progressFill.style.width = '100%';
    result.className = 'ingest-result error';
    result.textContent = 'Unexpected error: ' + e.message;
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
    // Try streaming
    const resp = await fetch(API + '/v1/query/stream', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ query })
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
            } catch {
              fullText += data;
            }
            answerEl.innerHTML = renderMarkdown(fullText);
            messages.scrollTop = messages.scrollHeight;
          }
        }
      }
      // Final render
      answerEl.innerHTML = renderMarkdown(fullText);
      msgDiv.querySelector('.message-header').innerHTML = 'QuantumRAG <span class="confidence medium">streamed</span>';
      appendFeedback(msgDiv, query, fullText);
    } else {
      // Sync fallback
      const syncResp = await fetch(API + '/v1/query', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ query })
      });
      const data = await syncResp.json();

      if (syncResp.ok) {
        // Render markdown answer
        answerEl.innerHTML = renderMarkdown(data.answer);

        // Confidence badge
        const confClass = data.confidence === 'strongly_supported' ? 'high' : data.confidence === 'partially_supported' ? 'medium' : 'low';
        msgDiv.querySelector('.message-header').innerHTML = `QuantumRAG <span class="confidence ${confClass}">${data.confidence.replace(/_/g, ' ')}</span>`;

        // Sources
        if (data.sources && data.sources.length > 0) {
          const srcDiv = document.createElement('div');
          srcDiv.className = 'sources-section';
          srcDiv.innerHTML = '<div class="sources-label">Sources</div>' +
            data.sources.map(s => {
              const title = escHtml(s.document_title || s.chunk_id.substring(0, 12));
              const section = s.section ? ' &mdash; ' + escHtml(s.section) : '';
              const page = s.page ? ' (p.' + s.page + ')' : '';
              const score = s.relevance_score || 0;
              const scoreCls = score > 0.7 ? 'high' : score > 0.4 ? 'mid' : 'low';
              const excerpt = escHtml((s.excerpt || '').substring(0, 200));
              return `<div class="source-card">
                <div class="source-header">
                  <span class="source-title">${title}${section}${page}</span>
                  <span class="source-score ${scoreCls}">${score.toFixed(3)}</span>
                </div>
                ${excerpt ? '<div class="source-excerpt">' + excerpt + '</div>' : ''}
              </div>`;
            }).join('');
          msgDiv.querySelector('.message-body').appendChild(srcDiv);
        }

        appendFeedback(msgDiv, query, data.answer);
      } else {
        answerEl.textContent = 'Error: ' + (data.detail || JSON.stringify(data));
        msgDiv.querySelector('.message-header').innerHTML = 'QuantumRAG <span class="confidence low">error</span>';
      }
    }
  } catch (e) {
    answerEl.textContent = 'Connection error: ' + e.message;
    msgDiv.querySelector('.message-header').innerHTML = 'QuantumRAG <span class="confidence low">error</span>';
  }

  btn.disabled = false;
  messages.scrollTop = messages.scrollHeight;
}

function appendFeedback(msgDiv, query, answer) {
  const fb = document.createElement('div');
  fb.className = 'feedback-row';
  const safeQ = query.replace(/'/g, "\\\\'").replace(/\\n/g, ' ').substring(0, 200);
  const safeA = answer.replace(/'/g, "\\\\'").replace(/\\n/g, ' ').substring(0, 200);
  fb.innerHTML = '<span style="font-size:11px;color:var(--muted);margin-right:6px">Rate:</span>' +
    [1,2,3,4,5].map(n => `<button class="feedback-btn" onclick="sendFeedback(this,${n},'${safeQ}','${safeA}')">${n}</button>`).join('');
  msgDiv.appendChild(fb);
}

// ===================== Feedback =====================
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
        '<div style="padding:6px 0;border-bottom:1px solid var(--border)">' +
        '<strong>' + escHtml(d.title || d.id.substring(0,12)) + '</strong>' +
        ' <span style="color:var(--muted)">' + d.chunk_count + ' chunks</span></div>'
      ).join('');
    } else {
      list.innerHTML = '<span style="color:var(--muted)">No documents yet</span>';
    }
  } catch {}
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
