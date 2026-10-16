// AI listing draft: sends one photo to /items/ai-draft/ and fills the item form with the reply.
// A separate file because the production CSP only allows script-src 'self'.
(() => {
  const panel = document.getElementById('ai-panel');
  if (!panel) return;
  const file = document.getElementById('ai-photo'), run = document.getElementById('ai-run'), status = document.getElementById('ai-status');
  panel.hidden = false;
  run.addEventListener('click', async () => {
    if (!file.files.length) { status.textContent = panel.dataset.pick; return; }
    run.disabled = true;
    status.textContent = panel.dataset.wait;
    const body = new FormData();
    body.append('photo', file.files[0]);
    try {
      const r = await fetch('/items/ai-draft/', {method: 'POST', body, credentials: 'same-origin', headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value}});
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || panel.dataset.fail);
      for (const [key, value] of Object.entries(data.draft)) {
        const el = document.getElementById('id_' + key);
        if (el && value !== '') el.value = value;
      }
      const main = document.getElementById('id_photo');
      if (main && !main.files.length) main.files = file.files;
      status.textContent = panel.dataset.done;
    } catch (e) {
      status.textContent = e.message || panel.dataset.fail;
    } finally {
      run.disabled = false;
    }
  });
})();
