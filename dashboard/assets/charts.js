function isNumeric(value) {
  return value !== null && value !== '' && Number.isFinite(Number(value));
}

function normalizeChartSpec(payload) {
  return payload.dashboard_spec || payload;
}

function renderBars(container, spec) {
  const svgWidth = 720;
  const svgHeight = 320;
  const padding = 40;
  const chart = spec.chart || {};
  const xIndex = spec.columns.indexOf(chart.x);
  const yIndex = spec.columns.indexOf(chart.y);
  if (xIndex < 0 || yIndex < 0) {
    container.innerHTML = '<p>No compatible chart columns were returned.</p>';
    return;
  }
  const values = spec.rows.map((row) => Number(row[yIndex]));
  const labels = spec.rows.map((row) => String(row[xIndex]));
  const max = Math.max(...values, 1);
  const barWidth = Math.max(24, (svgWidth - padding * 2) / Math.max(values.length, 1) - 12);
  const gap = 12;

  const bars = values.map((value, index) => {
    const x = padding + index * (barWidth + gap);
    const height = ((svgHeight - padding * 2) * value) / max;
    const y = svgHeight - padding - height;
    return `
      <g>
        <rect x="${x}" y="${y}" width="${barWidth}" height="${height}" rx="6" fill="#2563eb"></rect>
        <text x="${x + barWidth / 2}" y="${svgHeight - 12}" text-anchor="middle" font-size="11">${labels[index]}</text>
        <text x="${x + barWidth / 2}" y="${Math.max(y - 6, 12)}" text-anchor="middle" font-size="11">${value}</text>
      </g>`;
  }).join('');

  container.innerHTML = `
    <svg viewBox="0 0 ${svgWidth} ${svgHeight}" class="chart-svg" role="img" aria-label="${chart.title || 'Bar chart'}">
      <line x1="${padding}" y1="${svgHeight - padding}" x2="${svgWidth - padding}" y2="${svgHeight - padding}" stroke="#94a3b8"></line>
      <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${svgHeight - padding}" stroke="#94a3b8"></line>
      ${bars}
    </svg>`;
}

function renderMetric(container, spec) {
  const chart = spec.chart || {};
  const metricIndex = spec.columns.indexOf(chart.value);
  const metricValue = metricIndex >= 0 && spec.rows[0] ? spec.rows[0][metricIndex] : 'n/a';
  container.innerHTML = `
    <div class="metric-card">
      <span>${chart.title || 'Metric'}</span>
      <strong>${metricValue}</strong>
    </div>`;
}

export function renderAgentChart(container, payload) {
  const spec = normalizeChartSpec(payload);
  container.innerHTML = '';
  if (!spec.rows || !spec.rows.length) {
    container.innerHTML = '<p>No rows available for charting.</p>';
    return;
  }
  const chartType = (spec.chart && spec.chart.type) || 'table';
  if (chartType === 'bar') {
    renderBars(container, spec);
    return;
  }
  if (chartType === 'metric') {
    renderMetric(container, spec);
    return;
  }
  container.innerHTML = '<p>Rendered the latest response as a table below.</p>';
}

window.renderAgentChart = renderAgentChart;
