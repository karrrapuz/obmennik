'use strict';
(() => {
  const el = id => document.getElementById(id);
  const storageKey = 'giftmoney-admin-session-v1';
  const validToken = value => typeof value === 'string' && value.length > 0 && value.length <= 4096 && /^[!-~]+$/.test(value);
  let token = '', offset = 0, nextOffset = null, controller;
  const columns = {
    users: ['user_id', 'revision'],
    loans: ['id', 'user_id', 'gift_id', 'status', 'principal_nano', 'repayment_nano', 'created_at', 'due_at', 'autopay'],
    trades: ['id', 'user_id', 'status', 'expires_at'],
    accounts: ['user_id', 'kind', 'balance_nano'],
    ledger: ['id', 'user_id', 'kind', 'amount_nano', 'created_at_ns', 'postings'],
  };
  function status(message, error = false) { el('status').textContent = message; el('status').dataset.error = String(error); }
  function disconnect(clearStored = true) {
    controller?.abort(); controller = null; token = ''; el('token').value = '';
    if (clearStored) { try { sessionStorage.removeItem(storageKey); } catch { /* Storage may be disabled. */ } }
    el('workspace').hidden = true; el('login').hidden = false;
    for (const id of ['identity', 'overview', 'columns', 'records', 'page']) el(id).replaceChildren();
    status('Disconnected');
  }
  function cell(tag, text) { const node = document.createElement(tag); node.textContent = String(text ?? '-'); return node; }
  function busy(value) {
    for (const id of ['resource', 'limit', 'refresh']) el(id).disabled = value;
    el('previous').disabled = value || offset === 0;
    el('next').disabled = value || nextOffset === null;
  }
  async function refresh() {
    if (!token) return;
    controller?.abort(); const active = new AbortController(); controller = active;
    const timer = setTimeout(() => active.abort(), 20000);
    const resource = el('resource').value, limit = Number(el('limit').value);
    busy(true); status('Loading...'); el('records').replaceChildren();
    try {
      const request = async path => {
        const response = await fetch(path, { headers: { Authorization: `Bearer ${token}` }, signal: active.signal, cache: 'no-store', credentials: 'omit', redirect: 'error' });
        if (!response.ok) { const error = new Error('Request failed'); error.status = response.status; throw error; }
        return response.json();
      };
      const [overview, data] = await Promise.all([request('/api/admin/overview'), request(`/api/admin/${resource}?limit=${limit}&offset=${offset}`)]);
      if (controller !== active) return;
      try { sessionStorage.setItem(storageKey, token); } catch { /* An in-memory session still works. */ }
      el('identity').textContent = `Admin ${overview.admin_user_id}`;
      const stats = [...Object.entries(overview.counts), ...Object.entries(overview.account_balances_nano).map(([kind, value]) => [`${kind} balance (nano_DEMO_TON)`, value])];
      el('overview').replaceChildren(...stats.map(([key, value]) => { const row = document.createElement('div'); row.append(cell('dt', key.replaceAll('_', ' ')), cell('dd', value)); return row; }));
      const header = document.createElement('tr'); header.append(...columns[resource].map(key => { const node = cell('th', key); node.scope = 'col'; return node; }));
      el('columns').replaceChildren(header);
      el('records').replaceChildren(...data.items.map(item => {
        const row = document.createElement('tr'); row.append(...columns[resource].map(key => cell('td', key === 'postings' ? item.postings.map(posting => `${posting.account_kind}: ${posting.amount_nano}`).join('; ') : item[key]))); return row;
      }));
      nextOffset = data.next_offset;
      el('page').textContent = data.items.length ? `${offset + 1}-${offset + data.items.length}` : 'No records';
      if (data.has_more && nextOffset === null) el('page').textContent += ' (browse limit reached)';
      el('workspace').hidden = false; el('login').hidden = true;
      status('Connected - read-only DEMO_TON');
    } catch (error) {
      if (controller !== active) return;
      if (error.status === 401 || error.status === 403) { disconnect(); status(error.status === 401 ? 'Session expired or invalid' : 'Admin access denied', true); }
      else { disconnect(); status('Unable to load admin data', true); }
    } finally { clearTimeout(timer); if (controller === active) busy(false); }
  }
  el('login').addEventListener('submit', event => {
    event.preventDefault(); token = el('token').value.trim(); el('token').value = '';
    if (!validToken(token)) { disconnect(); status('Invalid bearer token', true); return; }
    offset = 0; nextOffset = null; void refresh();
  });
  el('disconnect').addEventListener('click', () => disconnect());
  el('refresh').addEventListener('click', () => { void refresh(); });
  for (const id of ['resource', 'limit']) el(id).addEventListener('change', () => { offset = 0; nextOffset = null; void refresh(); });
  el('previous').addEventListener('click', () => { offset = Math.max(0, offset - Number(el('limit').value)); void refresh(); });
  el('next').addEventListener('click', () => { if (nextOffset !== null) { offset = nextOffset; void refresh(); } });
  window.addEventListener('pagehide', () => disconnect(false));
  function resume() {
    if (token) return;
    try { token = sessionStorage.getItem(storageKey) || ''; } catch { token = ''; }
    if (token && validToken(token)) { offset = 0; nextOffset = null; void refresh(); }
    else if (token) disconnect();
  }
  window.addEventListener('pageshow', resume);
  resume();
})();
