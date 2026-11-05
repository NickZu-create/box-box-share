// The date picker on a rental listing. Booked days are greyed out and cannot be chosen.
// It fills in the page's own start and end fields, which still work by hand if this script does not run.
(() => {
  'use strict';
  const root = document.querySelector('[data-booking-calendar]');
  if (!root) return;
  const form = root.closest('form');
  const startField = form.elements.namedItem('start'), endField = form.elements.namedItem('end');
  if (!startField || !endField) return;

  const data = JSON.parse(root.dataset.calendar), copy = root.dataset;
  const booked = new Set(data.booked);
  const lang = document.documentElement.lang || 'en';
  const DAY = 86400000, DEFAULT_START = '10:00', DEFAULT_END = '18:00';
  // Dates are plain YYYY-MM-DD strings handled in UTC, so the visitor's own time zone can never shift a day.
  const ms = iso => Date.parse(`${iso}T00:00:00Z`);
  const toIso = value => new Date(value).toISOString().slice(0, 10);
  const addDays = (iso, days) => toIso(ms(iso) + days * DAY);
  const dateFormat = options => new Intl.DateTimeFormat(lang, { timeZone: 'UTC', ...options });
  const longDate = dateFormat({ year: 'numeric', month: 'long', day: 'numeric' });
  const shortDate = dateFormat({ month: 'numeric', day: 'numeric' });
  const monthName = dateFormat({ year: 'numeric', month: 'long' });
  const weekday = dateFormat({ weekday: 'narrow' });

  const selectable = iso => iso >= data.first && iso <= data.last && !booked.has(iso);
  const firstFree = () => {
    for (let iso = data.first; iso <= data.last; iso = addDays(iso, 1)) if (selectable(iso)) return iso;
    return '';
  };
  // The furthest day a loan starting here can reach: no booked day may fall inside it.
  const reachFrom = start => {
    const limit = addDays(start, Math.max(data.maxDays, 1) - 1);
    let reach = start;
    while (reach < limit && reach < data.last && !booked.has(addDays(reach, 1))) reach = addDays(reach, 1);
    return reach;
  };

  let startDate = '', endDate = '', extending = false;
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  // ---- Fixed parts
  root.hidden = false;
  const head = element('div', 'cal-head');
  const previous = element('button', 'cal-nav', '‹'), next = element('button', 'cal-nav', '›'), title = element('strong', 'cal-title');
  previous.type = next.type = 'button';
  previous.setAttribute('aria-label', copy.previousMonth);
  next.setAttribute('aria-label', copy.nextMonth);
  title.setAttribute('aria-live', 'polite');
  head.append(previous, title, next);
  const week = element('div', 'cal-week');
  week.setAttribute('aria-hidden', 'true');
  for (let index = 0; index < 7; index++) week.append(element('span', '', weekday.format(ms('2023-01-01') + index * DAY)));
  const grid = element('div', 'cal-grid');
  const legend = element('p', 'cal-legend');
  legend.append(element('span', 'cal-key cal-key-booked', copy.legendBooked), element('span', 'cal-key cal-key-picked', copy.legendPicked));
  const times = element('div', 'cal-times');
  const timeField = label => {
    const wrap = element('label', 'cal-time');
    const input = element('input');
    input.type = 'time';
    input.step = 900;
    wrap.append(element('span', '', label), input);
    times.append(wrap);
    return input;
  };
  const startTime = timeField(copy.startTime), endTime = timeField(copy.endTime);
  const summary = element('p', 'cal-summary');
  summary.setAttribute('role', 'status');
  const problem = element('p', 'cal-problem');
  problem.setAttribute('role', 'alert');
  problem.hidden = true;
  root.append(head, week, grid, legend, times, summary, problem);

  for (const field of [startField, endField]) {
    // The calendar is now how these are filled in; a hidden required field would silently block the form.
    field.required = false;
    const row = field.closest('p');
    if (row) row.hidden = true;
  }

  // ---- Keeping the form's own fields right
  const clockPlus = (time, minutes) => {
    const [hours, mins] = time.split(':').map(Number);
    const total = Math.min(hours * 60 + mins + minutes, 23 * 60 + 59);
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  };
  const forgetQuote = () => {
    // A price worked out for other dates must not be applied to these.
    form.querySelector('.rental-quote')?.remove();
    form.querySelector('[name=quote_token]')?.remove();
    form.querySelector('button[name=action][value=apply]')?.remove();
  };
  const sync = changed => {
    problem.hidden = true;
    startTime.disabled = endTime.disabled = !startDate;
    if (!startDate) {
      startField.value = endField.value = startTime.value = endTime.value = '';
      summary.textContent = copy.pickStart;
      return;
    }
    const earliest = startDate === data.first ? data.firstTime : '';
    const latest = endDate === data.last ? data.lastTime : '';
    startTime.min = earliest;
    endTime.max = latest;
    if (!startTime.value) startTime.value = DEFAULT_START;
    if (!endTime.value) endTime.value = DEFAULT_END;
    if (earliest && startTime.value < earliest) startTime.value = earliest;
    if (latest && endTime.value > latest) endTime.value = latest;
    if (startDate === endDate && endTime.value <= startTime.value) {
      endTime.value = clockPlus(startTime.value, 60);
      if (latest && endTime.value > latest) endTime.value = latest;
    }
    endTime.min = startDate === endDate ? startTime.value : '';
    startField.value = `${startDate}T${startTime.value}`;
    endField.value = `${endDate}T${endTime.value}`;
    const span = Date.parse(`${endField.value}:00Z`) - Date.parse(`${startField.value}:00Z`);
    const days = Math.max(Math.ceil(span / DAY), 1);
    const range = startDate === endDate ? shortDate.format(ms(startDate)) : `${shortDate.format(ms(startDate))} – ${shortDate.format(ms(endDate))}`;
    summary.textContent = `${range} · ${days} ${copy.dayUnit}${extending ? ` · ${copy.pickEnd}` : ''}`;
    if (changed) forgetQuote();
  };

  // ---- The month grid
  let month = '';
  const monthStart = iso => `${iso.slice(0, 7)}-01`;
  const shiftMonth = (iso, by) => {
    const date = new Date(ms(iso));
    return toIso(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + by, 1));
  };
  const render = () => {
    title.textContent = monthName.format(ms(month));
    previous.disabled = month <= monthStart(data.first);
    next.disabled = month >= monthStart(data.last);
    grid.replaceChildren();
    const lead = new Date(ms(month)).getUTCDay();
    for (let index = 0; index < lead; index++) grid.append(element('span', 'cal-blank'));
    const reach = extending ? reachFrom(startDate) : '';
    for (let iso = month; iso.slice(0, 7) === month.slice(0, 7); iso = addDays(iso, 1)) {
      const button = element('button', 'cal-day', String(Number(iso.slice(8))));
      button.type = 'button';
      button.dataset.date = iso;
      const isBooked = booked.has(iso) && iso >= data.first && iso <= data.last;
      const picked = startDate && iso >= startDate && iso <= endDate;
      let spoken = longDate.format(ms(iso));
      if (isBooked) { button.classList.add('is-booked'); spoken += ` · ${copy.legendBooked}`; }
      else if (iso < data.first || iso > data.last) { button.classList.add('is-outside'); spoken += ` · ${copy.notAvailable}`; }
      else if (extending && iso > reach) button.classList.add('is-far');
      // Disabled for real: a booked day cannot be clicked, focused or chosen.
      button.disabled = !selectable(iso);
      if (picked) button.classList.add('is-picked');
      if (iso === startDate) button.classList.add('is-start');
      if (iso === endDate) button.classList.add('is-end');
      button.setAttribute('aria-label', spoken);
      button.setAttribute('aria-pressed', String(Boolean(picked)));
      grid.append(button);
    }
  };
  grid.addEventListener('click', event => {
    const button = event.target.closest('.cal-day');
    if (!button || button.disabled) return;
    const iso = button.dataset.date;
    if (extending && iso >= startDate && iso <= reachFrom(startDate)) {
      endDate = iso;
      extending = false;
    } else {
      // One tap is already a valid one-day loan; a second tap further on extends it.
      startDate = endDate = iso;
      extending = true;
    }
    render();
    sync(true);
    grid.querySelector(`[data-date="${iso}"]`)?.focus();
  });
  previous.addEventListener('click', () => { month = shiftMonth(month, -1); render(); });
  next.addEventListener('click', () => { month = shiftMonth(month, 1); render(); });
  for (const input of [startTime, endTime]) input.addEventListener('change', () => sync(true));
  form.addEventListener('submit', event => {
    if (startField.value && endField.value) return;
    event.preventDefault();
    problem.textContent = copy.pickStart;
    problem.hidden = false;
  });

  // ---- Start: what the page came back with, as long as those days are still free
  const earlierStart = startField.value.slice(0, 10), earlierEnd = endField.value.slice(0, 10);
  if (earlierStart && earlierEnd && selectable(earlierStart) && earlierEnd >= earlierStart && earlierEnd <= reachFrom(earlierStart)) {
    startDate = earlierStart;
    endDate = earlierEnd;
    startTime.value = startField.value.slice(11, 16);
    endTime.value = endField.value.slice(11, 16);
  }
  const free = firstFree();
  if (!free) {
    grid.remove();
    week.remove();
    head.remove();
    legend.remove();
    times.remove();
    summary.textContent = copy.noDates;
    form.querySelector('button[name=action][value=quote]')?.setAttribute('disabled', '');
    return;
  }
  month = monthStart(startDate || free);
  render();
  sync(false);
})();
