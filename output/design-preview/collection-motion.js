/* Progressive enhancement for the two local collection routes only.
   Real links, history, filters and direct-entry URLs remain authoritative. */
(() => {
  'use strict';
  if (!document.body.classList.contains('collection-page')) return;
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const language = document.body.dataset.language;
  const routes = new Set(['/' + language + '/', '/' + language + '/seeking/']);
  const positions = new Map();
  let entryNumber = 0;
  let currentKey = history.state?.collectionKey || 'collection-' + Date.now();
  let currentURL = new URL(location.href);
  let hero = null, slot = null, metrics = null;
  let scrollFrame = 0, resizeFrame = 0;
  let requestId = 0, requestController = null, runningTransition = null;
  const duration = 480;
  const easing = 'cubic-bezier(.22,.72,.2,1)';

  function stickyTop() {
    return (document.querySelector('.site-header')?.getBoundingClientRect().height || 60) + 12;
  }

  function measureBox(collapsed) {
    const clone = hero.cloneNode(true);
    clone.removeAttribute('id');
    clone.classList.remove('is-scroll-driven', 'is-collapsed');
    clone.classList.add('is-measuring');
    if (collapsed) clone.classList.add('is-collapsed');
    clone.inert = true;
    clone.setAttribute('aria-hidden', 'true');
    clone.style.cssText = 'position:absolute;left:-100000px;top:0;visibility:hidden;pointer-events:none;height:auto;max-width:none;width:' + slot.getBoundingClientRect().width + 'px;view-transition-name:none';
    document.body.append(clone);
    const height = clone.getBoundingClientRect().height;
    clone.remove();
    return height;
  }

  function renderScroll() {
    scrollFrame = 0;
    positions.set(currentKey, scrollY);
    if (!hero || !slot || !metrics || reduceMotion.matches) return;
    const distance = Math.max(1, metrics.open - metrics.closed);
    const progress = Math.min(1, Math.max(0, (scrollY - (metrics.top - metrics.sticky)) / distance));
    hero.style.height = (metrics.open - distance * progress) + 'px';
    hero.style.setProperty('--hero-progress', progress.toFixed(5));
    hero.dataset.size = progress >= .999 ? 'compact' : progress <= .001 ? 'expanded' : 'shrinking';
    hero.classList.toggle('is-collapsed', progress >= .999);
    const concealed = progress >= 1 / 3;
    const actions = hero.querySelector('.hero-links');
    if (actions) actions.inert = concealed;
    hero.querySelectorAll('.hero-copy > p,.hero-links,.hero-note').forEach(node => {
      if (concealed) node.setAttribute('aria-hidden', 'true');
      else node.removeAttribute('aria-hidden');
    });
  }

  function measureHero() {
    if (!hero || !slot || !hero.isConnected) return;
    if (reduceMotion.matches) {
      hero.classList.remove('is-scroll-driven', 'is-collapsed');
      hero.style.height = '';
      hero.style.removeProperty('--hero-progress');
      slot.style.height = '';
      hero.querySelectorAll('.hero-copy > p,.hero-links,.hero-note').forEach(node => node.removeAttribute('aria-hidden'));
      const actions = hero.querySelector('.hero-links');
      if (actions) actions.inert = false;
      metrics = null;
      return;
    }
    const open = measureBox(false), closed = Math.min(open, measureBox(true));
    slot.style.height = open + 'px';
    slot.style.setProperty('--hero-sticky-top', stickyTop() + 'px');
    slot.style.setProperty('--hero-open-height', open + 'px');
    slot.style.setProperty('--hero-closed-height', closed + 'px');
    metrics = {open, closed, top: slot.getBoundingClientRect().top + scrollY, sticky: stickyTop()};
    hero.classList.add('is-scroll-driven');
    renderScroll();
  }

  function mountHero() {
    hero = document.querySelector('.borrow-hero');
    slot = document.querySelector('.borrow-hero-slot');
    metrics = null;
    if (hero && slot) measureHero();
    else document.querySelector('.hero-motion')?.setAttribute('data-size', 'compact');
  }

  function savePosition() {
    positions.set(currentKey, scrollY);
    history.replaceState({...history.state, collectionKey: currentKey, scrollY}, '', location.href);
  }

  function isCollectionURL(url) {
    return url.origin === location.origin && routes.has(url.pathname);
  }

  function scrollDestination(url, savedPosition = 0) {
    if (url.hash === '#discover') {
      const section = document.getElementById('discover');
      return section ? Math.max(0, section.getBoundingClientRect().top + scrollY - stickyTop()) : 0;
    }
    return savedPosition;
  }

  async function navigate(url, {push = true, key = null, restoreY = 0} = {}) {
    const id = ++requestId;
    requestController?.abort();
    requestController = new AbortController();
    document.body.classList.add('is-collection-loading');
    document.querySelector('main')?.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url.href, {signal: requestController.signal});
      if (!response.ok) throw new Error('Collection route unavailable');
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (!next.body.classList.contains('collection-page') || next.body.dataset.language !== language || !next.querySelector('main .hero-motion')) {
        throw new Error('Unexpected collection document');
      }
      if (id !== requestId) return;
      if (push) savePosition();
      runningTransition?.skipTransition?.();
      const oldHeroRect = document.querySelector('.hero-motion')?.getBoundingClientRect();
      const update = () => {
        if (id !== requestId) return;
        if (push) {
          key = 'collection-' + Date.now() + '-' + (++entryNumber);
          history.pushState({collectionKey: key, scrollY: 0}, '', url.href);
        }
        currentKey = key || 'collection-' + Date.now() + '-' + (++entryNumber);
        currentURL = new URL(url.href);
        document.body.className = next.body.className;
        document.body.dataset.route = next.body.dataset.route;
        document.body.dataset.notice = next.body.dataset.notice;
        document.title = next.title;
        for (const selector of ['.site-header', 'main', '.mobile-primary']) {
          const old = document.querySelector(selector), replacement = next.querySelector(selector);
          if (old && replacement) old.replaceWith(document.importNode(replacement, true));
        }
        // Scripts in the fetched document are never adopted or executed.
        document.dispatchEvent(new Event('collection:mounted'));
        window.scrollTo({top: 0, left: 0, behavior: 'instant'});
        mountHero();
        window.scrollTo({top: scrollDestination(url, restoreY), left: 0, behavior: 'instant'});
        renderScroll();
      };
      document.documentElement.dataset.collectionTransition = reduceMotion.matches ? 'reduced' : 'running';
      if (!reduceMotion.matches && typeof document.startViewTransition === 'function') {
        document.documentElement.dataset.collectionTransitionMode = 'native';
        const transition = document.startViewTransition(update);
        runningTransition = transition;
        await transition.finished;
      } else {
        document.documentElement.dataset.collectionTransitionMode = reduceMotion.matches ? 'reduced' : 'fallback';
        update();
        if (!reduceMotion.matches) {
          const animations = [];
          const nextHero = document.querySelector('.hero-motion');
          if (nextHero && oldHeroRect) {
            const nextHeight = nextHero.getBoundingClientRect().height;
            const host = document.querySelector('.borrow-hero-slot') || nextHero;
            const frames = [{height: oldHeroRect.height + 'px'}, {height: nextHeight + 'px'}];
            animations.push(host.animate(frames, {duration, easing, fill: 'both'}));
            if (host !== nextHero) animations.push(nextHero.animate(frames, {duration, easing, fill: 'both'}));
          }
          const content = document.querySelector('.collection-content');
          if (content) animations.push(content.animate([{opacity: 0, transform: 'translateY(12px)'}, {opacity: 1, transform: 'none'}], {duration, easing, fill: 'both'}));
          await Promise.all(animations.map(animation => animation.finished.catch(() => {})));
          animations.forEach(animation => animation.cancel());
        }
      }
      if (id === requestId) document.documentElement.dataset.collectionTransition = 'settled';
    } catch (error) {
      if (id !== requestId || error.name === 'AbortError') return;
      location.assign(url.href); // Real-link fallback, never a broken partial page.
    } finally {
      if (id === requestId) {
        requestController = null;
        runningTransition = null;
        document.body.classList.remove('is-collection-loading');
        document.querySelector('main')?.removeAttribute('aria-busy');
      }
    }
  }

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const url = new URL(link.href, location.href);
    if (!isCollectionURL(url)) return;
    if (url.pathname === location.pathname && url.search === location.search) {
      if (url.hash === '#discover') {
        event.preventDefault();
        ++requestId;
        requestController?.abort();
        runningTransition?.skipTransition?.();
        document.body.classList.remove('is-collection-loading');
        document.querySelector('main')?.removeAttribute('aria-busy');
        savePosition();
        currentKey = 'collection-' + Date.now() + '-' + (++entryNumber);
        history.pushState({collectionKey: currentKey}, '', url.href);
        currentURL = url;
        window.scrollTo({top: scrollDestination(url), behavior: reduceMotion.matches ? 'instant' : 'smooth'});
      } else if (!url.hash) {
        event.preventDefault();
        ++requestId;
        requestController?.abort();
        runningTransition?.skipTransition?.();
        document.body.classList.remove('is-collection-loading');
        document.querySelector('main')?.removeAttribute('aria-busy');
        history.replaceState({...history.state, scrollY: 0}, '', url.href);
        currentURL = url;
        window.scrollTo({top: 0, behavior: reduceMotion.matches ? 'instant' : 'smooth'});
      }
      return;
    }
    event.preventDefault();
    navigate(url);
  });

  window.addEventListener('popstate', event => {
    positions.set(currentKey, scrollY);
    const url = new URL(location.href);
    if (!isCollectionURL(url)) { location.reload(); return; }
    const key = event.state?.collectionKey;
    const restoreY = positions.get(key) ?? event.state?.scrollY ?? 0;
    if (url.pathname === currentURL.pathname && url.search === currentURL.search) {
      ++requestId;
      requestController?.abort();
      runningTransition?.skipTransition?.();
      document.body.classList.remove('is-collection-loading');
      document.querySelector('main')?.removeAttribute('aria-busy');
      currentKey = key || currentKey;
      currentURL = url;
      document.dispatchEvent(new Event('collection:mounted'));
      window.scrollTo({top: scrollDestination(url, restoreY), behavior: 'instant'});
      renderScroll();
    } else navigate(url, {push: false, key, restoreY});
  });

  window.addEventListener('scroll', () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(renderScroll);
  }, {passive: true});
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(measureHero);
  }, {passive: true});
  reduceMotion.addEventListener('change', measureHero);
  document.addEventListener('collection:filters-changed', () => { currentURL = new URL(location.href); });
  window.addEventListener('pagehide', savePosition);
  window.addEventListener('pageshow', event => {
    history.scrollRestoration = 'manual';
    if (event.persisted) measureHero();
  });
  document.addEventListener('DOMContentLoaded', () => {
    document.documentElement.dataset.collectionRouter = 'ready';
    history.scrollRestoration = 'manual';
    history.replaceState({...history.state, collectionKey: currentKey, scrollY}, '', location.href);
    mountHero();
    if (location.hash === '#discover') window.scrollTo({top: scrollDestination(new URL(location.href)), behavior: 'instant'});
    document.fonts?.ready.then(measureHero);
  });
})();
