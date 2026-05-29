/* EIP-2780 dashboard charts. Reads window.DASHBOARD_DATA (embedded in data.js,
   loaded before this file). No fetch, no chart-builder abstraction: three explicit
   Plotly.newPlot calls. */
(function () {
  "use strict";

  var PLOT_CONFIG = { responsive: true, displaylogo: false };
  var PALETTE = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3",
    "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3"
  ];

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
        line: { color: "#d62728", width: 1.5, dash: "dash" }
      }],
      annotations: [{
        xref: "paper", x: 1, xanchor: "right",
        yref: "y", y: value, yanchor: "bottom",
        text: label,
        showarrow: false,
        font: { color: "#d62728", size: 11 }
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
        x: cases,
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

    var layout = Object.assign({
      barmode: "group",
      margin: { t: 10, r: 20, b: 70, l: 70 },
      xaxis: { title: "Case ID", automargin: true },
      yaxis: { title: "Proposed gas (rounded)" },
      legend: { orientation: "h", y: -0.25 }
    }, referenceLine(currentGas, "Current (" + currentGas.toLocaleString() + ")"));

    Plotly.newPlot(div, traces, layout, PLOT_CONFIG);
  }

  // Grouped bar chart of R^2 per (client, case) from results, x = case_id, grouped by client.
  function plotRsquared(divId) {
    var div = document.getElementById(divId);
    if (!div || !window.DASHBOARD_DATA) return;

    var rows = window.DASHBOARD_DATA.results || [];
    if (!rows.length) { div.innerHTML = "<p class='no-data'>No data.</p>"; return; }

    var cases = uniqueSorted(rows, "case_id");
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
        x: cases,
        y: y,
        marker: { color: PALETTE[i % PALETTE.length] }
      };
    });

    var layout = Object.assign({
      barmode: "group",
      margin: { t: 10, r: 20, b: 70, l: 60 },
      xaxis: { title: "Case ID", automargin: true },
      yaxis: { title: "R²", range: [0, 1.05] },
      legend: { orientation: "h", y: -0.25 }
    }, referenceLine(0.5, "R² = 0.5"));

    Plotly.newPlot(div, traces, layout, PLOT_CONFIG);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!window.DASHBOARD_DATA) return;
    plotNewGas("chart-tx-base", "TX_BASE", 21000);
    plotNewGas("chart-value-gas", "VALUE_GAS", 9000);
    plotRsquared("chart-rsquared");
  });
})();
