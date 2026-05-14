# Visualization Patterns — Squidiff Gate Figure

This file contains the HTML, CSS, and JS patterns for producing the multi-panel Nature-style figure. Use these patterns directly — they encode the aesthetic and the plotting conventions the gate requires.

## Table of Contents
1. Aesthetic and design tokens
2. Page skeleton
3. Panel A — Latent embedding (PCA scatter with Δzsem arrows)
4. Panel B — Ground-truth vs predicted scatter
5. Panel C — DE gene heatmap
6. Panel D — Marker dot plot
7. Panel E — Pseudotime / trajectory density
8. Verdict card
9. Lightweight PCA in JavaScript
10. Putting it all together

---

## 1. Aesthetic and Design Tokens

**Design language:** Nature Methods supplementary figure. Clean, restrained, scientific. White background (not dark — this is *not* the Morpheus aesthetic). Print-readable at 100% zoom. Single-page A4-ish layout with all panels visible without scrolling on a 1080p screen.

```css
:root {
  --bg: #ffffff;
  --panel-bg: #ffffff;
  --border: #e5e5e5;
  --text-primary: #1a1a1a;
  --text-secondary: #555555;
  --text-tertiary: #8a8a8a;
  --accent: #2c5282;        /* desaturated blue, paper-like */
  --accent-warm: #c05621;   /* desaturated orange for contrast */

  /* Paper palette — used for cell types, conditions, time */
  --color-1: #4A6FA5;  /* iPSC / control / start */
  --color-2: #D4724E;  /* mesoderm / perturbed / mid */
  --color-3: #5A9B6B;  /* endothelial */
  --color-4: #9B5A8A;  /* mural / fibroblast */
  --color-5: #C4A86B;  /* late stage */
  --color-6: #B44D4D;  /* podocyte / extreme state */

  /* Verdict colors */
  --pass: #2f855a;
  --moderate: #b7791f;
  --fail: #c53030;

  --font-sans: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
}

body {
  font-family: var(--font-sans);
  background: var(--bg);
  color: var(--text-primary);
  margin: 0;
  padding: 24px;
  font-size: 13px;
  line-height: 1.4;
}
```

Typography rules:
- Panel titles: 13px, weight 600, uppercase, letter-spacing 1px
- Axis labels: 11px, weight 500
- Tick labels: 10px, weight 400, mono font
- Body text: 13px, weight 400
- Verdict text: 14px, weight 600

---

## 2. Page Skeleton

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Squidiff Gate — [HYPOTHESIS SLUG]</title>
<style>/* tokens from section 1 */</style>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
</head>
<body>

<header class="figure-header">
  <h1 class="title">Squidiff In-Silico Gate</h1>
  <div class="meta">
    <span class="meta-item"><strong>Hypothesis:</strong> [text]</span>
    <span class="meta-item"><strong>Operation:</strong> [interpolation / addition / two-gene / drug / drug-adapter]</span>
    <span class="meta-item"><strong>Mode:</strong> [A — conceptual / B — data-driven]</span>
    <span class="meta-item"><strong>Generated:</strong> [ISO timestamp]</span>
  </div>
  <div class="disclaimer">
    ⚠ This figure is produced by a <strong>methodology proxy</strong>, not a trained Squidiff model. PCA substitutes for the semantic encoder. Treat the verdict as a triage signal, not a research conclusion. See verdict card for next-step recommendation.
  </div>
</header>

<div class="grid">
  <section class="panel" id="panel-a"><h2 class="panel-title">A — Latent embedding</h2><div class="plot" id="plot-a"></div><p class="caption">[text]</p></section>
  <section class="panel" id="panel-b"><h2 class="panel-title">B — Predicted vs ground-truth</h2><div class="plot" id="plot-b"></div><p class="caption">[text]</p></section>
  <section class="panel" id="panel-c"><h2 class="panel-title">C — DE gene heatmap</h2><div class="plot" id="plot-c"></div><p class="caption">[text]</p></section>
  <section class="panel" id="panel-d"><h2 class="panel-title">D — Marker dot plot</h2><div class="plot" id="plot-d"></div><p class="caption">[text]</p></section>
  <section class="panel" id="panel-e"><h2 class="panel-title">E — Trajectory density</h2><div class="plot" id="plot-e"></div><p class="caption">[text]</p></section>
  <section class="panel" id="panel-verdict"><h2 class="panel-title">Verdict</h2><div class="verdict-content"></div></section>
</div>

<footer class="figure-footer">
  Squidiff methodology per He et al., <em>Nature Methods</em> 2026 (doi:10.1038/s41592-025-02877-y). In-chat proxy implementation. Witt × Organogenesis project.
</footer>

<script>/* PCA + panel drawing code */</script>
</body>
</html>
```

Grid layout:

```css
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: auto auto;
  gap: 20px;
  max-width: 1400px;
  margin: 24px auto;
}
#panel-verdict { grid-column: span 3; }

.panel {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 18px;
}
.panel-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.caption {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 8px;
  line-height: 1.4;
}
.disclaimer {
  background: #fef3c7;
  border-left: 3px solid var(--moderate);
  padding: 10px 14px;
  margin-top: 12px;
  font-size: 12px;
  color: #78350f;
}
```

---

## 3. Panel A — Latent Embedding (PCA Scatter with Δzsem Arrows)

The cornerstone panel. Shows cell populations as colored points in 2D zsem space (PC1 vs PC2), with arrows representing Δzsem stimulus vectors (when applicable).

```js
function drawPanelA(svgEl, points, deltaVectors, palette) {
  // points: [{ x, y, state, label }]
  // deltaVectors: [{ from: {x,y}, to: {x,y}, label }] — empty if interpolation
  const width = svgEl.clientWidth || 320;
  const height = 260;
  const margin = { top: 10, right: 10, bottom: 30, left: 36 };

  const svg = d3.select(svgEl).append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('width', '100%').attr('height', height);

  const xExtent = d3.extent(points, p => p.x);
  const yExtent = d3.extent(points, p => p.y);

  const x = d3.scaleLinear().domain(xExtent).nice().range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain(yExtent).nice().range([height - margin.bottom, margin.top]);

  // Axes
  svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(4).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px').style('font-family', 'var(--font-mono)'))
    .call(g => g.select('.domain').attr('stroke', '#999'));
  svg.append('g').attr('transform', `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(4).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px').style('font-family', 'var(--font-mono)'))
    .call(g => g.select('.domain').attr('stroke', '#999'));

  // Axis labels
  svg.append('text').attr('x', width / 2).attr('y', height - 4)
    .attr('text-anchor', 'middle').style('font-size', '11px').text('PC1 (zsem dim 1)');
  svg.append('text').attr('x', -height / 2).attr('y', 12)
    .attr('text-anchor', 'middle').attr('transform', 'rotate(-90)')
    .style('font-size', '11px').text('PC2 (zsem dim 2)');

  // Points
  svg.append('g').selectAll('circle').data(points).enter().append('circle')
    .attr('cx', d => x(d.x))
    .attr('cy', d => y(d.y))
    .attr('r', 2.5)
    .attr('fill', d => palette[d.state] || '#888')
    .attr('opacity', 0.65)
    .attr('stroke', 'none');

  // Δzsem arrows
  if (deltaVectors && deltaVectors.length) {
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead').attr('viewBox', '0 0 10 10')
      .attr('refX', 8).attr('refY', 5)
      .attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M 0 0 L 10 5 L 0 10 Z').attr('fill', '#1a1a1a');

    deltaVectors.forEach(v => {
      svg.append('line')
        .attr('x1', x(v.from.x)).attr('y1', y(v.from.y))
        .attr('x2', x(v.to.x)).attr('y2', y(v.to.y))
        .attr('stroke', '#1a1a1a').attr('stroke-width', 1.5)
        .attr('marker-end', 'url(#arrowhead)');
      if (v.label) {
        const mx = (x(v.from.x) + x(v.to.x)) / 2;
        const my = (y(v.from.y) + y(v.to.y)) / 2;
        svg.append('text').attr('x', mx + 8).attr('y', my - 4)
          .style('font-size', '10px').style('font-family', 'var(--font-mono)').text(v.label);
      }
    });
  }

  // Legend
  const states = [...new Set(points.map(p => p.state))];
  const legend = svg.append('g').attr('transform', `translate(${width - margin.right - 80}, ${margin.top})`);
  states.forEach((s, i) => {
    legend.append('circle').attr('cx', 0).attr('cy', i * 14).attr('r', 3.5)
      .attr('fill', palette[s] || '#888');
    legend.append('text').attr('x', 8).attr('y', i * 14 + 3)
      .style('font-size', '10px').text(s);
  });
}
```

---

## 4. Panel B — Ground-Truth vs Predicted Scatter

Mode B only. Shows predicted vs real gene expression for the held-out condition. Computes and displays Pearson r and R². If Mode A, replace this panel with a density curve showing the expected post-perturbation distribution.

```js
function drawPanelB(svgEl, predicted, groundTruth) {
  // predicted, groundTruth: parallel arrays of expression values
  const width = svgEl.clientWidth || 320;
  const height = 260;
  const margin = { top: 14, right: 14, bottom: 36, left: 42 };

  const svg = d3.select(svgEl).append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height);

  const allVals = predicted.concat(groundTruth);
  const max = d3.max(allVals);
  const min = d3.min(allVals);

  const x = d3.scaleLinear().domain([min, max]).nice().range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain([min, max]).nice().range([height - margin.bottom, margin.top]);

  // Identity line
  svg.append('line')
    .attr('x1', x(min)).attr('y1', y(min))
    .attr('x2', x(max)).attr('y2', y(max))
    .attr('stroke', '#cccccc').attr('stroke-width', 1).attr('stroke-dasharray', '4,3');

  // Axes (same as panel A)
  svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(4).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px').style('font-family', 'var(--font-mono)'));
  svg.append('g').attr('transform', `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(4).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px').style('font-family', 'var(--font-mono)'));

  svg.append('text').attr('x', width / 2).attr('y', height - 4)
    .attr('text-anchor', 'middle').style('font-size', '11px').text('Predicted expression');
  svg.append('text').attr('x', -height / 2).attr('y', 14)
    .attr('text-anchor', 'middle').attr('transform', 'rotate(-90)')
    .style('font-size', '11px').text('Ground-truth expression');

  // Points
  const pairs = predicted.map((p, i) => ({ p, g: groundTruth[i] }));
  svg.append('g').selectAll('circle').data(pairs).enter().append('circle')
    .attr('cx', d => x(d.p)).attr('cy', d => y(d.g))
    .attr('r', 1.8).attr('fill', 'var(--accent)').attr('opacity', 0.5);

  // Pearson r and R²
  const r = pearsonCorrelation(predicted, groundTruth);
  const r2 = r * r;
  svg.append('text').attr('x', margin.left + 8).attr('y', margin.top + 14)
    .style('font-size', '11px').style('font-family', 'var(--font-mono)')
    .text(`r = ${r.toFixed(3)}`);
  svg.append('text').attr('x', margin.left + 8).attr('y', margin.top + 28)
    .style('font-size', '11px').style('font-family', 'var(--font-mono)')
    .text(`R² = ${r2.toFixed(3)}`);
}

function pearsonCorrelation(a, b) {
  const n = a.length;
  const ma = d3.mean(a), mb = d3.mean(b);
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) {
    const xa = a[i] - ma, xb = b[i] - mb;
    num += xa * xb;
    da += xa * xa;
    db += xb * xb;
  }
  return num / Math.sqrt(da * db);
}
```

---

## 5. Panel C — DE Gene Heatmap

Top 15 differentially expressed genes (rows) × conditions/timepoints (columns). Color = mean expression z-scored per gene.

```js
function drawPanelC(divEl, geneNames, conditions, expressionMatrix) {
  // expressionMatrix: 2D array [gene_idx][condition_idx] = mean expression
  // Z-score per gene (row-wise)
  const zScored = expressionMatrix.map(row => {
    const m = d3.mean(row), s = d3.deviation(row) || 1;
    return row.map(v => (v - m) / s);
  });

  const cellW = 28, cellH = 16;
  const labelW = 80;
  const headerH = 24;
  const width = labelW + cellW * conditions.length + 20;
  const height = headerH + cellH * geneNames.length + 12;

  const svg = d3.select(divEl).append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height);

  const color = d3.scaleLinear()
    .domain([-2, 0, 2])
    .range(['#2c5282', '#ffffff', '#c05621'])
    .clamp(true);

  // Cells
  zScored.forEach((row, gi) => {
    row.forEach((v, ci) => {
      svg.append('rect')
        .attr('x', labelW + ci * cellW)
        .attr('y', headerH + gi * cellH)
        .attr('width', cellW - 1).attr('height', cellH - 1)
        .attr('fill', color(v));
    });
  });

  // Gene labels (left)
  geneNames.forEach((g, gi) => {
    svg.append('text')
      .attr('x', labelW - 6).attr('y', headerH + gi * cellH + cellH / 2 + 3)
      .attr('text-anchor', 'end')
      .style('font-size', '10px').style('font-family', 'var(--font-mono)')
      .text(g);
  });

  // Condition headers (top)
  conditions.forEach((c, ci) => {
    svg.append('text')
      .attr('x', labelW + ci * cellW + cellW / 2).attr('y', headerH - 8)
      .attr('text-anchor', 'middle')
      .style('font-size', '10px').style('font-weight', '500')
      .text(c);
  });
}
```

---

## 6. Panel D — Marker Dot Plot

For a set of canonical markers, show: dot size = fraction of cells expressing the gene; dot color = mean expression. Use the marker sets defined in `synthetic-data.md` per system.

```js
function drawPanelD(divEl, markers, conditions, fractionMatrix, meanMatrix) {
  // fractionMatrix[marker_idx][condition_idx] = fraction in [0,1]
  // meanMatrix[marker_idx][condition_idx] = mean expression
  const cellW = 32, cellH = 22;
  const labelW = 70;
  const headerH = 26;
  const width = labelW + cellW * conditions.length + 60; // +60 for legend
  const height = headerH + cellH * markers.length + 12;

  const svg = d3.select(divEl).append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height);

  const maxMean = d3.max(meanMatrix.flat());
  const color = d3.scaleSequential(d3.interpolateBlues).domain([0, maxMean]);
  const radius = d3.scaleSqrt().domain([0, 1]).range([0, cellH / 2 - 2]);

  markers.forEach((m, mi) => {
    conditions.forEach((c, ci) => {
      const cx = labelW + ci * cellW + cellW / 2;
      const cy = headerH + mi * cellH + cellH / 2;
      svg.append('circle')
        .attr('cx', cx).attr('cy', cy)
        .attr('r', radius(fractionMatrix[mi][ci]))
        .attr('fill', color(meanMatrix[mi][ci]));
    });
    // Marker label
    svg.append('text')
      .attr('x', labelW - 6).attr('y', headerH + mi * cellH + cellH / 2 + 3)
      .attr('text-anchor', 'end')
      .style('font-size', '10px').style('font-family', 'var(--font-mono)')
      .style('font-style', 'italic').text(m);
  });

  // Condition headers
  conditions.forEach((c, ci) => {
    svg.append('text')
      .attr('x', labelW + ci * cellW + cellW / 2).attr('y', headerH - 8)
      .attr('text-anchor', 'middle').style('font-size', '10px').text(c);
  });
}
```

---

## 7. Panel E — Pseudotime / Trajectory Density

Density of cells along the inferred trajectory, with one or two marker overlays. Useful for showing the cascade through intermediate states. Use a simple kernel density estimate over the projected pseudotime axis.

```js
function drawPanelE(divEl, cells, markerSeries) {
  // cells: [{ pseudotime: 0..1, state }]
  // markerSeries: { geneName: [{ pseudotime, expression }] }
  const width = 320, height = 240;
  const margin = { top: 14, right: 60, bottom: 36, left: 42 };

  const svg = d3.select(divEl).append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height);

  const x = d3.scaleLinear().domain([0, 1]).range([margin.left, width - margin.right]);

  // Density per state (KDE)
  const states = [...new Set(cells.map(c => c.state))];
  const palette = { /* match panel A palette */ };
  const bandwidth = 0.04;
  const kernel = (u) => Math.exp(-0.5 * u * u) / Math.sqrt(2 * Math.PI);
  const xs = d3.range(0, 1.01, 0.02);

  const densities = states.map(s => {
    const ts = cells.filter(c => c.state === s).map(c => c.pseudotime);
    const dens = xs.map(t => {
      const sum = ts.reduce((acc, ti) => acc + kernel((t - ti) / bandwidth), 0);
      return { t, d: sum / (ts.length * bandwidth) };
    });
    return { state: s, dens };
  });

  const maxD = d3.max(densities.flatMap(s => s.dens.map(d => d.d)));
  const y = d3.scaleLinear().domain([0, maxD]).range([height - margin.bottom, margin.top]);

  const line = d3.line().x(d => x(d.t)).y(d => y(d.d)).curve(d3.curveBasis);

  densities.forEach(s => {
    svg.append('path').datum(s.dens)
      .attr('d', line)
      .attr('fill', 'none').attr('stroke', palette[s.state] || '#888').attr('stroke-width', 1.6);
  });

  // Axes
  svg.append('g').attr('transform', `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(x).ticks(5).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px'));
  svg.append('g').attr('transform', `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(3).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px'));

  svg.append('text').attr('x', width / 2).attr('y', height - 4)
    .attr('text-anchor', 'middle').style('font-size', '11px').text('Pseudotime');
  svg.append('text').attr('x', -height / 2).attr('y', 14)
    .attr('text-anchor', 'middle').attr('transform', 'rotate(-90)')
    .style('font-size', '11px').text('Cell density');
}
```

---

## 8. Verdict Card

The summary panel at the bottom. Three states: PASS, MODERATE, FAIL. Each carries: metrics, rationale, recommended next step, methodology-proxy disclaimer.

```html
<section class="panel" id="panel-verdict">
  <h2 class="panel-title">Gate verdict</h2>
  <div class="verdict-content">
    <div class="verdict-badge verdict-pass">PASS</div>  <!-- or verdict-moderate / verdict-fail -->
    <div class="verdict-metrics">
      <div class="metric"><span class="metric-label">Pearson r</span><span class="metric-value">0.87</span></div>
      <div class="metric"><span class="metric-label">R²</span><span class="metric-value">0.76</span></div>
      <div class="metric"><span class="metric-label">DE direction accuracy</span><span class="metric-value">78%</span></div>
      <div class="metric"><span class="metric-label">Top markers recovered</span><span class="metric-value">4 / 5</span></div>
    </div>
    <div class="verdict-rationale">
      <strong>Rationale:</strong> [2–4 sentences explaining the verdict in domain terms]
    </div>
    <div class="verdict-next">
      <strong>Recommended next step:</strong> [one concrete action — run real Squidiff / commission wet experiment / collect more data / accept and proceed]
    </div>
    <div class="verdict-disclaimer">
      Methodology proxy — PCA substitutes for the trained semantic encoder. Treat as triage signal, not research conclusion. For non-additive effects (two-gene combinations, novel drugs), the proxy under-represents synergy; escalate to trained Squidiff before acting on borderline verdicts.
    </div>
  </div>
</section>
```

```css
.verdict-badge {
  display: inline-block;
  padding: 6px 16px; border-radius: 4px;
  font-size: 14px; font-weight: 700; letter-spacing: 2px;
  margin-bottom: 12px;
}
.verdict-pass { background: #d4f4dd; color: var(--pass); }
.verdict-moderate { background: #fef3c7; color: var(--moderate); }
.verdict-fail { background: #fed7d7; color: var(--fail); }

.verdict-metrics {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin: 12px 0;
}
.metric {
  background: #fafafa; padding: 10px 12px; border-radius: 4px;
  border-left: 3px solid var(--accent);
}
.metric-label { display: block; font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 1px; }
.metric-value { display: block; font-size: 18px; font-weight: 600; font-family: var(--font-mono); margin-top: 4px; }
.verdict-rationale, .verdict-next { margin-top: 10px; font-size: 13px; }
.verdict-disclaimer { margin-top: 12px; font-size: 11px; color: var(--text-tertiary); font-style: italic; border-top: 1px solid var(--border); padding-top: 10px; }
```

---

## 9. Lightweight PCA in JavaScript

For Mode B, we need PCA without a library. Power iteration is enough for 2D visualization.

```js
function pca2d(matrix) {
  // matrix: cells × genes (Array of Arrays)
  const n = matrix.length;
  const d = matrix[0].length;
  
  // Mean-center per column (gene)
  const colMeans = new Array(d).fill(0);
  for (let i = 0; i < n; i++) for (let j = 0; j < d; j++) colMeans[j] += matrix[i][j] / n;
  const X = matrix.map(row => row.map((v, j) => v - colMeans[j]));

  // Covariance matrix (gene × gene) — for d > 200, switch to dual PCA (cells × cells)
  // For typical use: subset to top-2000 most variable genes first
  
  // Power iteration to find top 2 eigenvectors
  function powerIter(cov, dim, prev = null) {
    let v = new Array(dim).fill(0).map(() => Math.random() - 0.5);
    const norm = Math.sqrt(v.reduce((s, x) => s + x * x, 0));
    v = v.map(x => x / norm);
    for (let iter = 0; iter < 100; iter++) {
      // Av
      const Av = new Array(dim).fill(0);
      for (let i = 0; i < dim; i++) for (let j = 0; j < dim; j++) Av[i] += cov[i][j] * v[j];
      // Deflate prev component if given
      if (prev) {
        const dot = Av.reduce((s, x, i) => s + x * prev[i], 0);
        for (let i = 0; i < dim; i++) Av[i] -= dot * prev[i];
      }
      const n2 = Math.sqrt(Av.reduce((s, x) => s + x * x, 0));
      v = Av.map(x => x / n2);
    }
    return v;
  }

  // Build cov
  const cov = [];
  for (let i = 0; i < d; i++) {
    cov.push(new Array(d).fill(0));
    for (let j = 0; j < d; j++) {
      let s = 0;
      for (let k = 0; k < n; k++) s += X[k][i] * X[k][j];
      cov[i][j] = s / (n - 1);
    }
  }

  const pc1 = powerIter(cov, d);
  const pc2 = powerIter(cov, d, pc1);

  // Project
  const projected = X.map(row => [
    row.reduce((s, v, j) => s + v * pc1[j], 0),
    row.reduce((s, v, j) => s + v * pc2[j], 0),
  ]);
  return { projected, pc1, pc2, colMeans };
}
```

**Cost note:** this is O(d²) per iteration. For d > 300 genes, subsample to most-variable genes first. Top-200 variable genes is usually fine for visualization.

---

## 10. Putting It All Together

The complete update function for the figure:

```js
async function generateGate(hypothesis, mode, operation, data) {
  // 1. Get or generate latent embedding
  let latentData;
  if (mode === 'A') {
    latentData = generateSyntheticLatent(hypothesis); // see synthetic-data.md
  } else {
    const pca = pca2d(data.matrix);
    latentData = { 
      points: pca.projected.map((p, i) => ({ x: p[0], y: p[1], state: data.labels[i] })),
      deltaVectors: computeDeltaVectors(pca, data.labels, operation),
    };
  }

  // 2. Compute predicted vs ground-truth (if Mode B with held-out)
  const comparison = mode === 'B' && data.heldOut ? computeComparison(data, latentData, operation) : null;

  // 3. Identify DE genes
  const deResult = identifyDE(data || syntheticData, latentData, operation);

  // 4. Compute markers
  const markerResult = computeMarkers(getMarkerSet(hypothesis), data || syntheticData);

  // 5. Pseudotime
  const trajResult = computePseudotime(latentData, data || syntheticData);

  // 6. Verdict (see gate-criteria.md)
  const verdict = computeVerdict(comparison, deResult, markerResult, mode, operation);

  // 7. Draw all panels
  drawPanelA(document.getElementById('plot-a'), latentData.points, latentData.deltaVectors, palette);
  if (comparison) drawPanelB(document.getElementById('plot-b'), comparison.pred, comparison.gt);
  drawPanelC(document.getElementById('plot-c'), deResult.genes, deResult.conditions, deResult.matrix);
  drawPanelD(document.getElementById('plot-d'), markerResult.markers, markerResult.conditions, markerResult.fraction, markerResult.mean);
  drawPanelE(document.getElementById('plot-e'), trajResult.cells, trajResult.markers);
  renderVerdict(verdict);
}
```

For an end-to-end working example with sensible defaults, generate a synthetic pronephros differentiation hypothesis and render all six panels using the patterns above. The result should be a single HTML file under 200KB (D3 from CDN).
