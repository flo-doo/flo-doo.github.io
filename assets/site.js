(() => {
  const root = document.documentElement;
  const toggle = document.querySelector('[data-theme-toggle]');
  let speakingMap = null;
  let speakingMarkerLayer = null;

  function themeText() {
    if (!toggle) return;
    toggle.textContent = root.dataset.theme === 'light' ? 'View in dark mode' : 'View in light mode';
  }

  function cssVar(name) {
    return getComputedStyle(root).getPropertyValue(name).trim();
  }

  function updateMapTheme() {
    if (speakingMap) window.setTimeout(() => speakingMap.invalidateSize(), 40);
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

  // Keep the navigation available while scrolling. Measure its real height so
  // wrapped mobile navigation never obscures the section it jumps to.
  const siteHeader = document.querySelector('.site-header');
  const syncHeaderHeight = () => {
    if (!siteHeader) return;
    document.documentElement.style.setProperty('--header-h', `${Math.ceil(siteHeader.getBoundingClientRect().height)}px`);
  };
  syncHeaderHeight();
  window.addEventListener('resize', syncHeaderHeight, {passive: true});
  if (siteHeader && 'ResizeObserver' in window) {
    new ResizeObserver(syncHeaderHeight).observe(siteHeader);
  }

  // Research remains the intentional gateway to Publications: hover on desktop, tap/click on touch/keyboard.
  // Keep the menu open briefly while the pointer moves from the trigger into the submenu.
  document.querySelectorAll('.nav-dropdown').forEach(dropdown => {
    const toggleButton = dropdown.querySelector('.nav-dropdown-toggle');
    const menu = dropdown.querySelector('.nav-menu');
    if (!toggleButton || !menu) return;
    let closeTimer = null;
    const setOpen = (open) => {
      if (closeTimer) { window.clearTimeout(closeTimer); closeTimer = null; }
      dropdown.classList.toggle('is-open', open);
      toggleButton.setAttribute('aria-expanded', String(open));
    };
    const scheduleClose = () => {
      if (closeTimer) window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(() => {
        if (!dropdown.matches(':hover') && !dropdown.contains(document.activeElement)) setOpen(false);
      }, 240);
    };
    toggleButton.addEventListener('click', (event) => {
      event.preventDefault();
      setOpen(!dropdown.classList.contains('is-open'));
    });
    dropdown.addEventListener('mouseenter', () => setOpen(true));
    dropdown.addEventListener('mouseleave', scheduleClose);
    menu.addEventListener('mouseenter', () => setOpen(true));
    menu.addEventListener('mouseleave', scheduleClose);
    dropdown.addEventListener('focusin', () => setOpen(true));
    dropdown.addEventListener('focusout', scheduleClose);
  });

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

  async function renderSpeakingMap(data, upcoming) {
    const el = document.getElementById('speaking-map');
    if (!el || !window.L) return;

    if (speakingMap) {
      speakingMap.remove();
      speakingMap = null;
    }

    speakingMap = L.map(el, {
      zoomControl: true,
      scrollWheelZoom: false,
      worldCopyJump: true,
      minZoom: 1,
      maxZoom: 10,
      attributionControl: true
    });

    // AcademicPages' talk-map approach uses Leaflet with geocoded talk locations.
    // We store coordinates directly in events.json, avoiding runtime geocoding/API keys.
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(speakingMap);

    // Local Natural Earth geometry gives a graceful background if raster tiles are slow or blocked.
    try {
      const land = await loadJSON('assets/ne_land_lowres.geojson');
      L.geoJSON(land, {
        interactive: false,
        style: {
          color: cssVar('--rule'),
          weight: 0.45,
          opacity: 0.22,
          fillColor: cssVar('--muted'),
          fillOpacity: 0.025
        }
      }).addTo(speakingMap);
    } catch (_) {}

    const points = [];
    const coordinateKey = (lat, lng) => `${Number(lat).toFixed(3)},${Number(lng).toFixed(3)}`;

    // Upcoming talks are aggregated by physical location before markers are created.
    // This prevents multiple talks at the same conference/city from spiderfying apart and
    // lets the map orient visitors to conferences rather than individual talk titles.
    const upcomingByLocation = new Map();
    upcoming.forEach(e => {
      const y = Number(e.lat), x = Number(e.lng);
      if (!Number.isFinite(y) || !Number.isFinite(x)) return;
      const key = coordinateKey(y, x);
      if (!upcomingByLocation.has(key)) {
        upcomingByLocation.set(key, {
          lat: y,
          lng: x,
          location: e.conferenceLocation || e.location || '',
          scope: e.scope,
          conferences: new Map(),
          talkCount: 0
        });
      }
      const group = upcomingByLocation.get(key);
      group.talkCount += 1;
      const conference = e.conference || e.event || e.title || 'Upcoming appearance';
      const current = group.conferences.get(conference) || {name: conference, count: 0};
      current.count += 1;
      group.conferences.set(conference, current);
      if (!group.location && (e.conferenceLocation || e.location)) group.location = e.conferenceLocation || e.location;
    });

    const upcomingKeys = new Set(upcomingByLocation.keys());
    const historicalSeen = new Set();
    const historicalCountsByKey = new Map();

    (data.speakingLocations || []).forEach(p => {
      const y = Number(p.lat), x = Number(p.lng);
      if (!Number.isFinite(y) || !Number.isFinite(x)) return;
      const key = coordinateKey(y, x);
      historicalCountsByKey.set(key, Number(p.talkCount || p.count || 0) || 0);
    });

    // Keep one historical marker per city. If that same city has an upcoming appearance,
    // the upcoming marker supersedes the historical marker so the two never overlap/spiderfy.
    (data.speakingLocations || []).forEach(p => {
      const y = Number(p.lat), x = Number(p.lng);
      if (!Number.isFinite(y) || !Number.isFinite(x)) return;
      const key = coordinateKey(y, x);
      if (historicalSeen.has(key) || upcomingKeys.has(key)) return;
      historicalSeen.add(key);
      points.push({
        lat: y,
        lng: x,
        label: p.label,
        scope: p.scope,
        upcoming: false,
        conferences: [],
        talkCount: Number(p.talkCount || p.count || 0) || 0
      });
    });

    upcomingByLocation.forEach(group => {
      const key = coordinateKey(group.lat, group.lng);
      points.push({
        lat: group.lat,
        lng: group.lng,
        label: group.location,
        scope: group.scope,
        upcoming: true,
        conferences: Array.from(group.conferences.values()),
        talkCount: group.talkCount,
        priorTalkCount: historicalCountsByKey.get(key) || 0
      });
    });

    const dotIcon = (upcomingFlag, talkCount = 0) => {
      // Keep historical city markers visually quiet; counts are shown in the tooltip.
      // Upcoming locations retain a count badge when multiple talks share one city.
      const showCount = upcomingFlag && Number(talkCount) > 1;
      const size = showCount ? 22 : (upcomingFlag ? 14 : 10);
      const countText = showCount ? `<span class="speaking-dot-count">${talkCount}</span>` : '';
      return L.divIcon({
        className: 'speaking-dot-wrap',
        html: `<span class="speaking-dot${upcomingFlag ? ' speaking-dot--upcoming' : ''}${showCount ? ' speaking-dot--has-count' : ''}">${countText}</span>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2]
      });
    };

    const clusterAvailable = typeof L.markerClusterGroup === 'function';
    speakingMarkerLayer = clusterAvailable
      ? L.markerClusterGroup({
          showCoverageOnHover: false,
          spiderfyOnMaxZoom: true,
          zoomToBoundsOnClick: true,
          maxClusterRadius: 34,
          iconCreateFunction: cluster => L.divIcon({
            html: `<span class="speaking-cluster">${cluster.getChildCount()}</span>`,
            className: 'speaking-cluster-wrap',
            iconSize: [30, 30],
            iconAnchor: [15, 15]
          })
        })
      : L.layerGroup();

    points.forEach(p => {
      const marker = L.marker([p.lat, p.lng], {icon: dotIcon(p.upcoming, p.talkCount), keyboard: true});
      let body;
      if (p.upcoming && p.conferences?.length) {
        const conferenceLines = p.conferences.map(c => {
          const talkLabel = c.count === 1 ? '1 talk' : `${c.count} talks`;
          return `<strong>${esc(c.name)}</strong> <span class="map-talk-count">(${talkLabel})</span>`;
        }).join('<br>');
        const cityTalkLabel = p.talkCount === 1 ? '1 talk' : `${p.talkCount} talks`;
        const priorLabel = Number(p.priorTalkCount) > 0
          ? ` · ${p.priorTalkCount === 1 ? '1 prior talk' : `${p.priorTalkCount} prior talks`}`
          : '';
        const locationLine = p.label ? `<br><span class="map-tooltip-location">${esc(p.label)} · ${cityTalkLabel}${priorLabel}</span>` : '';
        body = `${conferenceLines}${locationLine}<br><em>Upcoming</em>`;
      } else {
        const historicalCount = p.talkCount > 0
          ? ` · ${p.talkCount === 1 ? '1 talk' : `${p.talkCount} talks`}`
          : '';
        body = `<strong>${esc(p.label)}${historicalCount}</strong>`;
      }
      marker.bindTooltip(body, {direction: 'top', opacity: 1});
      marker.bindPopup(body);
      speakingMarkerLayer.addLayer(marker);
    });
    speakingMarkerLayer.addTo(speakingMap);

    if (points.length) {
      const bounds = L.latLngBounds(points.map(p => [p.lat, p.lng]));
      speakingMap.fitBounds(bounds, {padding: [26, 26], maxZoom: 2});
    } else {
      speakingMap.setView([25, 0], 1.5);
    }

    window.setTimeout(() => speakingMap?.invalidateSize(), 180);
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

          const groups = [];
          const byName = new Map();
          upcoming.forEach(e => {
            const name = e.conference || e.event || e.title;
            if (!byName.has(name)) {
              const group = {name, url: e.conferenceUrl || '', items: []};
              byName.set(name, group);
              groups.push(group);
            }
            const group = byName.get(name);
            if (!group.url && e.conferenceUrl) group.url = e.conferenceUrl;
            group.items.push(e);
          });

          eventsEl.innerHTML = groups.map(group => {
            const items = group.items.slice().sort((a,b) => a.date.localeCompare(b.date));
            const locations = [...new Set(items.map(e => e.conferenceLocation || e.location).filter(Boolean))];
            const groupMeta = locations.map(location => `<span class="event-location-tag">${esc(location)}</span>`).join('');
            const groupName = group.url
              ? `<a class="event-conference-link" href="${esc(group.url)}" target="_blank" rel="noreferrer">${esc(group.name)} ↗</a>`
              : esc(group.name);

            const normalizeEventLabel = (value = '') => value
              .toLowerCase()
              .replace(/\b20\d{2}\b/g, '')
              .replace(/[^a-z0-9]+/g, ' ')
              .trim();
            const normalizedGroup = normalizeEventLabel(group.name);

            const sessions = items.map(e => {
              const candidateEvent = e.event || '';
              const normalizedEvent = normalizeEventLabel(candidateEvent);
              const duplicateConferenceLabel = normalizedEvent && normalizedGroup &&
                (normalizedEvent === normalizedGroup || normalizedGroup.includes(normalizedEvent) || normalizedEvent.includes(normalizedGroup));
              const eventLabel = candidateEvent && !duplicateConferenceLabel ? candidateEvent : '';
              const details = [
                e.type && eventLabel ? `${e.type} · ${eventLabel}` : (e.type || eventLabel),
                e.note,
                e.time
              ].filter(Boolean).map(esc);
              const titleMarkup = e.url
                ? `<span class="event-title">${esc(e.title)} <span class="event-title-arrow" aria-hidden="true">↗</span></span>`
                : `<span class="event-title">${esc(e.title)}</span>`;
              const inner = `<div class="event-session-date">${esc(e.displayDate || e.date)}</div>` +
                `<div class="event-session-body">${titleMarkup}` +
                (details.length ? `<div class="event-meta">${details.join('<br>')}</div>` : '') +
                `</div>`;
              return e.url
                ? `<a class="event-session" href="${esc(e.url)}" target="_blank" rel="noreferrer">${inner}</a>`
                : `<div class="event-session">${inner}</div>`;
            }).join('');

            return `<section class="event-group"><div class="event-group-head"><div class="event-conference">${groupName}</div><div class="event-group-meta">${groupMeta}</div></div><div class="event-group-sessions">${sessions}</div></section>`;
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


  function organizeTimedEditorships() {
    const current = document.getElementById('current-editorships');
    const prior = document.getElementById('prior-editorships');
    const priorBlock = document.getElementById('prior-editorships-block');
    if (!current || !prior) return;

    const roles = Array.from(document.querySelectorAll('[data-editorial-role][data-end]'));
    if (!roles.length) return;

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const currentRoles = [];
    const priorRoles = [];

    roles.forEach(role => {
      const end = new Date(`${role.dataset.end}T23:59:59`);
      const isPrior = end < today;
      const display = role.dataset.endDisplay || role.dataset.end;
      const status = role.querySelector('.editorial-status');
      if (status) status.textContent = `${isPrior ? 'ended' : 'through'} ${display}`;
      (isPrior ? priorRoles : currentRoles).push(role);
    });

    currentRoles
      .sort((a, b) => (a.dataset.end || '').localeCompare(b.dataset.end || ''))
      .forEach(role => current.appendChild(role));
    priorRoles
      .sort((a, b) => (b.dataset.end || '').localeCompare(a.dataset.end || ''))
      .forEach(role => prior.appendChild(role));

    current.hidden = current.children.length === 0;
    if (priorBlock) priorBlock.hidden = prior.children.length === 0;
  }

  organizeTimedEditorships();
  renderHomepageEvents();
  enablePublicationBrowser();
})();
