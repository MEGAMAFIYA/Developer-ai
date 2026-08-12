"""GET /record/{slug} — the admin's in-browser game recorder page.

This is the fix for the core problem: Playwright/Chromium running
headless on the server cannot show its window on the admin's phone, so
the admin can never actually play the game to record it.

Instead, this page is opened as a Telegram Mini App directly on the
admin's own device. It iframes the real game (served from /games/{slug},
same origin), captures the game's <canvas> via captureStream(), and lets
the admin record their own gameplay with on-screen YOZISH/TO'XTATISH
buttons. The recorded WEBM is uploaded to /api/recording/upload, where
the bot picks it up and converts it to MP4 with ffmpeg (unchanged).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


def _safe_slug(slug: str) -> bool:
    return bool(slug) and all(c.isalnum() or c in "-_" for c in slug)


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Video yozish</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  html, body {{
    margin: 0; padding: 0; width: 100%; height: 100%;
    background: #0f1220; color: #fff; font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    overflow: hidden;
  }}
  #frameWrap {{
    position: absolute; top: 0; left: 0; right: 0; bottom: 84px;
    display: flex; align-items: center; justify-content: center;
    background: #000;
  }}
  iframe {{
    width: 100%; height: 100%; border: 0; background: #000;
  }}
  #bar {{
    position: absolute; left: 0; right: 0; bottom: 0; height: 84px;
    display: flex; align-items: center; justify-content: center; gap: 10px;
    background: #171a2b; box-shadow: 0 -2px 10px rgba(0,0,0,.4);
    padding: 0 12px; box-sizing: border-box;
  }}
  button {{
    flex: 1; max-width: 220px; height: 52px; border: 0; border-radius: 12px;
    font-size: 15px; font-weight: 600; color: #fff; cursor: pointer;
  }}
  #btnRecord {{ background: #e94560; }}
  #btnStop {{ background: #444a63; }}
  #btnStop:disabled, #btnRecord:disabled {{ opacity: .4; cursor: default; }}
  #status {{
    position: absolute; top: 8px; left: 8px; right: 8px;
    text-align: center; font-size: 13px; color: #ffd76b;
    background: rgba(0,0,0,.55); border-radius: 8px; padding: 6px 10px;
    z-index: 5; pointer-events: none;
  }}
  #dot {{
    display: none; position: absolute; top: 14px; right: 14px;
    width: 12px; height: 12px; border-radius: 50%; background: #ff3b30;
    animation: blink 1s infinite; z-index: 6;
  }}
  @keyframes blink {{ 50% {{ opacity: .2; }} }}
</style>
</head>
<body>
<div id="status">O'yin yuklanmoqda...</div>
<div id="dot"></div>
<div id="frameWrap">
  <iframe id="gameFrame" src="/games/{slug}"></iframe>
</div>
<div id="bar">
  <button id="btnRecord" disabled>🎥 YOZISH</button>
  <button id="btnStop" disabled>⏹ TO'XTATISH</button>
</div>
<script>
'use strict';

var tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
if (tg) {{ try {{ tg.ready(); tg.expand(); }} catch (e) {{}} }}

var TOKEN = {token!r};
var statusEl = document.getElementById('status');
var dotEl = document.getElementById('dot');
var btnRecord = document.getElementById('btnRecord');
var btnStop = document.getElementById('btnStop');
var frame = document.getElementById('gameFrame');

var stream = null;
var recorder = null;
var chunks = [];
var lastBlob = null;

function setStatus(text) {{ statusEl.textContent = text; }}

function findCanvas() {{
  try {{
    var doc = frame.contentDocument || frame.contentWindow.document;
    return doc.querySelector('canvas');
  }} catch (e) {{
    return null;
  }}
}}

function waitForCanvas(triesLeft) {{
  var canvas = findCanvas();
  if (canvas) {{
    setStatus('✅ Tayyor — 🎥 YOZISH tugmasini bosing');
    btnRecord.disabled = false;
    return;
  }}
  if (triesLeft <= 0) {{
    setStatus('⚠️ Canvas topilmadi. Ekranni yozishga urinib ko\\'riladi.');
    btnRecord.disabled = false;
    return;
  }}
  setTimeout(function () {{ waitForCanvas(triesLeft - 1); }}, 300);
}}

frame.addEventListener('load', function () {{
  waitForCanvas(20);
}});

function pickMimeType() {{
  var options = [
    'video/webm;codecs=vp9',
    'video/webm;codecs=vp8',
    'video/webm'
  ];
  for (var i = 0; i < options.length; i++) {{
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(options[i])) {{
      return options[i];
    }}
  }}
  return '';
}}

async function startRecording() {{
  btnRecord.disabled = true;
  setStatus('⏳ Tayyorlanmoqda...');

  var canvas = findCanvas();

  try {{
    if (canvas && canvas.captureStream) {{
      stream = canvas.captureStream(30);
    }} else if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {{
      stream = await navigator.mediaDevices.getDisplayMedia({{ video: true, audio: false }});
    }} else {{
      throw new Error('Bu qurilmada video yozish qo\\'llab-quvvatlanmaydi.');
    }}

    var mimeType = pickMimeType();
    recorder = mimeType ? new MediaRecorder(stream, {{ mimeType: mimeType }}) : new MediaRecorder(stream);
    chunks = [];

    recorder.ondataavailable = function (e) {{
      if (e.data && e.data.size > 0) chunks.push(e.data);
    }};

    recorder.onstop = onRecorderStop;

    recorder.start(1000);

    dotEl.style.display = 'block';
    setStatus('🔴 Yozilmoqda — o\\'ynang, tugatgach TO\\'XTATISHni bosing');
    btnStop.disabled = false;
  }} catch (err) {{
    setStatus('❌ Xato: ' + (err && err.message ? err.message : err));
    btnRecord.disabled = false;
  }}
}}

function stopRecording() {{
  btnStop.disabled = true;
  if (recorder && recorder.state !== 'inactive') {{
    recorder.stop();
  }}
  if (stream) {{
    stream.getTracks().forEach(function (t) {{ t.stop(); }});
  }}
  dotEl.style.display = 'none';
}}

async function onRecorderStop() {{
  setStatus('⏳ Video yuborilmoqda...');
  lastBlob = new Blob(chunks, {{ type: 'video/webm' }});
  await uploadBlob(lastBlob);
}}

async function uploadBlob(blob) {{
  try {{
    var res = await fetch('/api/recording/upload?token=' + encodeURIComponent(TOKEN), {{
      method: 'POST',
      headers: {{ 'Content-Type': 'video/webm' }},
      body: blob
    }});

    if (!res.ok) {{
      var body = await res.json().catch(function () {{ return {{}}; }});
      throw new Error(body.detail || ('HTTP ' + res.status));
    }}

    setStatus('✅ Yuborildi! Botga qayting.');
    setTimeout(function () {{
      if (tg) {{ try {{ tg.close(); }} catch (e) {{}} }}
    }}, 1200);
  }} catch (err) {{
    setStatus('❌ Yuborishda xato: ' + (err && err.message ? err.message : err) + ' — qayta urinib ko\\'ring');
    btnRecord.disabled = false;
    btnRecord.textContent = '🔁 QAYTA YUBORISH';
    btnRecord.onclick = function () {{ uploadBlob(lastBlob); }};
  }}
}}

btnRecord.addEventListener('click', startRecording);
btnStop.addEventListener('click', stopRecording);
</script>
</body>
</html>"""


@router.get("/record/{slug}")
async def serve_recorder(slug: str, token: str = "") -> HTMLResponse:
    if not _safe_slug(slug) or not token:
        return HTMLResponse(
            "<h3>Noto'g'ri so'rov</h3>",
            status_code=400,
        )

    html = _PAGE_TEMPLATE.format(slug=slug, token=token)

    return HTMLResponse(html)
