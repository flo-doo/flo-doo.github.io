(() => {
  const el = document.getElementById('travel-footprint');
  if (!el) return;

  const formatCarbon = (kg) => {
    const value = Number(kg);
    if (!Number.isFinite(value)) return '--';
    return value >= 1000 ? `${(value / 1000).toFixed(1)} t` : `${Math.round(value)} kg`;
  };

  async function render() {
    try {
      const response = await fetch('data/travel-emissions-cache.json', {cache: 'no-cache'});
      if (!response.ok) throw new Error(`${response.status} travel-emissions-cache.json`);
      const data = await response.json();
      if (data.status !== 'ready') {
        el.innerHTML = '<p class="travel-footprint-note">Travel footprint estimate has not been generated yet.</p>';
        return;
      }

      const summary = data.summary || {};
      const treeCount = Number(summary.pastTreeSeedlings10yr);
      const treeText = Number.isFinite(treeCount) ? `~${Math.round(treeCount)}` : '--';
      const unestimated = Number(summary.unestimatedTrips || 0);

      el.innerHTML = `
        <div class="travel-footprint-head">Estimated talk-related travel emissions</div>
        <div class="travel-footprint-summary" aria-label="Estimated talk-related travel emissions">
          <span><strong>Past</strong> ${formatCarbon(summary.pastKgCo2e)} CO₂e</span>
          <span class="travel-footprint-separator" aria-hidden="true">·</span>
          <span><strong>Upcoming</strong> ${formatCarbon(summary.upcomingKgCo2e)} CO₂e</span>
          <span class="travel-footprint-separator" aria-hidden="true">·</span>
          <span class="travel-footprint-tree-inline"><strong>${treeText}</strong> tree seedlings grown for 10 years</span>
        </div>
        <p class="travel-footprint-sources"><a href="https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026" target="_blank" rel="noreferrer">UK Government 2026 GHG factors ↗</a> · <a href="https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator" target="_blank" rel="noreferrer">U.S. EPA equivalency ↗</a></p>
        <p class="travel-footprint-disclaimer">approximate estimates from documented talk-related travel; economy assumed unless otherwise known; does not represent offsets.${unestimated ? ` ${unestimated} documented trip${unestimated === 1 ? '' : 's'} currently lack${unestimated === 1 ? 's' : ''} an estimate.` : ''}</p>`;
    } catch (error) {
      console.error(error);
      el.innerHTML = '<p class="travel-footprint-note">Travel footprint estimate could not be loaded.</p>';
    }
  }

  render();
})();
