"""A local dashboard on 127.0.0.1. Standard library only.

The outbox is the point: nothing leaves without you pressing approve.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db, model, pipeline, send

ROUTE_DRAFT = re.compile(r"^/api/drafts/(\d+)/(approve|skip|edit)$")


def state(cfg, con) -> dict:
    def rows(items):
        return [dict(row) for row in items]

    return {
        "product": cfg.path("product.name", ""),
        "model": model.describe(cfg),
        "delivery": send.mode(cfg),
        "counts": db.pipeline_counts(con),
        "drafts": rows(db.drafts(con, status="draft", limit=50)),
        "approved": rows(db.drafts(con, status="approved", limit=50)),
        "sent": rows(db.drafts(con, status="sent", limit=20)),
        "replies": rows(db.replies(con, limit=20)),
        "events": rows(db.recent_events(con, limit=25)),
        "prospects": rows(db.prospects(con, limit=200)),
    }


def page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>otto</title>
<style>
  :root { --bg:#0a0f0b; --panel:#101711; --line:#1f2d22; --fg:#cdf3d8;
          --dim:#5f7f68; --accent:#3dff86; --warn:#ffd166; }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
         font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; }
  h1 { font-size:15px; letter-spacing:.16em; text-transform:uppercase; margin:0 0 4px; }
  h1 b { color:var(--accent); }
  .sub { color:var(--dim); font-size:12px; margin-bottom:20px; }
  .bar { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px; }
  .stat { flex:1 1 120px; border:1px solid var(--line); background:var(--panel); padding:12px; }
  .stat span { display:block; color:var(--dim); font-size:10px; letter-spacing:.14em;
               text-transform:uppercase; }
  .stat strong { font-size:22px; font-weight:500; }
  button { font:inherit; background:transparent; color:var(--accent); cursor:pointer;
           border:1px solid var(--line); padding:6px 12px; }
  button:hover { border-color:var(--accent); }
  button.ghost { color:var(--dim); }
  section { margin:22px 0; }
  h2 { font-size:11px; letter-spacing:.16em; text-transform:uppercase;
       color:var(--dim); border-bottom:1px solid var(--line); padding-bottom:6px; }
  .card { border:1px solid var(--line); border-left:2px solid var(--accent);
          background:var(--panel); padding:14px 16px; margin:10px 0; }
  .card.reply { border-left-color:var(--warn); }
  .who { display:flex; justify-content:space-between; gap:12px; color:var(--dim);
         font-size:12px; margin-bottom:6px; }
  .subject { color:var(--accent); margin-bottom:8px; }
  pre { white-space:pre-wrap; margin:0 0 12px; font:inherit; color:var(--fg); }
  .empty { color:var(--dim); padding:10px 0; }
  .tag { border:1px solid var(--line); padding:0 6px; color:var(--dim); font-size:11px; }
  footer { color:var(--dim); font-size:11px; margin-top:28px; }
</style></head>
<body>
<h1>otto <b>&#9656;</b> outbox</h1>
<div class="sub" id="sub">loading</div>
<div class="bar" id="stats"></div>
<div class="bar">
  <button onclick="post('/api/cycle')">run one cycle</button>
  <button class="ghost" onclick="load()">refresh</button>
</div>
<section><h2>Outbox &mdash; waiting on you</h2><div id="outbox"></div></section>
<section><h2>Approved &mdash; next send pass</h2><div id="approved"></div></section>
<section><h2>Conversations</h2><div id="replies"></div></section>
<section><h2>Sent</h2><div id="sent"></div></section>
<section><h2>Log</h2><div id="log"></div></section>
<footer>Nothing sends without approval. Dry-run mode keeps everything local.</footer>
<script>
const esc = s => (s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function load() {
  const r = await fetch('/api/state');
  const d = await r.json();
  document.getElementById('sub').textContent =
    d.product + '  |  model: ' + d.model + '  |  delivery: ' + d.delivery;
  const c = d.counts;
  document.getElementById('stats').innerHTML = [
    ['prospects', d.prospects.length], ['unread replies', c.unhandled_replies],
    ['drafts', c.awaiting_approval], ['approved', c.approved], ['to profile', c.unprofiled]
  ].map(([k,v]) => `<div class="stat"><span>${k}</span><strong>${v}</strong></div>`).join('');

  const card = (x, actions) => `
    <div class="card ${x.kind === 'reply' ? 'reply' : ''}">
      <div class="who"><span>${esc(x.prospect_name)} &middot; ${esc(x.email || x.domain)}</span>
        <span>${esc(x.kind)} &middot; ${esc(x.created_at || '')}</span></div>
      <div class="subject">${esc(x.subject)}</div>
      <pre>${esc(x.body)}</pre>${actions || ''}</div>`;
  const btns = x => `<button onclick="post('/api/drafts/${x.id}/approve')">approve</button>
    <button class="ghost" onclick="post('/api/drafts/${x.id}/skip')">skip</button>`;

  document.getElementById('outbox').innerHTML =
    d.drafts.map(x => card(x, btns(x))).join('') || '<div class="empty">empty</div>';
  document.getElementById('approved').innerHTML =
    d.approved.map(x => card(x, '')).join('') || '<div class="empty">nothing queued</div>';
  document.getElementById('replies').innerHTML =
    d.replies.map(x => `<div class="card reply"><div class="who">
      <span>${esc(x.prospect_name || 'unknown')} &middot; ${esc(x.domain || '')}</span>
      <span class="tag">${esc(x.classification)}</span></div>
      <div class="subject">${esc(x.subject)}</div>
      <pre>${esc((x.body || '').slice(0, 500))}</pre></div>`).join('')
    || '<div class="empty">no replies yet</div>';
  document.getElementById('sent').innerHTML =
    d.sent.map(x => `<div class="card"><div class="who">
      <span>${esc(x.prospect_name)}</span><span>${esc(x.sent_at)} &middot; ${esc(x.delivery)}</span>
      </div><div class="subject">${esc(x.subject)}</div></div>`).join('')
    || '<div class="empty">nothing sent yet</div>';
  document.getElementById('log').innerHTML =
    d.events.map(e => `<div class="who"><span>${esc(e.kind)} ${esc(e.detail)}</span>
      <span>${esc(e.created_at)}</span></div>`).join('');
}
async function post(url) {
  await fetch(url, {method:'POST'});
  load();
}
load();
setInterval(load, 5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    """One fresh SQLite connection per request: threads and sqlite3 do not mix."""

    cfg = None

    def log_message(self, *args):  # keep the terminal clean
        return

    def _send(self, code, body, content_type="application/json"):
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, page(), "text/html; charset=utf-8")
        if self.path == "/api/state":
            con = db.connect(self.cfg.db_path)
            try:
                return self._send(200, json.dumps(state(self.cfg, con)))
            finally:
                con.close()
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        con = db.connect(self.cfg.db_path)
        try:
            if self.path == "/api/cycle":
                pipeline.cycle(self.cfg, con, out=lambda *a: None)
                return self._send(200, json.dumps({"ok": True}))
            match = ROUTE_DRAFT.match(self.path)
            if match:
                draft_id, action = int(match.group(1)), match.group(2)
                if action == "approve":
                    db.set_draft_status(con, draft_id, "approved")
                    draft = db.get_draft(con, draft_id)
                    if draft:
                        db.set_status(con, draft["prospect_id"], "approved")
                    db.log(con, "approved", None, str(draft_id))
                elif action == "skip":
                    db.set_draft_status(con, draft_id, "skipped")
                    db.log(con, "skipped", None, str(draft_id))
                return self._send(200, json.dumps({"ok": True}))
            self._send(404, json.dumps({"error": "not found"}))
        finally:
            con.close()


def serve(cfg, con=None, port=None, out=print):
    port = int(port or cfg.path("dashboard.port", 5555))
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    out(f"Otto dashboard: http://127.0.0.1:{port}  (local only, Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        out("\nstopped.")
    finally:
        httpd.server_close()
