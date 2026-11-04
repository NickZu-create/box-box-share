// Unread badges, in-page pop-ups, borrow-request prompts and live chat, by short polling.
// Nothing here is needed for links or forms to work.
(() => {
  'use strict';
  const copy = document.getElementById('notify-copy');
  if (!copy) return;
  const config = copy.dataset;
  const CHAT_EVERY = 5000, PAGE_EVERY = 20000, MAX_WAIT = 120000, IDLE_AFTER = 15 * 60 * 1000, SHOW_FOR = 6000, MAX_TOASTS = 3;
  const KEY = 'bbs-notify:' + config.uid, SNOOZED = 'bbs-request-later:' + config.uid, CHATTED = 'bbs-request-chat:' + config.uid;
  const live = document.querySelector('[data-live-url]');
  const feed = document.querySelector('[data-inbox-feed]');
  let timer = null, failures = 0, signature = null, lastActive = Date.now(), busy = false, finished = false, memory = null;

  function get(area, key, fallback) {
    try { return JSON.parse(area.getItem(key)) || fallback; } catch (err) { return fallback; }
  }
  function put(area, key, value) {
    try { area.setItem(key, JSON.stringify(value)); } catch (err) { /* private window: this page still works */ }
  }
  function readCursors() { return get(localStorage, KEY, memory); }
  function saveCursors(cursors) { memory = cursors; put(localStorage, KEY, cursors); }
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ---- Badges
  function paintCount(node, count) {
    node.textContent = count > 99 ? '99+' : String(count);
    node.hidden = !count;
    if (node.matches('[data-unread-badge]')) node.setAttribute('aria-label', config.unreadLabel.replace('{n}', count));
  }
  function paintCounts(unread) {
    document.querySelectorAll('[data-unread-badge]').forEach(node => paintCount(node, unread.total));
    document.querySelectorAll('[data-tab-count]').forEach(node => paintCount(node, unread[node.dataset.tabCount] || 0));
  }

  // ---- Pop-ups
  function stack() {
    let node = document.getElementById('notify-stack');
    if (!node) {
      node = element('div', 'notify-stack');
      node.id = 'notify-stack';
      node.setAttribute('role', 'status'); node.setAttribute('aria-live', 'polite');
      document.body.appendChild(node);
    }
    return node;
  }
  function toast(alert) {
    const holder = stack();
    if (holder.querySelector(`[data-key="${alert.key}"]`)) return;
    const box = element('div', 'notify-toast notify-' + alert.kind);
    box.dataset.key = alert.key;
    const link = element('a', 'notify-toast-link');
    link.href = alert.url;
    link.append(element('span', 'notify-toast-mark', Array.from(alert.title)[0] || ''));
    const words = element('span', 'notify-toast-words');
    words.append(element('strong', '', alert.title), element('span', '', alert.text));
    link.append(words);
    const close = element('button', 'notify-toast-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', config.closeLabel);
    box.append(link, close);
    let hide = null;
    const dismiss = () => { clearTimeout(hide); box.remove(); };
    const wait = () => { clearTimeout(hide); hide = setTimeout(dismiss, SHOW_FOR); };
    close.addEventListener('click', dismiss);
    ['pointerenter', 'focusin'].forEach(name => box.addEventListener(name, () => clearTimeout(hide)));
    ['pointerleave', 'focusout'].forEach(name => box.addEventListener(name, wait));
    holder.prepend(box);
    while (holder.children.length > MAX_TOASTS) holder.lastElementChild.remove();
    wait();
  }

  // ---- Borrow requests, for the owner
  function busyTyping() {
    const active = document.activeElement;
    if (active && active.matches('input,textarea,select,[contenteditable=true]')) return true;
    return Array.from(document.querySelectorAll('main form textarea')).some(field => field.value.trim());
  }
  function postAction(url, action) {
    const form = element('form');
    form.method = 'post'; form.action = url; form.hidden = true;
    const token = element('input'); token.type = 'hidden'; token.name = 'csrfmiddlewaretoken';
    token.value = document.querySelector('input[name=csrfmiddlewaretoken]').value;
    const field = element('input'); field.type = 'hidden'; field.name = 'action'; field.value = action;
    form.append(token, field);
    document.body.appendChild(form);
    form.submit();
  }
  function detail(list, label, value) {
    if (!value) return;
    list.append(element('dt', '', label), element('dd', '', value));
  }
  function showRequest(request, position, total, rest) {
    const dialog = element('dialog', 'request-dialog');
    dialog.id = 'request-dialog';
    dialog.setAttribute('aria-labelledby', 'request-dialog-title');
    const panel = element('div', 'request-panel');
    const head = element('div', 'request-head');
    head.append(element('span', 'pill', config.requestEyebrow));
    if (total > 1) head.append(element('span', 'request-count', `${position} / ${total}`));
    panel.append(head);
    const title = element('h2', '', request.title);
    title.id = 'request-dialog-title';
    if (request.photo) {
      const picture = element('img', 'request-photo');
      picture.src = request.photo; picture.alt = '';
      panel.append(picture);
    }
    panel.append(title);
    const applicant = element('a', 'request-applicant', config.requestFrom.replace('{name}', request.applicant));
    applicant.href = request.applicant_url;
    panel.append(applicant);
    if (request.applicant_detail) panel.append(element('p', 'request-who', request.applicant_detail));
    const list = element('dl', 'request-details');
    detail(list, config.requestDates, `${request.start} – ${request.end}`);
    detail(list, config.requestLocation, request.location);
    detail(list, config.requestRent, 'HK$ ' + request.rent);
    detail(list, config.requestDeposit, 'HK$ ' + request.deposit);
    detail(list, config.requestTotal, 'HK$ ' + request.total);
    panel.append(list);
    const actions = element('div', 'request-actions');
    const accept = element('button', 'button', config.requestAccept); accept.type = 'button';
    const reject = element('button', 'button secondary', config.requestReject); reject.type = 'button';
    accept.addEventListener('click', () => { accept.disabled = reject.disabled = true; postAction(request.order_url, 'accept'); });
    reject.addEventListener('click', () => {
      actions.replaceChildren();
      const sure = element('p', 'request-sure', config.requestRejectSure);
      const yes = element('button', 'button danger', config.requestRejectConfirm); yes.type = 'button';
      const back = element('button', 'button secondary', config.requestBack); back.type = 'button';
      yes.addEventListener('click', () => { yes.disabled = back.disabled = true; postAction(request.order_url, 'decline'); });
      back.addEventListener('click', () => { actions.replaceChildren(accept, reject); accept.focus(); });
      actions.append(sure, yes, back);
      back.focus();
    });
    actions.append(accept, reject);
    panel.append(actions);
    const links = element('div', 'request-links');
    const chat = element('a', 'text-link', config.requestChat); chat.href = request.chat_url;
    chat.addEventListener('click', () => put(localStorage, CHATTED, [...get(localStorage, CHATTED, []), request.id].slice(-50)));
    const later = element('button', 'text-button', config.requestLater); later.type = 'button';
    links.append(chat, later);
    panel.append(links);
    dialog.append(panel);
    const putOff = () => {
      put(sessionStorage, SNOOZED, [...get(sessionStorage, SNOOZED, []), request.id]);
      dialog.close(); dialog.remove();
      if (rest.length) showRequest(rest[0], position + 1, total, rest.slice(1));
    };
    later.addEventListener('click', putOff);
    dialog.addEventListener('cancel', event => { event.preventDefault(); putOff(); });
    document.body.appendChild(dialog);
    dialog.showModal();
    accept.focus();
  }
  function promptRequests(requests) {
    if (document.querySelector('dialog[open]')) return;
    const snoozed = get(sessionStorage, SNOOZED, []), chatted = get(localStorage, CHATTED, []);
    const waiting = requests.filter(request => !snoozed.includes(request.id) && !chatted.includes(request.id) && location.pathname !== request.order_url && !(live && String(request.person) === live.dataset.person));
    if (!waiting.length) return;
    if (busyTyping()) {
      waiting.slice(0, 1).forEach(request => toast({ key: 'r' + request.id, kind: 'request', title: config.requestEyebrow, text: config.requestFrom.replace('{name}', request.applicant) + ' · ' + request.title, url: request.order_url }));
      return;
    }
    showRequest(waiting[0], 1, waiting.length, waiting.slice(1));
  }

  // ---- Live pages
  function refreshChat() {
    if (!live) return Promise.resolve();
    const url = live.dataset.liveUrl + '?after=' + encodeURIComponent(live.dataset.lastId || 0);
    return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(response => { if (!response.ok) throw new Error('chat'); return response.json(); })
      .then(data => {
        paintCounts(data.unread);
        Object.entries(data.recalled || {}).forEach(([id, html]) => { const line = document.getElementById('line-' + id); if (line) line.outerHTML = html; });
        document.dispatchEvent(new CustomEvent('bbs:messages-added'));
        if (!data.html) return;
        const scroller = live.closest('.chat-body') || live;
        const atEnd = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
        live.querySelector('[data-chat-empty]')?.remove();
        live.insertAdjacentHTML('beforeend', data.html);
        live.dataset.lastId = data.last;
        document.dispatchEvent(new CustomEvent('bbs:messages-added'));
        if (atEnd) scroller.scrollTop = scroller.scrollHeight;
      })
      .catch(() => {});
  }
  function refreshFeed() {
    if (!feed || !feed.offsetParent) return;
    const params = new URLSearchParams({ tab: feed.dataset.tab, current: feed.dataset.current || '', group: feed.dataset.currentGroup || '' });
    fetch(config.feedUrl + '?' + params, { credentials: 'same-origin' })
      .then(response => { if (!response.ok) throw new Error('feed'); return response.text(); })
      .then(html => {
        const scroll = feed.scrollTop;
        feed.innerHTML = html;
        feed.scrollTop = scroll;
        document.dispatchEvent(new CustomEvent('bbs:messages-added'));
        document.querySelector('[data-thread-search]')?.dispatchEvent(new Event('input', { bubbles: true }));
      })
      .catch(() => {});
  }

  // ---- The loop: only while someone is looking at this tab.
  const asleep = () => document.hidden || Date.now() - lastActive > IDLE_AFTER;
  function schedule(delay) {
    clearTimeout(timer); timer = null;
    if (finished || asleep()) return;
    const every = live ? CHAT_EVERY : PAGE_EVERY;
    timer = setTimeout(tick, delay === undefined ? Math.min(every * 2 ** failures, MAX_WAIT) : delay);
  }
  function tick() {
    timer = null;
    if (busy || finished || asleep()) return;
    busy = true;
    const cursors = readCursors();
    const query = cursors ? '?' + new URLSearchParams(cursors) : '';
    fetch(config.pollUrl + query, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(response => {
        if (response.status === 401) { finished = true; return null; }
        if (!response.ok) throw new Error('poll');
        return response.json();
      })
      .then(data => {
        failures = 0;
        if (!data) return null;
        saveCursors(data.cursors);
        paintCounts(data.unread);
        data.alerts.filter(alert => alert.url !== location.pathname && !(live && alert.person && String(alert.person) === live.dataset.person)).reverse().forEach(toast);
        promptRequests(data.requests);
        const changed = signature !== data.signature;
        signature = data.signature;
        if (!changed) return null;
        refreshFeed();
        return refreshChat();
      })
      .catch(() => { failures = Math.min(failures + 1, 5); })
      .then(() => { busy = false; schedule(); });
  }
  const wake = () => {
    const wasAsleep = timer === null && !busy;
    lastActive = Date.now();
    if (wasAsleep) schedule(0);
  };
  ['pointerdown', 'keydown', 'scroll'].forEach(name => addEventListener(name, wake, { passive: true }));
  document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(timer); timer = null; } else wake(); });
  schedule(1200);
})();
