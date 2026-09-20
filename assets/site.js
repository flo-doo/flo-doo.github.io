(() => {
  const root = document.documentElement;
  const toggle = document.querySelector('[data-theme-toggle]');
  let speakingMap = null;
  let speakingTileLayer = null;
  let speakingMarkers = [];

  function themeText() {
    if (!toggle) return;
    toggle.textContent = root.dataset.theme === 'light' ? 'View in dark mode' : 'View in light mode';
  }

  function cssVar(name) {
    return getComputedStyle(root).getPropertyValue(name).trim();
  }

  function tileConfig() {
    // OpenStreetMap's standard tile service does not require an API key.
    return {
      url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: '&copy; OpenStreetMap contributors'
    };
  }

  function updateMapTheme() {
    if (!speakingMap || !window.L) return;
    const cfg = tileConfig();
    if (speakingTileLayer) speakingMap.removeLayer(speakingTileLayer);
    speakingTileLayer = L.tileLayer(cfg.url, {
      attribution: cfg.attribution,
      maxZoom: 18
    }).addTo(speakingMap);
    speakingTileLayer.bringToBack();

    const accent = cssVar('--accent');
    const accentStrong = cssVar('--accent-strong');
    speakingMarkers.forEach(({marker, upcoming}) => {
      marker.setStyle({
        color: upcoming ? accentStrong : accent,
        fillColor: upcoming ? accentStrong : accent,
        fillOpacity: upcoming ? 0.95 : 0.70
      });
    });
  }

  themeText();
  toggle?.addEventListener('click', () => {
    const next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('florence-doo-theme', next); } catch (_) {}
    themeText();
    updateMapTheme();
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

  function renderSpeakingMap(data, upcoming) {
    const el = document.getElementById('speaking-map');
    if (!el || !window.L) return;

    speakingMap = L.map(el, {
      zoomControl: true,
      scrollWheelZoom: false,
      worldCopyJump: true,
      minZoom: 1
    });

    const points = [];
    const seen = new Set();
    const addPoint = (lat, lng, label, scope, isUpcoming = false, title = '') => {
      if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return;
      const key = `${Number(lat).toFixed(3)},${Number(lng).toFixed(3)},${label}`;
      if (seen.has(key)) return;
      seen.add(key);
      points.push({lat: Number(lat), lng: Number(lng), label, scope, upcoming: isUpcoming, title});
    };

    (data.speakingLocations || []).forEach(p => addPoint(p.lat, p.lng, p.label, p.scope, false, ''));
    upcoming.forEach(e => addPoint(e.lat, e.lng, e.location || e.event, e.scope, true, e.title || e.event));

    speakingMarkers = points.map(p => {
      const marker = L.circleMarker([p.lat, p.lng], {
        radius: p.upcoming ? 6 : 4,
        weight: p.upcoming ? 2 : 1,
        color: cssVar(p.upcoming ? '--accent-strong' : '--accent'),
        fillColor: cssVar(p.upcoming ? '--accent-strong' : '--accent'),
        fillOpacity: p.upcoming ? 0.95 : 0.70
      }).addTo(speakingMap);
      const label = p.title ? `<strong>${esc(p.label)}</strong><br>${esc(p.title)}` : esc(p.label);
      marker.bindTooltip(label, {direction: 'top', opacity: 1});
      return {marker, upcoming: p.upcoming};
    });

    updateMapTheme();

    if (points.length) {
      const bounds = L.latLngBounds(points.map(p => [p.lat, p.lng]));
      speakingMap.fitBounds(bounds, {padding: [22, 22], maxZoom: 3});
    } else {
      speakingMap.setView([25, 0], 2);
    }

    window.setTimeout(() => speakingMap?.invalidateSize(), 80);
  }

  async function renderHomepageEvents() {
    const eventsEl = document.getElementById('upcoming-events');
    const countsEl = document.getElementById('speaking-counts');
    const mapEl = document.getElementById('speaking-map');
    if (!eventsEl && !countsEl && !mapEl) return;

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

      renderSpeakingMap(data, upcoming);
    } catch (err) {
      console.error(err);
      if (eventsEl) eventsEl.innerHTML = '<p class="empty-state">Upcoming appearances could not be loaded.</p>';
      if (mapEl) mapEl.innerHTML = '<p class="empty-state">Speaking map could not be loaded.</p>';
    }
  }

  function enablePublicationBrowser() {
    const list = document.getElementById('all-publications');
    if (!list) return;

    const search = document.getElementById('pub-search');
    const count = document.getElementById('pub-count');
    const filters = document.getElementById('topic-filters');
    const items = Array.from(list.querySelectorAll('.pub-item'));
    const filterEls = Array.from(filters?.querySelectorAll('[data-topic]') || []);
    const availableTopics = new Set(filterEls.map(el => el.dataset.topic));

    function currentTopic() {
      const requested = new URLSearchParams(location.search).get('topic') || 'all';
      return availableTopics.has(requested) ? requested : 'all';
    }

    let activeTopic = currentTopic();

    function render() {
      const q = (search?.value || '').trim().toLowerCase();
      let shown = 0;

      items.forEach(item => {
        const tags = (item.dataset.tags || '').split(',').map(x => x.trim()).filter(Boolean);
        const topicOK = activeTopic === 'all' || tags.includes(activeTopic);
        const textOK = !q || item.textContent.toLowerCase().includes(q);
        const visible = topicOK && textOK;

        item.hidden = !visible;
        item.style.display = visible ? '' : 'none';
        item.setAttribute('aria-hidden', visible ? 'false' : 'true');
        if (visible) shown += 1;
      });

      if (count) count.textContent = `${shown} publication${shown === 1 ? '' : 's'}`;
      filterEls.forEach(el => {
        const isActive = el.dataset.topic === activeTopic;
        el.classList.toggle('active', isActive);
        el.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        if (isActive) el.setAttribute('aria-current', 'true');
        else el.removeAttribute('aria-current');
      });
    }

    filters?.addEventListener('click', e => {
      const el = e.target.closest('[data-topic]');
      if (!el) return;
      e.preventDefault();
      activeTopic = el.dataset.topic || 'all';
      const u = new URL(location.href);
      if (activeTopic === 'all') u.searchParams.delete('topic');
      else u.searchParams.set('topic', activeTopic);
      history.pushState({topic: activeTopic}, '', u);
      render();
      list.scrollIntoView({block: 'start', behavior: 'smooth'});
    });

    search?.addEventListener('input', render);
    window.addEventListener('popstate', () => {
      activeTopic = currentTopic();
      render();
    });

    render();
    window.florencePublicationFilter = { render, setTopic: (topic) => { activeTopic = availableTopics.has(topic) ? topic : 'all'; render(); } };
  }

  renderHomepageEvents();
  enablePublicationBrowser();
})();
