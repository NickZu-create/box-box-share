/* Progressive enhancements shared by every page. Links and forms all work without this file. */
(() => {
  'use strict';
  const menus = '.lang-menu[open],.more-menu[open],.more-nav[open],.bubble-more[open]';
  document.addEventListener('click', event => {
    document.querySelectorAll(menus).forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
    const share = event.target.closest('[data-share-item]');
    if (share) { event.preventDefault(); openShare(share); }
    const orderState = event.target.closest('[data-order-state]');
    if (orderState) filterOrders(orderState);
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll(menus).forEach(menu => { menu.open = false; menu.querySelector('summary')?.focus(); });
  });

  // Sharing: copy, WhatsApp composer and the device's own share sheet. Nothing is sent by the site.
  function openShare(trigger) {
    const copy = document.getElementById('share-copy').dataset;
    const url = new URL(trigger.dataset.shareItem, location.origin).href;
    const title = trigger.dataset.shareTitle || document.title;
    document.getElementById('market-dialog')?.remove();
    const dialog = document.createElement('dialog');
    dialog.id = 'market-dialog'; dialog.className = 'market-dialog'; dialog.setAttribute('aria-labelledby', 'market-dialog-title');
    const make = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; };
    const heading = make('div', 'market-dialog-heading'), h2 = make('h2', '', copy.title); h2.id = 'market-dialog-title';
    const close = make('button', 'dialog-close', copy.close); close.type = 'button'; close.addEventListener('click', () => dialog.close());
    heading.append(h2, close);
    const field = make('input', 'share-url'); field.readOnly = true; field.value = url; field.setAttribute('aria-label', copy.title);
    const status = make('p', 'hint'); status.setAttribute('role', 'status');
    const actions = make('div', 'share-options');
    const whatsapp = make('a', 'button secondary', 'WhatsApp'); whatsapp.href = 'https://wa.me/?text=' + encodeURIComponent(title + '\n' + url); whatsapp.target = '_blank'; whatsapp.rel = 'noopener noreferrer';
    const device = make('button', 'button secondary', copy.device); device.type = 'button';
    device.addEventListener('click', async () => {
      if (!navigator.share) { status.textContent = copy.fallback; return; }
      try { await navigator.share({ title, url }); } catch (error) { if (error.name !== 'AbortError') status.textContent = copy.fallback; }
    });
    const copyLink = make('button', 'button secondary', copy.copy); copyLink.type = 'button';
    copyLink.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(url); status.textContent = copy.copied; } catch { field.focus(); field.select(); status.textContent = copy.manual; }
    });
    actions.append(whatsapp, device, copyLink);
    dialog.append(heading, make('p', '', copy.help), field, actions, status, make('p', 'hint', copy.note));
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('close', () => { dialog.remove(); trigger.focus({ preventScroll: true }); });
    document.body.append(dialog); dialog.showModal();
  }

  // Conversation search within the sidebar.
  document.addEventListener('input', event => {
    if (!event.target.matches('[data-thread-search]')) return;
    const query = event.target.value.trim().toLocaleLowerCase(); let count = 0;
    document.querySelectorAll('.thread-row').forEach(row => { row.hidden = !row.textContent.toLocaleLowerCase().includes(query); if (!row.hidden) count++; });
    const status = document.querySelector('.thread-search-status');
    if (status) { status.hidden = !query; status.textContent = count ? `${count}` : status.dataset.none; }
  });
  const revealManagement = () => {
    const tools = document.getElementById('inbox-tools');
    if (!tools || !location.hash) return;
    if (location.hash === '#inbox-tools' || tools.querySelector(location.hash)) { tools.open = true; document.querySelector(location.hash)?.scrollIntoView(); }
  };
  revealManagement(); window.addEventListener('hashchange', revealManagement);
  document.querySelector('.conversation-sidebar .thread-row.current')?.scrollIntoView({ block: 'nearest' });
  const chat = document.querySelector('.chat-body');
  if (chat) chat.scrollTop = chat.scrollHeight;

  function filterOrders(button) {
    let count = 0;
    document.querySelectorAll('[data-order-state]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    document.querySelectorAll('[data-order-status]').forEach(row => {
      row.hidden = button.dataset.orderState !== 'all' && row.dataset.orderStatus !== button.dataset.orderState;
      if (!row.hidden) count++;
    });
    const status = document.querySelector('.order-filter-status');
    if (status) status.hidden = count > 0;
  }

  // Sign-in code: six digits are enough, so there is nothing else to press.
  document.querySelector('[data-login-code] input[name=code]')?.addEventListener('input', event => {
    const digits = event.target.value.replace(/\D/g, '').slice(0, 6);
    event.target.value = digits;
    const form = event.target.form;
    if (digits.length === 6 && !form.dataset.sent) { form.dataset.sent = '1'; form.submit(); }
  });

  // Publishing: the same form covers lending and selling, or borrowing and buying.
  const form = document.querySelector('[data-market-publish]');
  if (form) {
    const update = () => {
      const intent = new FormData(form).get('intent') || form.dataset.intent;
      const oneOff = intent === 'sale' || intent === 'buy';
      const label = form.querySelector('[data-amount-label]');
      if (label) label.textContent = form.dataset['label' + intent[0].toUpperCase() + intent.slice(1)];
      const note = form.querySelector('[data-mode-note]');
      if (note) note.textContent = oneOff ? form.dataset.noteOneoff : form.dataset.noteDates;
      form.querySelectorAll('[data-rental-only]').forEach(node => { node.hidden = oneOff; node.querySelectorAll('input').forEach(field => { field.disabled = oneOff; }); });
      const description = form.elements.namedItem('description'), title = form.elements.namedItem('title'), preview = form.querySelector('[data-title-preview]');
      if (preview && description && title) {
        const generated = description.value.trim().split(/[\n。！？.!?]/)[0].trim().slice(0, 100);
        preview.textContent = generated && !title.value ? generated + ' · ' + form.dataset.generated : '';
      }
    };
    form.addEventListener('input', update); form.addEventListener('change', update); update();
    if (form.querySelector('.errorlist:not(:empty)')) form.querySelector('.publish-options')?.setAttribute('open', '');
    form.addEventListener('submit', () => {
      // Hidden date fields are switched off above, which is what a sale wants; a rental's defaults still post.
      form.querySelector('button[type=submit]')?.setAttribute('aria-busy', 'true');
    });
  }
})();
