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

  document.querySelectorAll('#year').forEach(el => el.textContent = new Date().getFullYear());

  const esc = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const urlForPub = p => p.url || (p.doi ? `https://doi.org/${p.doi}` : (p.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/` : ''));

  async function loadJSON(path) {
    const r = await fetch(path, {cache: 'no-cache'});
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  }

  function eventDateEnd(date) {
    return new Date(`${date}T23:59:59`);
  }

  async function renderHomepage() {
    const eventsEl = document.getElementById('upcoming-events');
    const pubsEl = document.getElementById('latest-publications');
    const countsEl = document.getElementById('speaking-counts');
    const venuesEl = document.getElementById('speaking-venues');

    if (eventsEl || countsEl || venuesEl) {
      try {
        const data = await loadJSON('data/events.json');
        const today = new Date(); today.setHours(0,0,0,0);
        const events = (data.events || []).slice().sort((a,b) => a.date.localeCompare(b.date));
        const upcoming = events.filter(e => eventDateEnd(e.date) >= today);

        if (eventsEl) {
          if (!upcoming.length) {
            eventsEl.innerHTML = '<p class="empty-state">No upcoming public appearances currently listed.</p>';
          } else {
            eventsEl.innerHTML = upcoming.map(e => {
              const details = [e.type && e.event ? `${e.type} · ${e.event}` : (e.type || e.event), e.note, e.time, e.location]
                .filter(Boolean).map(esc);
              const inner = `<div class="event-date">${esc(e.displayDate || e.date)}</div><span class="event-title">${esc(e.title)}</span>${details.length ? `<div class="event-meta">${details.join('<br>')}</div>` : ''}`;
              return e.url ? `<a class="event-item" href="${esc(e.url)}" target="_blank" rel="noreferrer">${inner}</a>` : `<div class="event-item">${inner}</div>`;
            }).join('');
          }
        }

        if (countsEl) {
          const baseline = data.baseline || {asOf: '2026-09-19', counts: {local:0,national:0,international:0}};
          const counts = {
            local: Number(baseline.counts?.local || 0),
            national: Number(baseline.counts?.national || 0),
            international: Number(baseline.counts?.international || 0)
          };
          for (const e of events) {
            if (!e.scope || !(e.scope in counts)) continue;
            if (e.date > baseline.asOf && eventDateEnd(e.date) < today) counts[e.scope] += 1;
          }
          const labels = {local:'Local', national:'National', international:'International'};
          countsEl.innerHTML = ['local','national','international'].map(k => `<div class="speaking-stat"><strong>${counts[k]}</strong><span>${labels[k]}</span></div>`).join('');
        }

        if (venuesEl) {
          const venues = data.selectedVenues || [];
          venuesEl.textContent = venues.length ? `Selected venues: ${venues.join(' · ')}` : '';
        }
      } catch (_) {
        if (eventsEl) eventsEl.innerHTML = '<p class="empty-state">Upcoming appearances could not be loaded.</p>';
      }
    }

    if (pubsEl) {
      try {
        const data = await loadJSON('data/publications.json');
        const pubs = (data.publications || []).slice().sort((a,b) => (b.year||0)-(a.year||0) || String(a.title).localeCompare(String(b.title))).slice(0,6);
        pubsEl.innerHTML = pubs.map(p => {
          const url = urlForPub(p);
          const inner = `<div class="latest-meta">${esc(p.year || '')}</div><span class="latest-title">${esc(p.title)}</span>`;
          return url ? `<a class="latest-item" href="${esc(url)}" target="_blank" rel="noreferrer">${inner}</a>` : `<div class="latest-item">${inner}</div>`;
        }).join('');
      } catch (_) {
        pubsEl.innerHTML = '<p class="empty-state">See the full publications index.</p>';
      }
    }
  }

  async function renderPublications() {
    const list = document.getElementById('all-publications');
    if (!list) return;
    const search = document.getElementById('pub-search');
    const count = document.getElementById('pub-count');
    const filters = document.getElementById('topic-filters');
    try {
      const [data, topicData] = await Promise.all([loadJSON('data/publications.json'), loadJSON('data/publication-topics.json')]);
      const labels = topicData.labels || {};
      const overrides = topicData.overrides || {};
      const titleOverrides = topicData.titleOverrides || {};
      const normTitle = s => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
      let activeTopic = new URLSearchParams(location.search).get('topic') || 'all';
      const pubs = (data.publications || []).map(p => {
        const doiKey = (p.doi || '').toLowerCase();
        const topics = overrides[doiKey] || titleOverrides[normTitle(p.title)] || [];
        return {...p, topics};
      });

      filters.innerHTML = [`<button class="topic-filter" data-topic="all">All</button>`]
        .concat(Object.entries(labels).map(([k,v]) => `<button class="topic-filter" data-topic="${esc(k)}">${esc(v)}</button>`)).join('');

      function render() {
        const q = (search.value || '').trim().toLowerCase();
        const shown = pubs.filter(p => {
          const topicOK = activeTopic === 'all' || (p.topics || []).includes(activeTopic);
          const hay = `${p.title || ''} ${p.citation || ''} ${p.year || ''}`.toLowerCase();
          return topicOK && (!q || hay.includes(q));
        }).sort((a,b) => (b.year||0)-(a.year||0) || String(a.title).localeCompare(String(b.title)));
        count.textContent = `${shown.length} publication${shown.length === 1 ? '' : 's'}`;
        document.querySelectorAll('.topic-filter').forEach(b => b.classList.toggle('active', b.dataset.topic === activeTopic));
        list.innerHTML = shown.length ? shown.map(p => {
          const url = urlForPub(p);
          const tags = (p.topics || []).filter(t => labels[t]).map(t => `<span class="pub-tag">${esc(labels[t])}</span>`).join('');
          const title = url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(p.title)} ↗</a>` : esc(p.title);
          return `<article class="pub-item"><div class="pub-year">${esc(p.year || '')}</div><div><h3 class="pub-title">${title}</h3><p class="pub-citation">${esc(p.citation || '')}</p>${tags ? `<div class="pub-tags">${tags}</div>` : ''}</div></article>`;
        }).join('') : '<p class="empty-state">No publications match this filter.</p>';
      }
      filters.addEventListener('click', e => {
        const b = e.target.closest('[data-topic]'); if (!b) return;
        activeTopic = b.dataset.topic;
        const u = new URL(location.href);
        if (activeTopic === 'all') u.searchParams.delete('topic'); else u.searchParams.set('topic', activeTopic);
        history.replaceState({},'',u);
        render();
      });
      search.addEventListener('input', render);
      render();
    } catch (_) {
      list.innerHTML = '<p class="empty-state">The publication index could not be loaded.</p>';
    }
  }

  renderHomepage();
  renderPublications();
})();
