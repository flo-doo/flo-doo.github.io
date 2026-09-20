(() => {
  const root = document.documentElement;
  const toggle = document.querySelector('[data-theme-toggle]');

  function themeText() {
    if (!toggle) return;
    toggle.textContent = root.dataset.theme === 'light' ? 'View in dark mode' : 'View in light mode';
  }
  themeText();
  toggle?.addEventListener('click', () => {
    const next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('florence-doo-theme', next); } catch (_) {}
    themeText();
  });

  document.querySelectorAll('#year').forEach(el => { el.textContent = new Date().getFullYear(); });

  const esc = (s = '') => String(s).replace(/[&<>'"]/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[c]));

  async function loadJSON(path) {
    const r = await fetch(path, {cache: 'no-cache'});
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  }

  function eventDateEnd(date) {
    return new Date(`${date}T23:59:59`);
  }

  async function renderHomepageEvents() {
    const eventsEl = document.getElementById('upcoming-events');
    const countsEl = document.getElementById('speaking-counts');
    const venuesEl = document.getElementById('speaking-venues');
    if (!eventsEl && !countsEl && !venuesEl) return;

    try {
      const data = await loadJSON('data/events.json');
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const events = (data.events || []).slice().sort((a, b) => a.date.localeCompare(b.date));
      const upcoming = events.filter(e => eventDateEnd(e.date) >= today);

      if (eventsEl) {
        if (!upcoming.length) {
          eventsEl.innerHTML = '<p class="empty-state">No upcoming public appearances currently listed.</p>';
        } else {
          eventsEl.innerHTML = upcoming.map(e => {
            const details = [
              e.type && e.event ? `${e.type} · ${e.event}` : (e.type || e.event),
              e.note,
              e.time,
              e.location
            ].filter(Boolean).map(esc);
            const inner = `<div class="event-date">${esc(e.displayDate || e.date)}</div>` +
              `<span class="event-title">${esc(e.title)}</span>` +
              (details.length ? `<div class="event-meta">${details.join('<br>')}</div>` : '');
            return e.url
              ? `<a class="event-item" href="${esc(e.url)}" target="_blank" rel="noreferrer">${inner}</a>`
              : `<div class="event-item">${inner}</div>`;
          }).join('');
        }
      }

      if (countsEl) {
        const baseline = data.baseline || {asOf: '2026-09-19', counts: {local: 0, national: 0, international: 0}};
        const counts = {
          local: Number(baseline.counts?.local || 0),
          national: Number(baseline.counts?.national || 0),
          international: Number(baseline.counts?.international || 0)
        };
        for (const e of events) {
          if (!e.scope || !(e.scope in counts)) continue;
          if (e.date > baseline.asOf && eventDateEnd(e.date) < today) counts[e.scope] += 1;
        }
        const labels = {local: 'Local', national: 'National', international: 'International'};
        countsEl.innerHTML = ['local', 'national', 'international']
          .map(k => `<div class="speaking-stat"><strong>${counts[k]}</strong><span>${labels[k]}</span></div>`)
          .join('');
      }

      if (venuesEl) {
        const venues = data.selectedVenues || [];
        venuesEl.textContent = venues.length ? `Selected venues: ${venues.join(' · ')}` : '';
      }
    } catch (_) {
      if (eventsEl) eventsEl.innerHTML = '<p class="empty-state">Upcoming appearances could not be loaded.</p>';
    }
  }

  function enablePublicationBrowser() {
    const list = document.getElementById('all-publications');
    if (!list) return;

    const search = document.getElementById('pub-search');
    const count = document.getElementById('pub-count');
    const filters = document.getElementById('topic-filters');
    const items = Array.from(list.querySelectorAll('.pub-item'));
    let activeTopic = new URLSearchParams(location.search).get('topic') || 'all';

    const availableTopics = new Set(
      Array.from(filters?.querySelectorAll('[data-topic]') || []).map(b => b.dataset.topic)
    );
    if (!availableTopics.has(activeTopic)) activeTopic = 'all';

    function render() {
      const q = (search?.value || '').trim().toLowerCase();
      let shown = 0;
      items.forEach(item => {
        const topics = (item.dataset.topics || '').split(',').filter(Boolean);
        const topicOK = activeTopic === 'all' || topics.includes(activeTopic);
        const textOK = !q || item.textContent.toLowerCase().includes(q);
        const visible = topicOK && textOK;
        item.hidden = !visible;
        if (visible) shown += 1;
      });
      if (count) count.textContent = `${shown} publication${shown === 1 ? '' : 's'}`;
      filters?.querySelectorAll('[data-topic]').forEach(b => {
        b.classList.toggle('active', b.dataset.topic === activeTopic);
        b.setAttribute('aria-pressed', b.dataset.topic === activeTopic ? 'true' : 'false');
      });
    }

    filters?.addEventListener('click', e => {
      const b = e.target.closest('[data-topic]');
      if (!b) return;
      activeTopic = b.dataset.topic;
      const u = new URL(location.href);
      if (activeTopic === 'all') u.searchParams.delete('topic');
      else u.searchParams.set('topic', activeTopic);
      history.replaceState({}, '', u);
      render();
    });
    search?.addEventListener('input', render);
    render();
  }

  renderHomepageEvents();
  enablePublicationBrowser();
})();
