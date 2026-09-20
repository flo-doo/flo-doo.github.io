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

  async function renderHomepage() {
    const eventsEl = document.getElementById('upcoming-events');
    const pubsEl = document.getElementById('latest-publications');

    if (eventsEl) {
      try {
        const data = await loadJSON('data/events.json');
        const today = new Date(); today.setHours(0,0,0,0);
        const events = (data.events || []).filter(e => new Date(`${e.date}T23:59:59`) >= today).sort((a,b) => a.date.localeCompare(b.date)).slice(0,5);
        if (!events.length) eventsEl.innerHTML = '<p class="empty-state">No upcoming public appearances currently listed.</p>';
        else eventsEl.innerHTML = events.map(e => {
          const inner = `<div class="event-date">${esc(e.displayDate || e.date)}</div><span class="event-title">${esc(e.title)}</span><div class="event-type">${esc(e.type || '')}${e.event ? ` · ${esc(e.event)}` : ''}</div>${e.time || e.location ? `<div class="event-meta">${[e.time,e.location].filter(Boolean).map(esc).join(' · ')}</div>` : ''}`;
          return e.url ? `<a class="event-item" href="${esc(e.url)}" target="_blank" rel="noreferrer">${inner}</a>` : `<div class="event-item">${inner}</div>`;
        }).join('');
      } catch (_) {
        eventsEl.innerHTML = '<p class="empty-state">Upcoming appearances are available on the appearances page.</p>';
      }
    }

    if (pubsEl) {
      try {
        const data = await loadJSON('data/publications.json');
        const pubs = (data.publications || []).slice().sort((a,b) => (b.year||0)-(a.year||0)).slice(0,5);
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
      let activeTopic = new URLSearchParams(location.search).get('topic') || 'all';
      const pubs = (data.publications || []).map(p => {
        const key = (p.doi || '').toLowerCase();
        const override = overrides[key];
        return {...p, topics: override || p.topics || []};
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
    } catch (err) {
      list.innerHTML = '<p class="empty-state">The publication index could not be loaded.</p>';
    }
  }

  async function renderAppearances() {
    const upcomingEl = document.getElementById('upcoming-appearances');
    const pastEl = document.getElementById('past-appearances');
    if (!upcomingEl && !pastEl) return;
    const filters = document.getElementById('appearance-filters');
    const count = document.getElementById('appearance-count');
    const scopeLabels = {
      institutional: 'Institutional',
      national: 'National',
      international: 'International'
    };
    try {
      const data = await loadJSON('data/events.json');
      const today = new Date(); today.setHours(0,0,0,0);
      const events = (data.events || []).slice();
      const isFuture = e => new Date(`${e.date}T23:59:59`) >= today;
      const upcoming = events.filter(isFuture).sort((a,b) => a.date.localeCompare(b.date));
      const past = events.filter(e => !isFuture(e)).sort((a,b) => b.date.localeCompare(a.date));

      const eventHTML = e => {
        const details = [e.time, e.location, e.note].filter(Boolean).map(esc).join(' · ');
        const title = e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noreferrer">${esc(e.title)} ↗</a>` : esc(e.title);
        const scope = e.scope && scopeLabels[e.scope] ? `<span class="appearance-scope">${esc(scopeLabels[e.scope])}</span>` : '';
        return `<article class="appearance-item"><div><div class="event-date">${esc(e.displayDate || e.date)}</div><div class="appearance-type">${esc(e.type || '')}</div>${scope}</div><div><h3>${title}</h3><p>${esc(e.event || '')}${details ? ` · ${details}` : ''}</p></div></article>`;
      };

      if (upcomingEl) {
        upcomingEl.innerHTML = upcoming.length ? upcoming.map(eventHTML).join('') : '<p class="empty-state">No upcoming public appearances currently listed.</p>';
      }

      if (pastEl) {
        let activeScope = 'all';
        function renderPast() {
          const shown = activeScope === 'all' ? past : past.filter(e => e.scope === activeScope);
          if (count) count.textContent = `${shown.length} selected prior appearance${shown.length === 1 ? '' : 's'}`;
          if (filters) filters.querySelectorAll('[data-scope]').forEach(b => b.classList.toggle('active', b.dataset.scope === activeScope));
          pastEl.innerHTML = shown.length ? shown.map(eventHTML).join('') : '<p class="empty-state">No prior appearances match this filter.</p>';
        }
        filters?.addEventListener('click', e => {
          const b = e.target.closest('[data-scope]'); if (!b) return;
          activeScope = b.dataset.scope;
          renderPast();
        });
        renderPast();
      }
    } catch (_) {
      if (upcomingEl) upcomingEl.innerHTML = '<p class="empty-state">Appearances could not be loaded.</p>';
      if (pastEl) pastEl.innerHTML = '<p class="empty-state">Prior appearances could not be loaded.</p>';
    }
  }

  renderHomepage();
  renderPublications();
  renderAppearances();
})();
