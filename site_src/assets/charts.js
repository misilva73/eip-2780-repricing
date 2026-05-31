/* EIP-2780 dashboard charts. Reads window.DASHBOARD_DATA (embedded in data.js,
   loaded before this file). No fetch, no chart-builder abstraction: three explicit
   Plotly.newPlot calls. */
(function () {
  "use strict";

  var PLOT_CONFIG = { responsive: true, displaylogo: false, displayModeBar: "hover" };

  // Human-readable axis labels for the raw case_ids. Keep in sync with CASE_LABELS
  // in scripts/build_site.py. case_id stays the lookup key; these are display-only.
  var CASE_LABELS = {
    diff_to_contract: "Contract",
    diff_to_existent: "EOA",
    diff_to_nonexistent: "Non-existent",
    diff_to_unique_code_jumpdest_contract: "Contract (unique code)"
  };
  function caseLabel(caseId) {
    return CASE_LABELS[caseId] || caseId;
  }
  var PALETTE = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3",
    "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3"
  ];

  var DARK = window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  var INK = DARK ? "#a8b3bf" : "#52606d";
  var GRID = DARK ? "#2a313a" : "#e1e5ea";
  var REF = DARK ? "#ff7b9c" : "#d62728";

  // Shared layout theme so charts inherit the page's typography and palette.
  function theme(extra) {
    return Object.assign({
      font: { family: "Inter, -apple-system, Segoe UI, Roboto, sans-serif",
              size: 12, color: INK },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      hovermode: "closest",
      bargap: 0.25,
      bargroupgap: 0.08,
      xaxis: { gridcolor: GRID, zerolinecolor: GRID, linecolor: GRID },
      yaxis: { gridcolor: GRID, zerolinecolor: GRID, linecolor: GRID }
    }, extra);
  }

  function uniqueSorted(rows, key) {
    var seen = {};
    var out = [];
    rows.forEach(function (r) {
      var v = r[key];
      if (v !== undefined && v !== null && !seen[v]) {
        seen[v] = true;
        out.push(v);
      }
    });
    out.sort();
    return out;
  }

  // Build a horizontal reference line + label across the whole x-range.
  function referenceLine(value, label) {
    return {
      shapes: [{
        type: "line",
        xref: "paper", x0: 0, x1: 1,
        yref: "y", y0: value, y1: value,
        line: { color: REF, width: 1.5, dash: "dash" }
      }],
      annotations: [{
        xref: "paper", x: 1, xanchor: "right",
        yref: "y", y: value, yanchor: "bottom",
        text: label,
        showarrow: false,
        font: { color: REF, size: 11 }
      }]
    };
  }

  // Grouped bar chart of new_gas_rounded for one param, x = case_id, grouped by client.
  function plotNewGas(divId, param, currentGas) {
    var div = document.getElementById(divId);
    if (!div || !window.DASHBOARD_DATA) return;

    var rows = (window.DASHBOARD_DATA.new_gas || []).filter(function (r) {
      return r.param === param;
    });
    if (!rows.length) { div.innerHTML = "<p class='no-data'>No data.</p>"; return; }

    var cases = uniqueSorted(rows, "case_id");
    var caseTicks = cases.map(caseLabel);
    var clients = uniqueSorted(rows, "client_name");

    var traces = clients.map(function (client, i) {
      var y = [], errHigh = [], errLow = [];
      cases.forEach(function (caseId) {
        var row = rows.find(function (r) {
          return r.client_name === client && r.case_id === caseId;
        });
        var val = row && row.new_gas_rounded != null ? row.new_gas_rounded : null;
        y.push(val);
        if (val == null) { errHigh.push(0); errLow.push(0); return; }
        var hi = row.new_gas_conf_int_high;
        var lo = row.new_gas_conf_int_low;
        errHigh.push(hi != null ? Math.max(hi - val, 0) : 0);
        errLow.push(lo != null ? Math.max(val - lo, 0) : 0);
      });
      return {
        type: "bar",
        name: client,
        x: caseTicks,
        y: y,
        marker: { color: PALETTE[i % PALETTE.length] },
        error_y: {
          type: "data",
          symmetric: false,
          array: errHigh,
          arrayminus: errLow,
          color: "#333",
          thickness: 1,
          width: 3
        }
      };
    });

    var layout = theme({
      barmode: "group",
      margin: { t: 10, r: 20, b: 70, l: 70 },
      legend: { orientation: "h", y: -0.25 }
    });
    Object.assign(layout.xaxis, { title: "Case", automargin: true });
    Object.assign(layout.yaxis, { title: "Proposed gas (rounded)" });
    Object.assign(layout, referenceLine(currentGas, "Current (" + currentGas.toLocaleString() + ")"));

    Plotly.newPlot(div, traces, layout, PLOT_CONFIG);
  }

  // Grouped bar chart of R^2 per (client, case) from results, x = case_id, grouped by client.
  function plotRsquared(divId) {
    var div = document.getElementById(divId);
    if (!div || !window.DASHBOARD_DATA) return;

    var rows = window.DASHBOARD_DATA.results || [];
    if (!rows.length) { div.innerHTML = "<p class='no-data'>No data.</p>"; return; }

    var cases = uniqueSorted(rows, "case_id");
    var caseTicks = cases.map(caseLabel);
    var clients = uniqueSorted(rows, "client_name");

    var traces = clients.map(function (client, i) {
      var y = cases.map(function (caseId) {
        var row = rows.find(function (r) {
          return r.client_name === client && r.case_id === caseId;
        });
        return row && row.rsquared != null ? row.rsquared : null;
      });
      return {
        type: "bar",
        name: client,
        x: caseTicks,
        y: y,
        marker: { color: PALETTE[i % PALETTE.length] }
      };
    });

    var layout = theme({
      barmode: "group",
      margin: { t: 10, r: 20, b: 70, l: 60 },
      legend: { orientation: "h", y: -0.25 }
    });
    Object.assign(layout.xaxis, { title: "Case", automargin: true });
    Object.assign(layout.yaxis, { title: "R²", range: [0, 1.05] });
    Object.assign(layout, referenceLine(0.5, "R² = 0.5"));

    Plotly.newPlot(div, traces, layout, PLOT_CONFIG);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!window.DASHBOARD_DATA) return;
    plotNewGas("chart-tx-base", "TX_BASE", 21000);
    plotNewGas("chart-value-gas", "VALUE_GAS", 9000);
    plotRsquared("chart-rsquared");
  });
})();
