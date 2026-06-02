/* Cross-run Trends page. Reads the dataset embedded as JSON in #trends-data by
   build_site.collect_trends(); Plotly (loaded by base.html) draws the charts.
   Two sections: a latest-vs-previous delta table + Δ% diverging-bar chart, and one
   line chart per param across every run. Lower = cheaper, so a negative delta (bar
   pointing left, green) is an improvement and a positive one (right, red) a rise.

   Unlike the per-(param, client) upstream page, 2780 keeps the receiver-case
   dimension: every line/row is a (client, case) pair — colour is the client, line
   style is the case. */
(function () {
  "use strict";

  var el = document.getElementById("trends-data");
  if (!el || typeof Plotly === "undefined") return;
  var DATA = JSON.parse(el.textContent);

  var RUNS = DATA.runs; // chronological (oldest → newest)
  var N = RUNS.length;
  var LABELS = RUNS.map(function (r) { return r.label; });

  // Palette + case-label map kept in sync with charts.js.
  var PALETTE = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3",
    "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3"
  ];
  var CASE_LABELS = {
    diff_to_contract: "Contract",
    diff_to_existent: "EOA",
    diff_to_nonexistent: "Non-existent",
    diff_to_unique_code_jumpdest_contract: "Contract (unique code)"
  };
  function caseLabel(c) { return CASE_LABELS[c] || c; }

  // Stable colour per client and dash per case (order-independent of filters).
  var COLOR = {};
  DATA.clients.forEach(function (c, i) { COLOR[c] = PALETTE[i % PALETTE.length]; });
  var DASHES = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"];
  var DASH = {};
  DATA.cases.forEach(function (c, i) { DASH[c] = DASHES[i % DASHES.length]; });
  // SVG stroke-dasharray equivalents of the Plotly dash names, for the shared key.
  var DASH_SVG = {
    solid: "", dash: "6,4", dot: "2,3", dashdot: "6,3,2,3",
    longdash: "10,4", longdashdot: "10,3,2,3"
  };

  var DARK = window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  var INK = DARK ? "#a8b3bf" : "#52606d";
  var GRID = DARK ? "#2a313a" : "#e1e5ea";
  var GREEN = DARK ? "#56d364" : "#0f9d58";  // cheaper / lower (improvement)
  var RED = DARK ? "#ff7b9c" : "#d6336c";    // costlier / higher (regression)
  var BIND = DARK ? "#e3b341" : "#b8860b";   // binding (worst-case) outline
  var REF = DARK ? "#ff7b9c" : "#d62728";    // reference line (current cost)

  var PLOT_CONFIG = { responsive: true, displaylogo: false, displayModeBar: "hover" };

  // Horizontal reference line + label across the whole x-range (mirrors charts.js).
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

  function theme(extra) {
    return Object.assign({
      font: { family: "Inter, -apple-system, Segoe UI, Roboto, sans-serif",
              size: 12, color: INK },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      hovermode: "closest",
      xaxis: { gridcolor: GRID, zerolinecolor: GRID, linecolor: GRID },
      yaxis: { gridcolor: GRID, zerolinecolor: GRID, linecolor: GRID }
    }, extra);
  }

  // ---- shared UI state ----
  var state = {
    param: "all",
    case: "all",
    metric: "gas",                       // "gas" | "runtime"
    clients: new Set(DATA.clients),      // active (checked) clients
  };

  function store() { return state.metric === "runtime" ? DATA.runtime : DATA.gas; }
  function seriesFor(param, client, caseId) {
    var s = store()[param];
    return (s && s[client] && s[client][caseId]) || null;
  }
  function poorFor(param, client, caseId) {
    var p = DATA.poor[param];
    return (p && p[client] && p[client][caseId]) || null;
  }
  function metricLabel() { return state.metric === "runtime" ? "runtime (ms)" : "proposed gas"; }

  function fmt(v) {
    if (v === null || v === undefined) return "—";
    if (state.metric === "runtime") return Number(v).toPrecision(4).replace(/\.?0+$/, "");
    return Number(v).toLocaleString();
  }
  function signed(v) {
    if (state.metric === "runtime" && Math.abs(Number(v)) < 1000) {
      var s = Number(v).toPrecision(4).replace(/\.?0+$/, "");
      return (Number(v) > 0 ? "+" : "") + s;
    }
    return (Number(v) > 0 ? "+" : "") + Math.round(Number(v)).toLocaleString();
  }

  // Which (client, case) pairs to show for a param, honouring the filters and
  // skipping pairs with no series at all.
  function visiblePairs(param) {
    var pairs = [];
    DATA.clients.forEach(function (client) {
      if (!state.clients.has(client)) return;
      DATA.cases.forEach(function (caseId) {
        if (state.case !== "all" && state.case !== caseId) return;
        if (seriesFor(param, client, caseId)) {
          pairs.push({ client: client, caseId: caseId });
        }
      });
    });
    return pairs;
  }

  function visibleParams() {
    return DATA.params.filter(function (p) {
      return state.param === "all" || state.param === p;
    });
  }

  // --------------------------------------------------------------------- //
  // Section 1 — latest-vs-previous rows (shared by the table and the Δ% bar)
  // --------------------------------------------------------------------- //
  function collectDeltaRows() {
    var prev = N - 2, last = N - 1;
    var rows = [];
    visibleParams().forEach(function (param) {
      // The binding row is the worst case in the latest run — it sets the proposal.
      var b = DATA.binding[param] && DATA.binding[param][last];
      visiblePairs(param).forEach(function (pair) {
        var s = seriesFor(param, pair.client, pair.caseId);
        var pv = s[prev], lv = s[last];
        if (pv == null && lv == null) return;
        var ps = poorFor(param, pair.client, pair.caseId);
        var delta = (pv != null && lv != null) ? lv - pv : null;
        var pct = (delta != null && pv) ? (delta / pv) * 100 : null;
        rows.push({
          param: param, client: pair.client, caseId: pair.caseId,
          isBinding: !!(b && b.client === pair.client && b.case === pair.caseId),
          pv: pv, lv: lv, delta: delta, pct: pct,
          poorPrev: !!(ps && ps[prev]), poorLast: !!(ps && ps[last]),
        });
      });
    });
    return rows;
  }

  // --------------------------------------------------------------------- //
  // Section 1 — delta table
  // --------------------------------------------------------------------- //
  var tableBody = document.querySelector("#delta-table tbody");
  var deltaEmpty = document.getElementById("delta-empty");
  var caption = document.getElementById("compare-caption");
  var poorNote = document.getElementById("poor-note");

  function poorMark(isPoor) {
    return isPoor
      ? '<span class="poor-flag" title="Low-confidence fit (R² ≤ 0.5 or p > 0.05)">*</span>'
      : "";
  }

  function deltaRow(r) {
    var tr = document.createElement("tr");
    if (r.isBinding) tr.className = "worst-case";
    var cls = r.delta == null || r.delta === 0 ? "chg-flat"
      : (r.delta < 0 ? "chg-down" : "chg-up");

    var clientCell = r.client;
    if (r.isBinding) {
      clientCell += ' <span class="binding-tag" title="Worst case for this parameter — sets the proposed gas">binding</span>';
    }

    tr.innerHTML =
      "<td>" + r.param + "</td>" +
      "<td>" + clientCell + "</td>" +
      "<td>" + caseLabel(r.caseId) + "</td>" +
      '<td class="num">' + fmt(r.pv) + poorMark(r.poorPrev) + "</td>" +
      '<td class="num">' + fmt(r.lv) + poorMark(r.poorLast) + "</td>" +
      '<td class="num chg ' + cls + '">' + (r.delta == null ? "—" : signed(r.delta)) + "</td>" +
      '<td class="num chg ' + cls + '">' +
        (r.pct == null ? "—" : (r.pct > 0 ? "+" : "") + r.pct.toFixed(1) + "%") + "</td>";
    return tr;
  }

  function buildTable(rows) {
    if (!tableBody) return;                       // < 2 runs: table not rendered
    caption.textContent = "Comparing " + LABELS[N - 2] + " → " + LABELS[N - 1] +
      " · metric: " + metricLabel() + " · highlighted = binding (worst-case) row";
    tableBody.textContent = "";
    var anyPoor = false;
    rows.forEach(function (r) {
      tableBody.appendChild(deltaRow(r));
      anyPoor = anyPoor || r.poorPrev || r.poorLast;
    });
    deltaEmpty.hidden = rows.length > 0;
    if (poorNote) poorNote.hidden = !anyPoor;
  }

  // --------------------------------------------------------------------- //
  // Section 1 — diverging Δ% bars (one bar per row; left = cheaper, right = costlier)
  // --------------------------------------------------------------------- //
  // A two-run line chart is just two dots, so we show the *change* instead. Δ%
  // normalises across params (gas spans 100→200k), so one axis works whether a
  // single param or "All" is selected — and the bars mirror the table rows.
  var barDiv = document.getElementById("delta-bar");

  function rowLabel(r) {
    var c = r.client + " · " + caseLabel(r.caseId);
    return state.param === "all" ? r.param + " · " + c : c;
  }

  function buildBar(rows) {
    if (!barDiv) return;                          // < 2 runs
    var drawable = rows.filter(function (r) { return r.pct != null; })
      .sort(function (a, b) { return a.pct - b.pct; });  // biggest improvement first

    if (!drawable.length) {
      Plotly.purge(barDiv);
      barDiv.innerHTML = "<p class='no-data'>No rows with a percent change for the current filters.</p>";
      return;
    }
    barDiv.innerHTML = "";

    var trace = {
      type: "bar",
      orientation: "h",
      y: drawable.map(rowLabel),
      x: drawable.map(function (r) { return r.pct; }),
      marker: {
        color: drawable.map(function (r) { return r.pct < 0 ? GREEN : RED; }),
        line: {
          color: drawable.map(function (r) { return r.isBinding ? BIND : "rgba(0,0,0,0)"; }),
          width: drawable.map(function (r) { return r.isBinding ? 2 : 0; }),
        },
      },
      customdata: drawable.map(function (r) {
        return [fmt(r.pv), fmt(r.lv)];
      }),
      hovertemplate:
        "%{y}<br>%{customdata[0]} → %{customdata[1]}  (%{x:+.1f}%)<extra></extra>",
    };

    var layout = theme({
      height: Math.max(220, drawable.length * 28 + 90),
      margin: { t: 10, r: 20, b: 50, l: 220 },
      bargap: 0.25,
    });
    Object.assign(layout.xaxis, {
      title: "Δ% vs previous run   (◄ cheaper · costlier ►)",
      ticksuffix: "%",
      zeroline: true,
    });
    Object.assign(layout.yaxis, { automargin: true, autorange: "reversed" });

    Plotly.newPlot(barDiv, [trace], layout, PLOT_CONFIG);
  }

  function renderSection1() {
    if (N < 2) return;                            // section not rendered
    var rows = collectDeltaRows();
    buildTable(rows);
    buildBar(rows);
  }

  // --------------------------------------------------------------------- //
  // Section 2 — one line chart per param, across all runs
  // --------------------------------------------------------------------- //
  var chartsHost = document.getElementById("trend-charts");
  var chartsEmpty = document.getElementById("charts-empty");
  var legendHost = document.getElementById("trend-legend");

  // One shared key for every chart: colour encodes the client, line style the
  // case. It factors the (client × case) series into two small groups so we don't
  // repeat up to 24 entries under each param's chart. Reflects the active filters.
  function lineSwatch(color, dash) {
    return '<svg class="trend-legend-line" width="26" height="10" aria-hidden="true">' +
      '<line x1="1" y1="5" x2="25" y2="5" stroke="' + (color || INK) +
      '" stroke-width="2"' +
      (DASH_SVG[dash] ? ' stroke-dasharray="' + DASH_SVG[dash] + '"' : "") +
      "></line></svg>";
  }

  function buildLegend() {
    if (!legendHost) return;
    var clients = DATA.clients.filter(function (c) { return state.clients.has(c); });
    var cases = DATA.cases.filter(function (c) {
      return state.case === "all" || state.case === c;
    });
    if (!clients.length || !cases.length) { legendHost.hidden = true; return; }

    var clientItems = clients.map(function (c) {
      return '<span class="trend-legend-item">' + lineSwatch(COLOR[c], "solid") +
        "<span>" + c + "</span></span>";
    }).join("");
    var caseItems = cases.map(function (c) {
      return '<span class="trend-legend-item">' + lineSwatch(INK, DASH[c]) +
        "<span>" + caseLabel(c) + "</span></span>";
    }).join("");

    legendHost.innerHTML =
      '<div class="trend-legend-group"><span class="trend-legend-label">Client</span>' +
      clientItems + "</div>" +
      '<div class="trend-legend-group"><span class="trend-legend-label">Case</span>' +
      caseItems + "</div>";
    legendHost.hidden = false;
  }

  function buildCharts() {
    // Tear down any prior plots before clearing the host (Plotly leaves listeners).
    Array.prototype.slice.call(chartsHost.querySelectorAll(".chart"))
      .forEach(function (d) { Plotly.purge(d); });
    chartsHost.textContent = "";

    var params = visibleParams();
    chartsEmpty.hidden = params.length > 0;
    if (params.length) buildLegend(); else legendHost.hidden = true;

    params.forEach(function (param) {
      var block = document.createElement("div");
      block.className = "chart-block";
      var h3 = document.createElement("h3");
      h3.textContent = param;
      var plot = document.createElement("div");
      plot.className = "chart";
      block.appendChild(h3);
      block.appendChild(plot);
      chartsHost.appendChild(block);

      var traces = visiblePairs(param).map(function (pair) {
        var label = pair.client + " · " + caseLabel(pair.caseId);
        return {
          type: "scatter",
          mode: "lines+markers",
          name: label,
          x: LABELS,
          y: seriesFor(param, pair.client, pair.caseId).slice(),
          connectgaps: true,
          line: { color: COLOR[pair.client], dash: DASH[pair.caseId], width: 2 },
          marker: { color: COLOR[pair.client], size: 6 },
          hovertemplate: label + "<br>%{x}: %{y}<extra></extra>",
        };
      });

      var layout = theme({
        margin: { t: 10, r: 20, b: 50, l: 70 },
        showlegend: false,   // a single shared key sits above all the charts
      });
      Object.assign(layout.xaxis, { title: "Run", automargin: true });
      Object.assign(layout.yaxis, { title: metricLabel(), rangemode: "tozero" });
      // Value transfer's reference is today's flat 21,000 gas. Only meaningful on
      // the proposed-gas axis, not the runtime one.
      if (param === "VALUE_TRANSFER" && state.metric === "gas") {
        Object.assign(layout, referenceLine(21000, "Current (21,000)"));
      }

      if (!traces.length) {
        plot.innerHTML = "<p class='no-data'>No (client, case) series match the current filters.</p>";
      } else {
        Plotly.newPlot(plot, traces, layout, PLOT_CONFIG);
      }
    });
  }

  // --------------------------------------------------------------------- //
  // Wiring
  // --------------------------------------------------------------------- //
  var paramSel = document.getElementById("param-filter");
  paramSel.addEventListener("change", function () {
    state.param = paramSel.value;
    renderSection1();
    buildCharts();
  });

  var caseSel = document.getElementById("case-filter");
  caseSel.addEventListener("change", function () {
    state.case = caseSel.value;
    renderSection1();
    buildCharts();
  });

  document.querySelectorAll("#client-toggles input").forEach(function (cb) {
    cb.addEventListener("change", function () {
      if (cb.checked) state.clients.add(cb.value); else state.clients.delete(cb.value);
      renderSection1();
      buildCharts();
    });
  });

  document.querySelectorAll("#metric-toggle input").forEach(function (rb) {
    rb.addEventListener("change", function () {
      if (!rb.checked) return;
      state.metric = rb.value;
      renderSection1();
      buildCharts();
    });
  });

  // ---- initial render ----
  renderSection1();
  buildCharts();
})();
