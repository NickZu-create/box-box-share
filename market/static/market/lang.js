// Switching language reloads the same page. Keep whatever the visitor has typed but not sent, and the
// scroll position, so changing language never loses a half-written form. Same-tab sessionStorage only.
(() => {
  const key = 'bbs-lang-draft:' + location.pathname;
  const fields = () => [...document.querySelectorAll('main form')].flatMap((form, f) => [...form.elements].map((el) => [f, el]));
  const skip = (el) => !el.name || ['hidden', 'file', 'password', 'submit', 'button'].includes(el.type) || el.name === 'csrfmiddlewaretoken';
  const changed = (el) => {
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked !== el.defaultChecked;
    if (el.tagName === 'SELECT') return [...el.options].some((o) => o.selected !== o.defaultSelected);
    return el.value !== el.defaultValue;
  };

  document.getElementById('lang-form')?.addEventListener('submit', () => {
    const values = [];
    for (const [f, el] of fields()) {
      if (skip(el) || !changed(el)) continue;
      values.push([f, el.name, el.type === 'checkbox' || el.type === 'radio' ? el.value : null, el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.tagName === 'SELECT' && el.multiple ? [...el.selectedOptions].map((o) => o.value) : el.value]);
    }
    try { sessionStorage.setItem(key, JSON.stringify({ scroll: window.scrollY, values })); } catch (e) { /* storage blocked: switch without restoring */ }
  });

  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(key)); sessionStorage.removeItem(key); } catch (e) { saved = null; }
  if (!saved) return;
  const forms = [...document.querySelectorAll('main form')];
  for (const [f, name, option, value] of saved.values) {
    const form = forms[f];
    if (!form) continue;
    for (const el of form.querySelectorAll('[name]')) {
      if (el.name !== name || skip(el)) continue;
      if (option !== null) { if (el.value === option) el.checked = value; }
      else if (Array.isArray(value)) for (const o of el.options) o.selected = value.includes(o.value);
      else el.value = value;
    }
  }
  window.scrollTo(0, saved.scroll || 0);
})();
