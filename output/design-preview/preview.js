/* Local, synthetic-data preview interactions. No API calls or message writes. */
(() => {
  'use strict';
  const body = document.body;
  const language = body.dataset.language || 'hans';
  const copy = (hans, traditional, english) => language === 'en' ? english : language === 'zh' ? traditional : hans;
  const app = body.classList.contains('preview-app');
  let noticeTimer;

  function previewNotice() {
    const notice = document.getElementById('showcase-notice');
    if (!notice) return;
    notice.textContent = body.dataset.notice || copy(
      '仅展示示例流程，不会发送消息或创建交易。',
      '僅展示示例流程，不會傳送訊息或建立交易。',
      'This is a sample flow. No messages or transactions are sent.'
    );
    notice.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { notice.hidden = true; }, 5000);
  }

  // datetime-local values represent Hong Kong time, regardless of device zone.
  function hongKongTimestamp(value) {
    if (!value || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)) return NaN;
    return Date.parse(value + '+08:00');
  }

  function fieldValue(form, name) {
    const field = form.elements.namedItem(name);
    return field && typeof field.value === 'string' ? field.value.trim() : '';
  }

  function restoreFilters(form) {
    const params = new URLSearchParams(location.search);
    for (const field of form.elements) {
      if (!field.name || !params.has(field.name) || field.type === 'submit' || field.type === 'button') continue;
      const value = params.get(field.name);
      if (field.tagName === 'SELECT' && ![...field.options].some(option => option.value === value)) continue;
      field.value = value;
    }
  }

  function saveFilters(form) {
    const url = new URL(location.href);
    for (const field of form.elements) {
      if (!field.name || field.type === 'submit' || field.type === 'button' || field.type === 'reset') continue;
      const value = field.value.trim();
      if (value) url.searchParams.set(field.name, value);
      else url.searchParams.delete(field.name);
    }
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    document.dispatchEvent(new Event('collection:filters-changed'));
  }

  function validateFilters(form) {
    const price = fieldValue(form, 'price');
    const priceField = form.elements.namedItem('price');
    if ((priceField && priceField.validity && priceField.validity.badInput) ||
        (price !== '' && (!Number.isFinite(Number(price)) || Number(price) < 0))) {
      if(form.dataset.filter==='items'&&fieldValue(form,'intent')!=='rent')return copy('请输入不小于 0 的金额上限。','請輸入不小於 0 的金額上限。','Enter a price limit of zero or more.');
      return form.dataset.filter === 'wanted'
        ? copy('请输入不小于 0 的总预算上限。', '請輸入不小於 0 的總預算上限。', 'Enter a total budget limit of zero or more.')
        : copy('请输入不小于 0 的每日租金上限。', '請輸入不小於 0 的每日租金上限。', 'Enter a daily price limit of zero or more.');
    }
    const start = fieldValue(form, 'start');
    const end = fieldValue(form, 'end');
    const invalidDateField = ['start', 'end'].some(name => {
      const field = form.elements.namedItem(name);
      return field && field.validity && field.validity.badInput;
    });
    if (invalidDateField) {
      return copy('请输入有效的香港日期和时间。', '請輸入有效的香港日期和時間。', 'Enter valid dates and times in Hong Kong time.');
    }
    if (Boolean(start) !== Boolean(end)) {
      return copy('请同时填写开始和结束时间，或清空两个日期。', '請同時填寫開始和結束時間，或清空兩個日期。', 'Enter both start and end times, or clear both dates.');
    }
    if (start && (!Number.isFinite(hongKongTimestamp(start)) || !Number.isFinite(hongKongTimestamp(end)))) {
      return copy('请输入有效的香港日期和时间。', '請輸入有效的香港日期和時間。', 'Enter valid dates and times in Hong Kong time.');
    }
    if (start && hongKongTimestamp(end) <= hongKongTimestamp(start)) {
      return copy('结束时间须晚于开始时间。', '結束時間須晚於開始時間。', 'The end time must be after the start time.');
    }
    return '';
  }

  function applyFilters(form, updateUrl = false) {
    if (updateUrl) saveFilters(form);
    const type = form.dataset.filter;
    const selector = type === 'buddy' ? '.recruitment-row' : type === 'wanted' ? '.wanted-tile' : '.item-tile';
    const cards = [...document.querySelectorAll(selector)];
    const status = document.getElementById('filter-status');
    const count = document.getElementById('result-count');
    const empty = document.getElementById('empty-results');
    const collection = type === 'items' || type === 'wanted';
    if (collection) {
      const hasFilters = ['q', 'category', 'price', 'start', 'end','intent'].some(name => fieldValue(form, name) !== '');
      document.querySelectorAll('.collection-summary [data-clear-filters]').forEach(button => { button.hidden = !hasFilters; });
    }
    const error = validateFilters(form);
    if (error) {
      cards.forEach(card => { card.hidden = true; });
      if (status) { status.textContent = error; status.dataset.state = 'error'; }
      if (count) count.textContent = '—';
      if (empty) empty.hidden = true;
      form.dataset.invalid = 'true';
      return;
    }
    delete form.dataset.invalid;
    if (status) status.dataset.state = 'ready';
    const query = fieldValue(form, 'q').toLocaleLowerCase();
    const terms = query.split(/\s+/).filter(Boolean);
    const category = fieldValue(form, 'category');
    const kind = fieldValue(form, 'kind');
    const price = fieldValue(form, 'price');
    const intent = fieldValue(form, 'intent');
    const startText = fieldValue(form, 'start');
    const endText = fieldValue(form, 'end');
    const requestedStart = hongKongTimestamp(startText);
    const requestedEnd = hongKongTimestamp(endText);
    const selectedState = fieldValue(form, 'state') || 'open';
    const days = { today: 1, week: 7, month: 30 }[fieldValue(form, 'when')];
    const now = Date.now();
    let matches = 0;
    for (const card of cards) {
      const text = (card.dataset.search || card.textContent).toLocaleLowerCase();
      let show = terms.every(term => text.includes(term));
      if(type==='buddy' && window.BoxStudentDemo){
        show=window.BoxStudentDemo.match(text,query)||!query;
        const major=fieldValue(form,'major');
        if(major&&!window.BoxStudentDemo.match(card.dataset.major,major))show=false;
      }
      if (category && card.dataset.category !== category) show = false;
      if (kind && card.dataset.kind !== kind) show = false;
      if (intent && card.dataset.intent !== intent) show = false;
      if (type === 'items') {
        const amount = Number(card.dataset.price);
        if (price !== '' && (!Number.isFinite(amount) || amount > Number(price))) show = false;
        if (startText && endText && card.dataset.intent !== 'sale') {
          const availableStart = Date.parse(card.dataset.start);
          const availableEnd = Date.parse(card.dataset.end);
          const maximumDays = Number(card.dataset.maxDays);
          const requestedDays = Math.ceil((requestedEnd - requestedStart) / 86400000);
          if (!Number.isFinite(availableStart) || !Number.isFinite(availableEnd) ||
              requestedStart < availableStart || requestedEnd > availableEnd ||
              (Number.isFinite(maximumDays) && maximumDays > 0 && requestedDays > maximumDays)) show = false;
        }
      } else if (type === 'wanted') {
        // Seeking uses the existing backend rules: total budget ceiling and
        // overlapping requested periods, with touching endpoints excluded.
        const budget = Number(card.dataset.price);
        const requestEnd = Date.parse(card.dataset.end);
        const stateLabel = card.querySelector('.request-state');
        if (stateLabel && card.dataset.intent !== 'buy' && Number.isFinite(requestEnd) && requestEnd <= now) {
          stateLabel.textContent = copy('已过期', '已過期', 'Expired');
          stateLabel.classList.add('expired');
        }
        if (price !== '' && (!Number.isFinite(budget) || budget > Number(price))) show = false;
        if (startText && endText && card.dataset.intent !== 'buy') {
          const neededStart = Date.parse(card.dataset.start);
          const neededEnd = Date.parse(card.dataset.end);
          if (!Number.isFinite(neededStart) || !Number.isFinite(neededEnd) ||
              neededStart >= requestedEnd || neededEnd <= requestedStart) show = false;
        }
      } else {
        const starts = Date.parse(card.dataset.start);
        const ends = Date.parse(card.dataset.end);
        let state = card.dataset.state;
        if ((state === 'open' || state === 'full') && Number.isFinite(ends) && ends <= now) state = 'ended';
        if (selectedState !== 'all' && state !== selectedState) show = false;
        if (days && (!Number.isFinite(starts) || !Number.isFinite(ends) || ends <= now || starts >= now + days * 86400000)) show = false;
      }
      card.hidden = !show;
      if (show) matches += 1;
    }
    if (count) count.textContent = matches + (type === 'buddy' ? copy(' 个招募', ' 個招募', ' posts') : type === 'wanted' ? copy(' 条求物', ' 條求物', ' requests') : copy(' 件物品', ' 件物品', ' items'));
    if (empty) empty.hidden = matches !== 0;
    if(type==='buddy' && window.BoxStudentDemo)window.BoxStudentDemo.rank(cards,form);
    if (status) {
      const result = matches + copy(' 条匹配结果', ' 條符合結果', ' matching results');
      const active = query || category || kind || price !== '' || startText || fieldValue(form, 'when') || (type === 'buddy' && selectedState !== 'open');
      status.textContent = !active ? '' : startText ? result + (type === 'wanted' ? copy(
        '。显示求物时段与所选日期有重叠的示例，不代表已找到可借物品。',
        '。顯示求物時段與所選日期有重疊的示例，不代表已找到可借物品。',
        '. Shows sample requests whose needed period overlaps your dates; no available item is implied.'
      ) : copy(
        '。仅按示例可借时段与最长借期筛选，不代表真实库存或订单占用。',
        '。僅按示例可借時段與最長借期篩選，不代表真實庫存或訂單佔用。',
        '. Dates check sample availability windows and maximum duration only, not live reservations.'
      )) : result;
      if (collection && !startText) status.textContent = '';
      if (collection && startText) status.textContent = type === 'wanted'
        ? copy('按所选时段的交集筛选求借需求。', '按所選時段的交集篩選求借需求。', 'Requests overlap your selected period.')
        : copy('按示例可借窗口筛选，借用仍须检查实际占用。', '按示例可借窗口篩選，借用仍須檢查實際佔用。', 'Sample windows only; reservations still need checking.');
    }
  }

  function revealManagement() {
    let hash;
    try { hash = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    if (!hash) return;
    const target = document.getElementById(hash);
    const container = target && target.closest('details');
    if (container) container.open = true;
    if (target instanceof HTMLDetailsElement) target.open = true;
  }

  function initializeCurrentFilters() {
    const filters = [...document.querySelectorAll('.filter-form[data-filter]')];
    if (app) filters.forEach(form => { restoreFilters(form); applyFilters(form); });
  }

  document.addEventListener('collection:mounted', () => {
    document.querySelectorAll('.filter-form[data-filter]').forEach(form => form.reset());
    initializeCurrentFilters();
    revealManagement();
  });

  document.addEventListener('DOMContentLoaded', () => {
    initializeCurrentFilters();
    const sidebar = document.querySelector('.conversation-sidebar');
    const current = sidebar && sidebar.querySelector('.thread-row.current');
    if (sidebar && current) {
      const rail = current.closest('.thread-list') || sidebar;
      const keepCurrentVisible = () => {
        const current = sidebar.querySelector('.thread-row.current');
        if (!current) return;
        if (!sidebar.getClientRects().length || !rail.clientHeight) return;
        const difference = current.getBoundingClientRect().top - rail.getBoundingClientRect().top;
        if (difference < 0 || difference + current.offsetHeight > rail.clientHeight) {
          rail.scrollTop += difference - Math.max(0, (rail.clientHeight - current.offsetHeight) / 2);
        }
      };
      keepCurrentVisible();
      new ResizeObserver(keepCurrentVisible).observe(sidebar);
    }
    revealManagement();
    window.addEventListener('hashchange', revealManagement);
    if (app) window.addEventListener('popstate', () => {
      if (document.documentElement.dataset.collectionRouter === 'ready') return;
      document.querySelectorAll('.filter-form[data-filter]').forEach(form => { form.reset(); restoreFilters(form); applyFilters(form); });
    });
  });

  document.addEventListener('submit', event => {
    if (!app) return; // Legacy pages retain their existing showcase handlers.
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    if (form.matches('.filter-form[data-filter]')) { applyFilters(form, true); return; }
    if (form.matches('[data-demo-language]')) {
      const selected = event.submitter && event.submitter.value || new FormData(form).get('lang');
      if (!['en', 'zh', 'hans'].includes(selected)) return;
      const route = (body.dataset.route || '/').replace(/^\/(?:en|zh|hans)(?=\/)/, '');
      const target = new URL('/' + selected + (route.startsWith('/') ? route : '/' + route), location.origin);
      target.search = location.search;
      target.hash = location.hash;
      location.href = target.href;
      return;
    }
    const destination = event.submitter && event.submitter.dataset.demoLink;
    if (destination) { location.href = destination; return; }
    previewNotice();
  });

  document.addEventListener('reset', event => {
    if (!app || !event.target.matches('.filter-form[data-filter]')) return;
    // Reset values settle after the native reset event.
    setTimeout(() => { if (event.target.isConnected) applyFilters(event.target, true); }, 0);
  });

  document.addEventListener('click', event => {
    const more = document.querySelector('details.more-nav');
    if (more && more.open && !more.contains(event.target)) more.open = false;
    if (!app) return;
    const destination = event.target.closest('[data-demo-link]');
    if (destination) { event.preventDefault(); location.href = destination.dataset.demoLink; }
    const clear = event.target.closest('[data-clear-filters]');
    if (clear) {
      event.preventDefault();
      const form = document.querySelector('.filter-form[data-filter]');
      if (form) {
        form.reset();
        applyFilters(form, true);
        const query = form.elements.namedItem('q');
        if (query) query.focus();
      }
    }
  });

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('details.more-nav[open]').forEach(menu => {
      menu.open = false;
      const summary = menu.querySelector('summary');
      if (summary) summary.focus();
    });
  });
})();
