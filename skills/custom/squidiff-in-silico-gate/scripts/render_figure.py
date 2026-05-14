#!/usr/bin/env python
"""
render_figure.py — produce the final HTML figure from metrics JSON.

Reads metrics from run_inference.py (Mode 1), synthetic_fallback.py (Mode 0),
or pair_with_morpheus.py (Mode 3), and renders a single self-contained HTML
file with the Nature-Methods-style multi-panel figure plus verdict card.

Usage:
  python render_figure.py \
    --metrics /tmp/metrics.json \
    --cross-verdict /tmp/cross_verdict.json  # optional, for Mode 3
    --out /mnt/user-data/outputs/squidiff-gate-<slug>.html
"""
from __future__ import annotations
import argparse
import json
import datetime
from pathlib import Path


def load(path):
    if path and Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return None


def render_html(metrics: dict, cross: dict | None) -> str:
    """Render the full HTML figure."""
    mode = metrics.get("mode", "unknown")
    op = metrics.get("operation", "unknown")
    hypothesis = metrics.get("hypothesis", "(unspecified)")
    system = metrics.get("system", "generic")
    seed = metrics.get("seed", "unspecified")
    ck = metrics.get("checkpoint", {})

    is_synthetic = mode.startswith("0_")
    mode_badge = {
        "1_real_inference": "Mode 1 · Real inference",
        "3_cross_verdict":  "Mode 3 · Cross-verdict",
        "0_synthetic_proxy": "Mode 0 · Synthetic proxy",
    }.get(mode, mode)

    # Verdict
    if cross:
        verdict_label = cross["consolidated"]["consolidated_label"]
        verdict_class = _verdict_class(cross["consolidated"]["consolidated_verdict"])
        confidence = cross["consolidated"]["confidence"]
        rationale = cross["consolidated"]["rationale"]
        spurious = cross.get("spurious_check", {})
    else:
        # Compute Squidiff-only verdict inline (mirrors pair_with_morpheus logic)
        from_metrics = _verdict_from_metrics(metrics)
        verdict_label = from_metrics["verdict"].upper().replace("-", " ")
        verdict_class = _verdict_class(from_metrics["verdict"])
        confidence = from_metrics["confidence"]
        rationale = from_metrics["rationale"]
        spurious = {"is_spurious": None, "message": "Morphology not evaluated."}

    # Metrics for display
    pearson_r = metrics.get("pearson_r")
    r2 = metrics.get("r_squared")
    de_acc = metrics.get("directional_accuracy_top20_de")
    delta_norm = metrics.get("delta_zsem_norm")
    n_src = metrics.get("n_source")
    n_tgt = metrics.get("n_target")
    n_genes = metrics.get("n_genes")

    # Latent PCA data
    latent = metrics.get("latent_pca", {})
    pca_json = json.dumps(latent)

    # Top DE genes
    top_de = metrics.get("top_de_genes", {})
    top_de_json = json.dumps(top_de)

    # Synthetic watermark
    synthetic_watermark = ""
    if is_synthetic:
        synthetic_watermark = """
        <div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-25deg);
                    font-size: 80px; font-weight: 800; color: rgba(184, 134, 11, 0.08);
                    pointer-events: none; z-index: 1; letter-spacing: 4px;">SYNTHETIC PROXY</div>
        """

    # Spurious flag block
    spurious_block = ""
    if spurious.get("is_spurious"):
        spurious_block = f"""
        <div class="spurious-flag">
          <strong>⚠ Spurious convergence detected:</strong> {spurious['message']}
        </div>
        """
    elif spurious.get("severity") == "none" and cross:
        spurious_block = f"""
        <div class="spurious-ok">
          ✓ Cross-verdict check: {spurious.get('message','')}
        </div>
        """

    timestamp = datetime.datetime.now().isoformat(timespec='seconds')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Squidiff Gate — {hypothesis[:60]}</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<style>
:root {{
  --bg: #ffffff; --border: #e5e5e5;
  --text-primary: #1a1a1a; --text-secondary: #555555; --text-tertiary: #8a8a8a;
  --accent: #2c5282; --accent-warm: #c05621;
  --pass: #2f855a; --moderate: #b7791f; --fail: #c53030; --decouple: #6366f1;
  --font-sans: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: var(--font-sans); background: var(--bg); color: var(--text-primary);
  padding: 24px; font-size: 13px; line-height: 1.45; position: relative;
}}
.figure-header {{ max-width: 1400px; margin: 0 auto 16px; position: relative; z-index: 2; }}
.title {{ font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }}
.subtitle {{ font-size: 13px; color: var(--text-secondary); margin-top: 4px; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; font-size: 11px; color: var(--text-tertiary); }}
.meta-item strong {{ color: var(--text-secondary); font-weight: 600; }}
.mode-badge {{
  display: inline-block; padding: 2px 9px; border-radius: 3px;
  background: var(--accent); color: white;
  font-size: 10px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
}}
.mode-badge.synthetic {{ background: var(--moderate); }}
.disclaimer {{
  background: #fef3c7; border-left: 3px solid var(--moderate);
  padding: 10px 14px; margin-top: 12px;
  font-size: 12px; color: #78350f;
}}
.honesty {{
  background: #f0f9ff; border-left: 3px solid var(--accent);
  padding: 10px 14px; margin-top: 8px;
  font-size: 12px; color: #1e3a5f;
}}
.grid {{ display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 18px; max-width: 1400px; margin: 0 auto; position: relative; z-index: 2; }}
.panel {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 16px; }}
.panel.full {{ grid-column: span 3; }}
.panel-title {{
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 1.5px; color: var(--text-secondary);
  margin: 0 0 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border);
}}
.caption {{ font-size: 11px; color: var(--text-tertiary); margin-top: 8px; line-height: 1.45; }}
.verdict-badge {{
  display: inline-block; padding: 8px 18px; border-radius: 4px;
  font-size: 14px; font-weight: 700; letter-spacing: 2px;
  margin-bottom: 12px;
}}
.verdict-pass {{ background: #d4f4dd; color: var(--pass); }}
.verdict-moderate {{ background: #fef3c7; color: var(--moderate); }}
.verdict-fail {{ background: #fed7d7; color: var(--fail); }}
.verdict-decouple {{ background: #e0e7ff; color: var(--decouple); }}
.summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 10px 0 16px; }}
.summary-stat {{ background: #fafafa; padding: 12px; border-radius: 4px; border-left: 3px solid var(--accent); }}
.summary-stat-label {{ font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 1px; }}
.summary-stat-value {{ font-size: 20px; font-weight: 700; font-family: var(--font-mono); margin-top: 4px; }}
.verdict-rationale, .verdict-next {{ margin-top: 10px; font-size: 13px; }}
.verdict-disclaimer {{ margin-top: 12px; font-size: 11px; color: var(--text-tertiary); font-style: italic; border-top: 1px solid var(--border); padding-top: 10px; }}
.spurious-flag {{ background: #fed7d7; border: 1px solid var(--fail); padding: 12px; border-radius: 4px; margin: 12px 0; color: #742a2a; }}
.spurious-ok {{ background: #d4f4dd; border: 1px solid var(--pass); padding: 8px 12px; border-radius: 4px; margin: 8px 0; color: #22543d; font-size: 12px; }}
.figure-footer {{ max-width: 1400px; margin: 16px auto 0; padding-top: 12px; border-top: 1px solid var(--border); font-size: 10px; color: var(--text-tertiary); }}
</style>
</head>
<body>

{synthetic_watermark}

<header class="figure-header">
  <h1 class="title">Squidiff In-Silico Gate</h1>
  <p class="subtitle">{hypothesis}</p>
  <div class="meta">
    <span class="meta-item"><span class="mode-badge {'synthetic' if is_synthetic else ''}">{mode_badge}</span></span>
    <span class="meta-item"><strong>System:</strong> {system}</span>
    <span class="meta-item"><strong>Operation:</strong> {op}</span>
    <span class="meta-item"><strong>Checkpoint:</strong> {ck.get('tag','n/a')} (transfer: {ck.get('transfer_distance','n/a')})</span>
    <span class="meta-item"><strong>Seed:</strong> {seed} <span style="color:#2f855a;">(deterministic)</span></span>
    <span class="meta-item"><strong>Generated:</strong> {timestamp}</span>
  </div>
  <div class="honesty">
    <strong>What this gate evaluates:</strong> predicted transcriptomic response. It does <em>not</em> evaluate tissue morphology, sub-cellular geometry, or biomechanical phenotype. For those, pair with Morpheus (Mode 3) or commission wet validation.
  </div>
  {"<div class='disclaimer'>⚠ Mode 0 synthetic proxy — methodology demonstration only. Confidence capped at 0.50. Escalate to Mode 1 when real data exists.</div>" if is_synthetic else ""}
</header>

<div class="grid">

  <section class="panel" style="grid-column: span 2;">
    <h2 class="panel-title">A — Latent embedding (zsem)</h2>
    <div id="plot-a" style="height: 360px;"></div>
    <p class="caption">2D projection of the semantic latent. Source state in blue, target in orange, predicted perturbed state in green. The arrow shows the learned Δzsem direction. |Δzsem| = <strong>{delta_norm if delta_norm else 'n/a'}</strong>.</p>
  </section>

  <section class="panel">
    <h2 class="panel-title">B — Quantitative metrics</h2>
    <div style="display: grid; gap: 8px;">
      <div class="summary-stat"><div class="summary-stat-label">Pearson r</div><div class="summary-stat-value">{f'{pearson_r:.3f}' if pearson_r is not None else 'n/a'}</div></div>
      <div class="summary-stat"><div class="summary-stat-label">R²</div><div class="summary-stat-value">{f'{r2:.3f}' if r2 is not None else 'n/a'}</div></div>
      <div class="summary-stat"><div class="summary-stat-label">DE direction acc.</div><div class="summary-stat-value">{f'{de_acc:.0%}' if de_acc is not None else 'n/a'}</div></div>
    </div>
    <p class="caption">Predicted vs ground-truth comparison. Pearson r on mean gene expression; directional accuracy on top-20 DE genes. {'These are from real Squidiff inference.' if not is_synthetic else 'These are from the PCA proxy — interpret as a rough triage.'}</p>
  </section>

  <section class="panel full">
    <h2 class="panel-title">C — Top differentially expressed genes</h2>
    <div id="plot-c" style="height: 200px;"></div>
    <p class="caption">Top 15 genes by |change|. Blue = predicted change, orange = ground-truth change. Direction agreement is what drives the directional accuracy score in panel B.</p>
  </section>

  <section class="panel full">
    <h2 class="panel-title">Verdict</h2>

    <div class="verdict-badge {verdict_class}">{verdict_label}</div>

    {spurious_block}

    <div class="summary-grid">
      <div class="summary-stat">
        <div class="summary-stat-label">Confidence</div>
        <div class="summary-stat-value">{confidence:.2f}</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-label">Mode</div>
        <div class="summary-stat-value" style="font-size:14px;">{mode}</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-label">N cells (source)</div>
        <div class="summary-stat-value">{n_src or 'n/a'}</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-label">N genes</div>
        <div class="summary-stat-value">{n_genes or 'n/a'}</div>
      </div>
    </div>

    <div class="verdict-rationale"><strong>Rationale:</strong> {rationale}</div>

    <div class="verdict-disclaimer">
      {'<strong>Mode 0 disclaimer:</strong> PCA proxy, not real Squidiff. Use only for early triage.' if is_synthetic else '<strong>Mode 1/3 disclaimer:</strong> Squidiff predicts transcriptomic response, not morphology. For morphological hypotheses pair with Morpheus.'}
      Methodology per He et al., Nat Methods 2026, doi:10.1038/s41592-025-02877-y.
    </div>
  </section>

</div>

<footer class="figure-footer">
  Squidiff In-Silico Gate v2.0 · Witt × Organogenesis · Generated {timestamp}
</footer>

<script>
const latentData = {pca_json};
const topDEData = {top_de_json};

// =========================================================================
// Panel A — Latent embedding
// =========================================================================
(function() {{
  const el = document.getElementById('plot-a');
  if (!latentData || Object.keys(latentData).length === 0) {{
    el.innerHTML = '<p style="color:#999; padding:20px;">No latent data available.</p>';
    return;
  }}
  const width = 700, height = 360;
  const margin = {{ top: 20, right: 20, bottom: 40, left: 50 }};
  const svg = d3.select(el).append('svg')
    .attr('viewBox', `0 0 ${{width}} ${{height}}`)
    .attr('width', '100%').attr('height', height);

  // Collect points from source/target/predicted
  const groups = [];
  if (latentData.source) groups.push({{name: 'source', points: latentData.source, color: '#2c5282'}});
  if (latentData.target) groups.push({{name: 'target', points: latentData.target, color: '#c05621'}});
  if (latentData.predicted) groups.push({{name: 'predicted', points: latentData.predicted, color: '#2f855a'}});
  if (latentData.coords) groups.push({{name: 'all', points: latentData.coords, color: '#888'}});

  if (!groups.length) {{
    el.innerHTML = '<p style="color:#999;">No points to plot.</p>';
    return;
  }}

  const allX = groups.flatMap(g => g.points.map(p => p[0]));
  const allY = groups.flatMap(g => g.points.map(p => p[1]));
  const x = d3.scaleLinear().domain(d3.extent(allX)).nice().range([margin.left, width - margin.right]);
  const y = d3.scaleLinear().domain(d3.extent(allY)).nice().range([height - margin.bottom, margin.top]);

  svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
    .call(d3.axisBottom(x).ticks(5).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px').style('font-family', 'var(--font-mono)'));
  svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
    .call(d3.axisLeft(y).ticks(5).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '10px').style('font-family', 'var(--font-mono)'));

  svg.append('text').attr('x', width/2).attr('y', height - 8).attr('text-anchor', 'middle')
    .style('font-size', '11px').text('PC1 (zsem dim 1)');
  svg.append('text').attr('x', -height/2).attr('y', 14).attr('text-anchor', 'middle').attr('transform', 'rotate(-90)')
    .style('font-size', '11px').text('PC2 (zsem dim 2)');

  groups.forEach(g => {{
    svg.append('g').selectAll('circle').data(g.points).enter().append('circle')
      .attr('cx', d => x(d[0])).attr('cy', d => y(d[1]))
      .attr('r', 2).attr('fill', g.color).attr('opacity', 0.4);
  }});

  // Legend
  const legend = svg.append('g').attr('transform', `translate(${{margin.left + 10}}, ${{margin.top}})`);
  groups.forEach((g, i) => {{
    legend.append('circle').attr('cx', 0).attr('cy', i * 16).attr('r', 4).attr('fill', g.color);
    legend.append('text').attr('x', 9).attr('y', i*16 + 3).style('font-size', '11px').text(g.name);
  }});
}})();

// =========================================================================
// Panel C — Top DE genes
// =========================================================================
(function() {{
  const el = document.getElementById('plot-c');
  if (!topDEData || !topDEData.names || !topDEData.names.length) {{
    el.innerHTML = '<p style="color:#999; padding:8px;">No DE gene data available for this operation.</p>';
    return;
  }}
  const width = 1300, height = 200;
  const margin = {{top: 16, right: 20, bottom: 50, left: 50}};
  const svg = d3.select(el).append('svg')
    .attr('viewBox', `0 0 ${{width}} ${{height}}`)
    .attr('width', '100%').attr('height', height);

  const names = topDEData.names;
  const trueC = topDEData.true_change || [];
  const predC = topDEData.predicted_change || [];

  const x0 = d3.scaleBand().domain(names).range([margin.left, width - margin.right]).padding(0.2);
  const x1 = d3.scaleBand().domain(['predicted','true']).range([0, x0.bandwidth()]).padding(0.1);
  const all = trueC.concat(predC);
  const y = d3.scaleLinear().domain([d3.min(all)*1.1 || -1, d3.max(all)*1.1 || 1]).nice()
    .range([height - margin.bottom, margin.top]);

  svg.append('g').attr('transform', `translate(0,${{y(0)}})`)
    .call(d3.axisBottom(x0).tickSize(3))
    .call(g => g.selectAll('text').style('font-size', '9px').style('font-family', 'var(--font-mono)').attr('transform', 'rotate(-30)').attr('text-anchor', 'end'));
  svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
    .call(d3.axisLeft(y).ticks(4).tickSize(3));

  svg.append('g').selectAll('g').data(names).enter().append('g')
    .attr('transform', d => `translate(${{x0(d)}},0)`)
    .each(function(d, i) {{
      const g = d3.select(this);
      g.append('rect').attr('x', x1('predicted'))
        .attr('y', d => Math.min(y(0), y(predC[i])))
        .attr('width', x1.bandwidth())
        .attr('height', Math.abs(y(predC[i]) - y(0)))
        .attr('fill', '#2c5282');
      g.append('rect').attr('x', x1('true'))
        .attr('y', d => Math.min(y(0), y(trueC[i])))
        .attr('width', x1.bandwidth())
        .attr('height', Math.abs(y(trueC[i]) - y(0)))
        .attr('fill', '#c05621');
    }});
}})();
</script>
</body>
</html>
"""
    return html


def _verdict_class(v: str) -> str:
    return {
        "pass": "verdict-pass",
        "moderate": "verdict-moderate",
        "fail": "verdict-fail",
        "pass-decouple": "verdict-decouple",
    }.get(v, "verdict-moderate")


def _verdict_from_metrics(metrics: dict) -> dict:
    """Inline copy of pair_with_morpheus.squidiff_verdict_from_metrics."""
    op = metrics.get("operation", "unknown")
    mode = metrics.get("mode", "unknown")
    is_synthetic = mode.startswith("0_")
    if op == "addition":
        r = metrics.get("pearson_r", 0.0) or 0.0
        d = metrics.get("directional_accuracy_top20_de", 0.0) or 0.0
        if r >= 0.80 and d >= 0.75: v, c = "pass", 0.80
        elif r >= 0.55 or d >= 0.50: v, c = "moderate", 0.60
        else: v, c = "fail", 0.70
        rat = f"Pearson r={r:.3f}, directional accuracy={d:.1%}"
    else:
        v, c, rat = "moderate", 0.55, f"Operation {op}: default conservative"
    distance = metrics.get("checkpoint", {}).get("transfer_distance", "unknown")
    if distance == "far":
        v = {"pass": "moderate", "moderate": "fail"}.get(v, v)
        c *= 0.75
        rat += "; FAR transfer distance penalty"
    elif distance == "mid":
        c *= 0.90
    if is_synthetic:
        c = min(c, 0.50)
        rat += "; Mode 0 synthetic"
    return {"verdict": v, "confidence": round(c, 2), "rationale": rat}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--cross-verdict", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    metrics = load(args.metrics)
    if metrics is None:
        print(f"[render_figure] ERROR: metrics file not found: {args.metrics}", file=sys.stderr)
        sys.exit(1)
    cross = load(args.cross_verdict)

    html = render_html(metrics, cross)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"[render_figure] Wrote {args.out}")


if __name__ == "__main__":
    import sys
    main()
