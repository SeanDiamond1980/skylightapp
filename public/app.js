// ── Tab navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const tab = link.dataset.tab;
    document.querySelectorAll('.nav-item').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    link.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
    if (tab === 'history') loadHistory();
    if (tab === 'setup') loadSetup();
  });
});

// ── Toast ─────────────────────────────────────────────────────────────────────

function toast(msg, duration = 3000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.classList.remove('show');
    el.classList.add('hidden');
  }, duration);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit'
    });
  } catch { return iso; }
}

function fmtRelative(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function badgeHtml(status) {
  return `<span class="event-badge badge-${status}">${status}</span>`;
}

function eventRowHtml(ev) {
  const title = ev.parsed_title || ev.email_subject || 'Untitled';
  const detail = ev.parsed_start ? fmtDate(ev.parsed_start) : 'Date unknown';
  const loc = ev.parsed_location ? ` · ${ev.parsed_location}` : '';
  const link = ev.calendar_event_link
    ? `<a class="event-link" href="${ev.calendar_event_link}" target="_blank">Open in Calendar →</a>` : '';
  const err = ev.error ? `<div class="event-detail" style="color:#ef4444">${ev.error}</div>` : '';
  return `
    <div class="event-row">
      ${badgeHtml(ev.status)}
      <div class="event-meta">
        <div class="event-title">${escHtml(title)}</div>
        <div class="event-detail">${escHtml(detail + loc)}</div>
        ${err}
        ${link}
      </div>
      <div class="event-time">${fmtRelative(ev.created_at)}</div>
    </div>`;
}

function escHtml(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Status ────────────────────────────────────────────────────────────────────

let appStatus = null;

async function loadStatus() {
  try {
    const res = await fetch('/api/status');
    appStatus = await res.json();
    renderStatus();
    renderSetupCard();
  } catch (e) {
    document.getElementById('status-label').textContent = 'Server offline';
    document.getElementById('status-dot').className = 'status-dot error';
  }
}

function renderStatus() {
  const { googleAuthed, anthropicConfigured } = appStatus;
  const dot = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  if (googleAuthed && anthropicConfigured) {
    dot.className = 'status-dot ok';
    label.textContent = 'Ready';
  } else {
    dot.className = 'status-dot warn';
    label.textContent = 'Setup needed';
  }

  // Webhook URL
  document.getElementById('webhook-url').textContent =
    `${window.location.origin}/webhook/email`;
}

function renderSetupCard() {
  const { googleAuthed, anthropicConfigured, gmailPolling } = appStatus;
  const all = googleAuthed && anthropicConfigured;
  const card = document.getElementById('setup-card');
  card.style.display = all ? 'none' : 'block';

  const items = [
    { ok: anthropicConfigured, label: 'ANTHROPIC_API_KEY set in .env' },
    { ok: googleAuthed, label: 'Google Calendar connected', action: '<a href="/auth/google" class="btn btn-google" style="padding:6px 14px;font-size:12px;">Connect Google</a>' },
    { ok: gmailPolling, label: 'Gmail auto-polling configured (optional)' }
  ];

  document.getElementById('checklist').innerHTML = items.map(i => `
    <div class="check-item">
      <span class="check-icon">${i.ok ? '✅' : '⬜'}</span>
      <span>${i.label}</span>
      ${!i.ok && i.action ? i.action : ''}
    </div>`).join('');
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function loadDashboard() {
  try {
    const events = await fetch('/api/events').then(r => r.json());
    const total = events.length;
    const added = events.filter(e => e.status === 'added').length;
    const errors = events.filter(e => e.status === 'error').length;

    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-added').textContent = added;
    document.getElementById('stat-errors').textContent = errors;

    const recent = events.slice(0, 5);
    const container = document.getElementById('recent-events');
    container.innerHTML = recent.length
      ? recent.map(eventRowHtml).join('')
      : '<div class="empty">No events yet. Go to <strong>Add Event</strong> to get started.</div>';
  } catch (e) {
    console.error(e);
  }
}

// ── History ───────────────────────────────────────────────────────────────────

async function loadHistory() {
  const container = document.getElementById('history-list');
  container.innerHTML = '<div class="loading-pulse">Loading...</div>';
  try {
    const events = await fetch('/api/events').then(r => r.json());
    container.innerHTML = events.length
      ? events.map(eventRowHtml).join('')
      : '<div class="empty">No events yet.</div>';
  } catch (e) {
    container.innerHTML = '<div class="empty" style="color:#ef4444">Failed to load events.</div>';
  }
}

// ── Add Event Form ────────────────────────────────────────────────────────────

document.getElementById('add-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const subject = document.getElementById('f-subject').value.trim();
  const from = document.getElementById('f-from').value.trim();
  const body = document.getElementById('f-body').value.trim();

  if (!body && !subject) {
    toast('Please enter at least an email body or subject.');
    return;
  }

  const btn = document.getElementById('add-btn');
  const btnText = document.getElementById('add-btn-text');
  const spinner = document.getElementById('add-spinner');

  btn.disabled = true;
  btnText.textContent = 'Processing…';
  spinner.classList.remove('hidden');

  const resultCard = document.getElementById('result-card');
  const resultContent = document.getElementById('result-content');
  resultCard.classList.add('hidden');

  try {
    const res = await fetch('/api/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject, from, body })
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || 'Unknown error');

    const ev = data.event;
    resultContent.innerHTML = `
      <div class="result-success">
        <div class="result-title">✅ Added to Calendar!</div>
        <div class="result-rows">
          <div class="result-row"><span class="result-key">Event</span><span class="result-val">${escHtml(ev.title)}</span></div>
          <div class="result-row"><span class="result-key">Date/Time</span><span class="result-val">${fmtDate(ev.start)}${ev.end ? ' → ' + fmtDate(ev.end) : ''}</span></div>
          ${ev.location ? `<div class="result-row"><span class="result-key">Location</span><span class="result-val">${escHtml(ev.location)}</span></div>` : ''}
          ${ev.description ? `<div class="result-row"><span class="result-key">Details</span><span class="result-val">${escHtml(ev.description)}</span></div>` : ''}
          ${ev.organizer ? `<div class="result-row"><span class="result-key">Organizer</span><span class="result-val">${escHtml(ev.organizer)}</span></div>` : ''}
          ${data.calEvent?.link ? `<div class="result-row"><span class="result-key">Calendar</span><span class="result-val"><a class="result-link" href="${data.calEvent.link}" target="_blank">Open event →</a></span></div>` : ''}
          ${ev.notes ? `<div class="result-row"><span class="result-key">Notes</span><span class="result-val" style="color:#92400e">${escHtml(ev.notes)}</span></div>` : ''}
        </div>
      </div>`;

    // Clear form
    document.getElementById('f-subject').value = '';
    document.getElementById('f-from').value = '';
    document.getElementById('f-body').value = '';

    loadDashboard();
  } catch (err) {
    resultContent.innerHTML = `
      <div class="result-error">
        <div class="result-title">❌ Failed</div>
        <p style="margin-top:6px;font-size:13px;">${escHtml(err.message)}</p>
      </div>`;
  }

  resultCard.classList.remove('hidden');
  btn.disabled = false;
  btnText.textContent = '✨ Parse & Add to Calendar';
  spinner.classList.add('hidden');
});

// ── Setup ─────────────────────────────────────────────────────────────────────

async function loadSetup() {
  if (!appStatus) await loadStatus();
  await renderAccountsList();
  renderGmailSection();
}

async function renderAccountsList() {
  const container = document.getElementById('accounts-list');
  const accounts = appStatus?.connectedAccounts || [];

  if (accounts.length === 0) {
    container.innerHTML = '<p class="hint">No accounts connected yet.</p>';
    return;
  }

  container.innerHTML = accounts.map(a => `
    <div class="account-row" style="display:flex;align-items:center;gap:12px;padding:10px 12px;background:var(--bg);border-radius:8px;border:1px solid var(--border);margin-bottom:8px;">
      <span style="font-size:20px">✅</span>
      <span style="flex:1;font-weight:500">${escHtml(a.email)}</span>
      <button class="btn btn-secondary" style="padding:5px 12px;font-size:12px" onclick="disconnectAccount('${escHtml(a.email)}')">Disconnect</button>
    </div>
  `).join('');
}

async function disconnectAccount(email) {
  if (!confirm(`Disconnect ${email}?`)) return;
  await fetch(`/api/accounts/${encodeURIComponent(email)}`, { method: 'DELETE' });
  await loadStatus();
  await renderAccountsList();
  toast(`${email} disconnected`);
}

function renderGmailSection() {
  const el = document.getElementById('gmail-poll-status');
  if (appStatus?.gmailPolling) {
    el.innerHTML = `✅ Gmail polling is active — checking every <strong>${appStatus.pollInterval} min</strong> for emails in the <strong>${escHtml(process?.env?.GMAIL_LABEL || 'Skylight Events')}</strong> label.`;
  } else {
    el.innerHTML = 'Gmail polling is not configured. Add the variables below to your <code>.env</code> file and restart the server.';
  }
}

document.getElementById('poll-now-btn').addEventListener('click', async () => {
  try {
    await fetch('/api/poll', { method: 'POST' });
    toast('Gmail poll triggered!');
  } catch { toast('Poll failed — check your Gmail credentials.'); }
});

// ── URL params (auth result) ──────────────────────────────────────────────────

const params = new URLSearchParams(window.location.search);
if (params.get('auth') === 'success') {
  toast('✅ Google Calendar connected!');
  history.replaceState({}, '', '/');
  // Switch to setup tab
  document.querySelector('[data-tab="setup"]').click();
} else if (params.get('auth') === 'error') {
  toast('❌ Google auth failed: ' + (params.get('reason') || 'unknown'));
  history.replaceState({}, '', '/');
}

// ── Code block copy ───────────────────────────────────────────────────────────

document.addEventListener('click', e => {
  if (e.target.classList.contains('code-block')) {
    navigator.clipboard?.writeText(e.target.textContent.trim())
      .then(() => toast('Copied!'))
      .catch(() => {});
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

(async () => {
  await loadStatus();
  await loadDashboard();
})();
