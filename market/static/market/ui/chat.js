// The chat box: growing text, Enter to send, quoting, photos, and recall buttons that disappear on time.
(() => {
  'use strict';
  const form = document.querySelector('[data-chat-form]');
  if (form) {
    const input = form.elements.namedItem('text');
    const file = form.elements.namedItem('image');
    const replyField = form.elements.namedItem('reply_to');
    const replyBar = form.querySelector('[data-reply-bar]');
    const photoBar = form.querySelector('[data-photo-bar]');
    const hasContent = () => input.value.trim() || file.files.length;
    const fit = () => { input.style.height = 'auto'; input.style.height = input.scrollHeight + 'px'; };
    input.addEventListener('input', fit);
    input.addEventListener('keydown', event => {
      if (event.key !== 'Enter' || event.shiftKey || event.isComposing || !matchMedia('(pointer:fine)').matches) return;
      event.preventDefault();
      if (hasContent()) form.requestSubmit(form.querySelector('button[data-send]'));
    });
    form.addEventListener('submit', event => {
      if (!hasContent() || form.dataset.sending) { event.preventDefault(); return; }
      form.dataset.sending = '1';
    });
    file.addEventListener('change', () => {
      const chosen = file.files[0];
      photoBar.hidden = !chosen;
      if (!chosen) return;
      const reader = new FileReader();
      reader.onload = () => { photoBar.querySelector('img').src = reader.result; };
      reader.readAsDataURL(chosen);
    });
    photoBar.querySelector('button').addEventListener('click', () => { file.value = ''; photoBar.hidden = true; input.focus(); });
    replyBar.querySelector('button').addEventListener('click', () => { replyField.value = ''; replyBar.hidden = true; input.focus(); });
    document.addEventListener('click', event => {
      const quote = event.target.closest('[data-reply]');
      if (!quote) return;
      replyField.value = quote.dataset.reply;
      replyBar.querySelector('strong').textContent = quote.dataset.replyName;
      replyBar.querySelector('span').textContent = quote.dataset.replyText;
      replyBar.hidden = false;
      quote.closest('details').open = false;
      input.focus();
    });
  }

  // "Delete from this device": remembered only in this browser, for this account. The server is never told.
  const copy = document.getElementById('notify-copy');
  if (copy) {
    const KEY = 'bbs-deleted:' + copy.dataset.uid, LIMIT = 3000;
    let deleted = [];
    try { deleted = JSON.parse(localStorage.getItem(KEY)) || []; } catch (err) { /* blocked storage: nothing is remembered */ }
    const apply = () => {
      const gone = new Set(deleted);
      document.querySelectorAll('[data-line]').forEach(line => { if (gone.has(line.dataset.line)) line.remove(); });
      document.querySelectorAll('[data-last-line]').forEach(preview => { if (gone.has(preview.dataset.lastLine)) preview.textContent = copy.dataset.deletedLabel; });
    };
    document.addEventListener('click', event => {
      const button = event.target.closest('[data-delete-line]');
      if (!button) return;
      deleted = [...deleted, button.dataset.deleteLine].slice(-LIMIT);
      try { localStorage.setItem(KEY, JSON.stringify(deleted)); } catch (err) { /* still gone until this page reloads */ }
      apply();
    });
    document.addEventListener('bbs:messages-added', apply);
    apply();
  }

  const dropExpired = () => {
    const now = Date.now() / 1000;
    document.querySelectorAll('[data-recall-until]').forEach(button => { if (Number(button.dataset.recallUntil) <= now) button.remove(); });
  };
  dropExpired();
  setInterval(dropExpired, 5000);
})();
