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
    diff_to_self: "Self",
    diff_to_unique_code_jumpdest_contract: "Contract (jumpdest)",
    diff_to_contract_minimal: "Contract (minimal)",
    diff_to_contract_same_max: "Contract (24KB, same code)",
    diff_to_contract_diff_max: "Contract (24KB, unique code)",
    diff_to_delegated_contract_diff: "Delegated (24KB, unique code)"
  };
  function caseLabel(caseId) {
    return CASE_LABELS[caseId] || caseId;
  }

  // Cases kept out of the charts. Presentation-only: the embedded run data still
  // carries them and both detail tables still list them; the summary cards and the
  // worst-case highlight drop them server-side. Keep in sync with EXCLUDED_CASES
  // in scripts/build_site.py (the Trends page has its own, smaller set — see
  // TRENDS_EXCLUDED_CASES there).
  var EXCLUDED_CASES = {
    diff_to_unique_code_jumpdest_contract: true,
    diff_to_contract: true
  };
  function charted(rows) {
    return rows.filter(function (r) {
      return !EXCLUDED_CASES[r.case_id];
    });
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

  // One client -> colour map shared by every chart in the section, so a given
  // client is always the same colour whether or not it has data for a given
  // chart (a per-chart uniqueSorted index would shift colours when a client is
  // missing from that chart's rows). Built once from the union of clients across
  // both chart data sources; the legend at the top of the section is rendered
  // from this same map.
  var CLIENT_COLOR = null;
  function clientColorMap() {
    if (CLIENT_COLOR) return CLIENT_COLOR;
    var data = window.DASHBOARD_DATA || {};
    var clients = uniqueSorted(
      charted(data.new_gas || []).concat(charted(data.results || [])),
      "client_name"
    );
    CLIENT_COLOR = {};
    clients.forEach(function (c, i) {
      CLIENT_COLOR[c] = PALETTE[i % PALETTE.length];
    });
    return CLIENT_COLOR;
  }

  // Render the section's single legend from the shared colour map.
  function buildChartsLegend() {
    var host = document.getElementById("charts-legend");
    if (!host) return;
    var colors = clientColorMap();
    var clients = Object.keys(colors).sort();
    if (!clients.length) { host.hidden = true; return; }
    host.innerHTML = clients.map(function (c) {
      return '<span class="chart-legend-item">' +
        '<span class="chart-legend-swatch" style="background:' + colors[c] + '"></span>' +
        "<span>" + c + "</span></span>";
    }).join("");
    host.hidden = false;
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

  // Grouped bar chart of new_gas_rounded for one Summary goal row, grouped by
  // client, with a "Goal" line at the row's target instead of a flat "current"
  // reference. goalRow is one entry of window.DASHBOARD_DATA.goals.rows (see
  // collect_goals in build_site.py). The x-axis is one tick per (case, param)
  // combination: usually one param per case, but "Transfer to self" spans both
  // ZERO_VALUE_TRANSFER and VALUE_TRANSFER over its one case, so that row gets two
  // ticks per case instead of collapsing to the worse of the two — both values stay
  // visible, matching what the row covers even though its table cell shows only
  // the worst.
  function plotGoal(divId, goalRow) {
    var div = document.getElementById(divId);
    if (!div || !window.DASHBOARD_DATA) return;

    var params = goalRow.params;
    var cases = goalRow.cases || [];
    var caseIds = cases.map(function (c) { return c.case_id; });
    var rows = charted(window.DASHBOARD_DATA.new_gas || []).filter(function (r) {
      return params.indexOf(r.param) !== -1 && caseIds.indexOf(r.case_id) !== -1;
    });
    if (!rows.length) { div.innerHTML = "<p class='no-data'>No data.</p>"; return; }

    var series = [];
    cases.forEach(function (c) {
      params.forEach(function (p) {
        series.push({
          case_id: c.case_id,
          param: p,
          tick: params.length > 1 ? c.label + " (" + p + ")" : c.label
        });
      });
    });
    var seriesTicks = series.map(function (s) { return s.tick; });
    var clients = uniqueSorted(rows, "client_name");
    var colors = clientColorMap();

    var traces = clients.map(function (client) {
      var y = [], errHigh = [], errLow = [];
      series.forEach(function (s) {
        var row = rows.find(function (r) {
          return r.client_name === client && r.case_id === s.case_id && r.param === s.param;
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
        x: seriesTicks,
        y: y,
        marker: { color: colors[client] },
        showlegend: false,
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
      margin: { t: 10, r: 20, b: 50, l: 70 }
    });
    Object.assign(layout.xaxis, { title: "Case", automargin: true });
    Object.assign(layout.yaxis, { title: "Proposed gas (rounded)" });
    Object.assign(layout, referenceLine(goalRow.goal, "Goal (" + goalRow.goal.toLocaleString() + ")"));

    Plotly.newPlot(div, traces, layout, PLOT_CONFIG);
  }

  // Grouped bar chart of R^2 per (client, case) from results, x = case_id, grouped by
  // client. Each (client, case) is now two fits (zero-value / value); we plot the worse
  // of the two, matching the R² <= 0.5 caveat logic. The detail table breaks out both.
  function plotRsquared(divId) {
    var div = document.getElementById(divId);
    if (!div || !window.DASHBOARD_DATA) return;

    var rows = charted(window.DASHBOARD_DATA.results || []);
    if (!rows.length) { div.innerHTML = "<p class='no-data'>No data.</p>"; return; }

    var cases = uniqueSorted(rows, "case_id");
    var caseTicks = cases.map(caseLabel);
    var clients = uniqueSorted(rows, "client_name");
    var colors = clientColorMap();

    var traces = clients.map(function (client) {
      var y = cases.map(function (caseId) {
        var row = rows.find(function (r) {
          return r.client_name === client && r.case_id === caseId;
        });
        if (!row) return null;
        var vals = [row.without_rsquared, row.with_rsquared].filter(function (v) {
          return v != null;
        });
        return vals.length ? Math.min.apply(null, vals) : null;
      });
      return {
        type: "bar",
        name: client,
        x: caseTicks,
        y: y,
        marker: { color: colors[client] },
        showlegend: false
      };
    });

    var layout = theme({
      barmode: "group",
      margin: { t: 10, r: 20, b: 50, l: 60 }
    });
    Object.assign(layout.xaxis, { title: "Case", automargin: true });
    Object.assign(layout.yaxis, { title: "R²", range: [0, 1.05] });
    Object.assign(layout, referenceLine(0.5, "R² = 0.5"));

    Plotly.newPlot(div, traces, layout, PLOT_CONFIG);
  }

  // Run selector: a custom button + listbox so the font/colors match the page
  // open and closed (a native <select> popup uses the OS font). Each option is a
  // link, so selecting one just navigates to that run's pre-rendered page.
  function initRunDropdown() {
    var root = document.querySelector("[data-run-dropdown]");
    if (!root) return;
    var toggle = root.querySelector(".run-dropdown-toggle");
    var list = root.querySelector(".run-dropdown-list");
    var options = Array.prototype.slice.call(
      root.querySelectorAll(".run-dropdown-option")
    );
    if (!toggle || !list || !options.length) return;

    function isOpen() {
      return toggle.getAttribute("aria-expanded") === "true";
    }
    function open(focusIndex) {
      list.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      var i = focusIndex;
      if (i == null) {
        i = options.findIndex(function (o) {
          return o.classList.contains("is-current");
        });
        if (i < 0) i = 0;
      }
      options[i].focus();
    }
    function close(focusToggle) {
      list.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      if (focusToggle) toggle.focus();
    }
    function focusAt(i) {
      var n = options.length;
      options[((i % n) + n) % n].focus();
    }

    toggle.addEventListener("click", function () {
      isOpen() ? close(false) : open();
    });
    toggle.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open(0);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        open(options.length - 1);
      }
    });
    options.forEach(function (opt, i) {
      opt.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown") { e.preventDefault(); focusAt(i + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); focusAt(i - 1); }
        else if (e.key === "Home") { e.preventDefault(); focusAt(0); }
        else if (e.key === "End") { e.preventDefault(); focusAt(options.length - 1); }
        else if (e.key === "Escape") { e.preventDefault(); close(true); }
        // Enter / click follow the link's href (native navigation).
      });
    });
    document.addEventListener("click", function (e) {
      if (isOpen() && !root.contains(e.target)) close(false);
    });
  }

  // Detail-table filters. Pure DOM toggling on server-rendered rows: each select
  // carries data-filter-key="<k>" and matches against the row's data-<k> attribute,
  // so a group filters on whatever keys it declares (e.g. client/param/case). No
  // re-render, no data read. Wires every [data-table-filters] block on the page.
  function initTableFilter(controls) {
    var table = controls.parentElement.querySelector("[data-filter-table]");
    if (!table) return;
    var selects = Array.prototype.slice.call(
      controls.querySelectorAll("[data-filter-key]")
    );
    var empty = controls.querySelector("[data-filter-empty]");
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));

    function apply() {
      var shown = 0;
      rows.forEach(function (tr) {
        var match = selects.every(function (sel) {
          return !sel.value ||
            tr.getAttribute("data-" + sel.getAttribute("data-filter-key")) === sel.value;
        });
        tr.hidden = !match;
        if (match) shown++;
      });
      if (empty) empty.hidden = shown > 0;
    }

    selects.forEach(function (sel) {
      sel.addEventListener("change", apply);
    });
    apply();
  }

  function initTableFilters() {
    Array.prototype.slice
      .call(document.querySelectorAll("[data-table-filters]"))
      .forEach(initTableFilter);
  }

  // Hover info for [data-tip] elements (the goal table's cell/row-name tooltips).
  // Not the native `title` attribute: that relies on the browser's own tooltip
  // layer, which doesn't render in every browser/embedding. This draws a single
  // shared tooltip div in fixed coordinates instead, so it can't be clipped by
  // .table-scroll's overflow and doesn't depend on native support.
  function initTooltips() {
    var targets = Array.prototype.slice.call(document.querySelectorAll("[data-tip]"));
    if (!targets.length) return;
    var tip = document.createElement("div");
    tip.className = "js-tooltip";
    document.body.appendChild(tip);
    var current = null;

    function position(el) {
      var r = el.getBoundingClientRect();
      var tr = tip.getBoundingClientRect();
      var left = r.left + r.width / 2 - tr.width / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
      var top = r.top - tr.height - 8;
      if (top < 8) top = r.bottom + 8;
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }
    function show(el) {
      tip.textContent = el.getAttribute("data-tip");
      tip.classList.add("is-visible");
      position(el);
      current = el;
    }
    function hide() {
      tip.classList.remove("is-visible");
      current = null;
    }

    targets.forEach(function (el) {
      el.addEventListener("mouseenter", function () { show(el); });
      el.addEventListener("mouseleave", hide);
    });
    window.addEventListener("scroll", function () {
      if (current) position(current);
    }, true);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initRunDropdown();
    initTableFilters();
    initTooltips();
    if (!window.DASHBOARD_DATA) return;
    buildChartsLegend();
    // One chart per Summary goal row (see collect_goals in build_site.py); div ids
    // are chart-goal-<index>, assigned in the same order by index.html's loop.
    (window.DASHBOARD_DATA.goals && window.DASHBOARD_DATA.goals.rows || []).forEach(
      function (row, i) { plotGoal("chart-goal-" + i, row); }
    );
    plotRsquared("chart-rsquared");
  });
})();
