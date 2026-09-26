const state = {
  data: null,
  view: "dashboard",
  pair: null,
  side: "long",
  period: "1Y",
  customStart: null,
  brokers: new Set(),
  chart: null,
  rankingMetric: "totalReturn",
  rankingDirection: "desc",
  tableSort: { key: "total", direction: "desc" },
};

const BROKER_COLORS = {
  matsui_fx: "#38bdf8",
  fxbroadnet: "#facc15",
  gaitame_com: "#57e3b4",
  gmo_gaika: "#60a5fa",
  gmo_click: "#f2b45f",
  triauto: "#b991ff",
  minfx: "#22d3ee",
  minfx_light: "#06b6d4",
  lightfx: "#f472b6",
  lightfx_light: "#ec4899",
  sbi_fx: "#ef6f6c",
  hirose: "#a3e635",
  jfx: "#fb923c",
};

const SPOT_COLOR = "#94a3b8";

const RANKING_METRICS = {
  totalReturn: { label: "Total Return", best: "max", defaultDirection: "desc", format: formatPct },
  annualizedReturn: { label: "Annualized Return", best: "max", defaultDirection: "desc", format: formatPct },
  swapContribution: { label: "Swap Contribution", best: "max", defaultDirection: "desc", format: formatPct },
  annualizedSwap: { label: "Annualized Swap", best: "max", defaultDirection: "desc", format: formatPct },
  maxDrawdown: { label: "Max Drawdown", best: "max", defaultDirection: "desc", format: formatPct },
  volatility: { label: "Volatility", best: "min", defaultDirection: "asc", format: formatPct },
};

const $ = (id) => document.getElementById(id);

function brokerName(id) {
  return state.data.brokers.find((broker) => broker.id === id)?.name || id;
}

function brokerColor(id) {
  return BROKER_COLORS[id] || "#7dd3fc";
}

function formatPct(value) {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatJpy(value) {
  if (!Number.isFinite(value)) return "—";
  const rounded = Math.round(value);
  const sign = rounded > 0 ? "+" : rounded < 0 ? "-" : "";
  return `${sign}¥${Math.abs(rounded).toLocaleString("ja-JP")}`;
}

function valueClass(value) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function formatDate(dateText) {
  if (!dateText) return "—";
  const [year, month, day] = dateText.split("-");
  return `${year}/${month}/${day}`;
}

function daysBetween(start, end) {
  if (!start || !end) return 0;
  return Math.max(
    0,
    Math.round(
      (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000
    )
  );
}

function cutoffFor(points) {
  if (!points.length) return null;
  if (state.customStart) return state.customStart;
  if (state.period === "MAX") return null;

  const last = new Date(`${points[points.length - 1].date}T00:00:00Z`);
  const cutoff = new Date(last);
  if (state.period === "1M") cutoff.setUTCMonth(cutoff.getUTCMonth() - 1);
  if (state.period === "3M") cutoff.setUTCMonth(cutoff.getUTCMonth() - 3);
  if (state.period === "1Y") cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
  if (state.period === "3Y") cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 3);
  return cutoff.toISOString().slice(0, 10);
}

function periodPoints(rawPoints) {
  if (!rawPoints?.length) return [];
  const cutoff = cutoffFor(rawPoints);
  return cutoff ? rawPoints.filter((point) => point.date >= cutoff) : rawPoints.slice();
}

function rebase(points, startDate = null) {
  if (!points?.length) return [];
  const aligned = startDate ? points.filter((point) => point.date >= startDate) : points;
  if (!aligned.length) return [];

  const first = aligned[0];
  const unit = state.data.metadata.unit;
  const initialNotionalJpy = unit * first.base_jpy;

  return aligned.map((point) => {
    const fxLongJpy = unit * (point.spot - first.spot) * point.quote_jpy;
    const longSwapJpy = point.cum_long_swap_jpy - first.cum_long_swap_jpy;
    const shortSwapJpy = point.cum_short_swap_jpy - first.cum_short_swap_jpy;
    const longPnlJpy = fxLongJpy + longSwapJpy;
    const shortPnlJpy = -fxLongJpy + shortSwapJpy;

    return {
      ...point,
      fxLongJpy,
      longSwapJpy,
      shortSwapJpy,
      longPnlJpy,
      shortPnlJpy,
      longIndex: 100 + (longPnlJpy / initialNotionalJpy) * 100,
      shortIndex: 100 + (shortPnlJpy / initialNotionalJpy) * 100,
      spotLongIndex: 100 + (fxLongJpy / initialNotionalJpy) * 100,
      spotShortIndex: 100 - (fxLongJpy / initialNotionalJpy) * 100,
    };
  });
}

function sideKeys(side) {
  return side === "long"
    ? { index: "longIndex", spot: "spotLongIndex", swap: "longSwapJpy" }
    : { index: "shortIndex", spot: "spotShortIndex", swap: "shortSwapJpy" };
}

function standardDeviation(values) {
  if (values.length < 2) return 0;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function metricsFor(item, side) {
  if (!item?.points?.length) return null;
  const points = item.points;
  const keys = sideKeys(side);
  const first = points[0];
  const last = points.at(-1);
  const totalReturn = last[keys.index] - 100;
  const spotReturn = last[keys.spot] - 100;
  const swapContribution = totalReturn - spotReturn;
  const holdingDays = Math.max(1, daysBetween(first.date, last.date));
  const finalIndex = last[keys.index];

  const annualizedReturn = finalIndex > 0
    ? (Math.pow(finalIndex / 100, 365 / holdingDays) - 1) * 100
    : null;
  const annualizedSwap = swapContribution * (365 / holdingDays);

  let peak = points[0][keys.index];
  let maxDrawdown = 0;
  const dailyReturns = [];

  for (let i = 0; i < points.length; i += 1) {
    const value = points[i][keys.index];
    if (value > peak) peak = value;
    if (peak > 0) {
      const drawdown = ((value / peak) - 1) * 100;
      if (drawdown < maxDrawdown) maxDrawdown = drawdown;
    }
    if (i > 0) {
      const previous = points[i - 1][keys.index];
      if (previous > 0 && Number.isFinite(value)) {
        dailyReturns.push((value / previous) - 1);
      }
    }
  }

  const volatility = standardDeviation(dailyReturns) * Math.sqrt(365) * 100;

  return {
    broker: item.broker,
    side,
    totalReturn,
    spotReturn,
    swapContribution,
    cumulativeSwap: last[keys.swap],
    annualizedReturn,
    annualizedSwap,
    maxDrawdown,
    volatility,
    startDate: first.date,
    endDate: last.date,
    holdingDays,
  };
}

function activeBrokerCandidates() {
  const pairSeries = state.data.series[state.pair] || {};
  const candidates = [];

  for (const broker of state.brokers) {
    const item = pairSeries[broker];
    if (!item) continue;
    const points = periodPoints(item.points);
    if (points.length) candidates.push({ broker, points });
  }
  return candidates;
}

function comparisonBrokerSeries() {
  const candidates = activeBrokerCandidates();
  if (!candidates.length) return [];
  const commonStart = candidates.map((item) => item.points[0].date).sort().at(-1);
  return candidates
    .map((item) => ({ broker: item.broker, points: rebase(item.points, commonStart) }))
    .filter((item) => item.points.length);
}

function chartBrokerSeries() {
  return activeBrokerCandidates()
    .map((item) => ({ broker: item.broker, points: rebase(item.points) }))
    .filter((item) => item.points.length);
}

function longestSpotReference() {
  const candidates = activeBrokerCandidates();
  if (!candidates.length) return [];
  const oldestBrokerStart = candidates.map((item) => item.points[0].date).sort()[0];
  const longest = candidates.reduce(
    (best, item) => (!best || item.points[0].date < best.points[0].date ? item : best),
    null
  );
  return rebase(longest.points.filter((point) => point.date >= oldestBrokerStart));
}

function renderBrokerButtons() {
  const pairSeries = state.data.series[state.pair] || {};
  const container = $("brokerButtons");
  container.innerHTML = "";

  for (const broker of state.data.brokers) {
    if (!pairSeries[broker.id]) continue;
    const button = document.createElement("button");
    button.textContent = broker.name;
    button.style.setProperty("--broker-color", brokerColor(broker.id));
    button.className = state.brokers.has(broker.id) ? "active" : "";
    button.addEventListener("click", () => {
      if (state.brokers.has(broker.id) && state.brokers.size > 1) {
        state.brokers.delete(broker.id);
      } else {
        state.brokers.add(broker.id);
      }
      renderDashboard();
    });
    container.appendChild(button);
  }
}

function renderRangeSummary(chartSeries, comparisonSeries) {
  if (chartSeries.length) {
    const starts = chartSeries.map((item) => item.points[0].date).sort();
    const ends = chartSeries.map((item) => item.points.at(-1).date).sort();
    $("comparisonRange").textContent =
      `Chart  ${formatDate(starts[0])} → ${formatDate(ends.at(-1))}`;
  } else {
    $("comparisonRange").textContent = "Chart —";
  }

  if (comparisonSeries.length) {
    $("spotRange").textContent =
      `Comparison  ${formatDate(comparisonSeries[0].points[0].date)} → ${formatDate(comparisonSeries[0].points.at(-1).date)}`;
  } else {
    $("spotRange").textContent = "";
  }
}

function sortMetrics(rows, key, direction) {
  return rows.slice().sort((a, b) => {
    if (key === "broker") {
      return direction === "asc"
        ? brokerName(a.broker).localeCompare(brokerName(b.broker), "ja")
        : brokerName(b.broker).localeCompare(brokerName(a.broker), "ja");
    }
    if (key === "since") {
      const av = a.startDate || "";
      const bv = b.startDate || "";
      return direction === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    const av = a[key];
    const bv = b[key];
    if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
    if (!Number.isFinite(av)) return 1;
    if (!Number.isFinite(bv)) return -1;
    return direction === "asc" ? av - bv : bv - av;
  });
}

function sortHeader(label, key) {
  const active = state.tableSort.key === key;
  const marker = active ? (state.tableSort.direction === "asc" ? "↑" : "↓") : "";
  return `<button class="sort-header-button ${active ? "active-sort" : ""}" data-table-sort="${key}">${label}<span class="sort-marker">${marker}</span></button>`;
}

function bindTableSort() {
  document.querySelectorAll("[data-table-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.tableSort;
      if (state.tableSort.key === key) {
        state.tableSort.direction = state.tableSort.direction === "desc" ? "asc" : "desc";
      } else {
        state.tableSort.key = key;
        state.tableSort.direction = key === "broker" || key === "since" ? "asc" : "desc";
      }
      renderDashboard();
    });
  });
}

function renderPerformanceTable(series, spotReference) {
  const head = $("performanceHead");
  const body = $("performanceBody");
  head.innerHTML = "";
  body.innerHTML = "";

  if (state.side === "both") {
    const rows = series.map((item) => {
      const long = metricsFor(item, "long");
      const short = metricsFor(item, "short");
      return {
        broker: item.broker,
        longReturn: long.totalReturn,
        shortReturn: short.totalReturn,
        longSwap: long.cumulativeSwap,
        shortSwap: short.cumulativeSwap,
        startDate: long.startDate,
      };
    });
    const sorted = sortMetrics(rows, state.tableSort.key, state.tableSort.direction);
    head.innerHTML = `<tr>
      <th>${sortHeader("Broker", "broker")}</th>
      <th>${sortHeader("Long return", "longReturn")}</th>
      <th>${sortHeader("Short return", "shortReturn")}</th>
      <th>${sortHeader("Long swap", "longSwap")}</th>
      <th>${sortHeader("Short swap", "shortSwap")}</th>
      <th>${sortHeader("Since", "since")}</th>
    </tr>`;

    for (const metric of sorted) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(metric.broker)}"></span>${brokerName(metric.broker)}</div></td>
        <td class="return-value ${valueClass(metric.longReturn)}">${formatPct(metric.longReturn)}</td>
        <td class="return-value ${valueClass(metric.shortReturn)}">${formatPct(metric.shortReturn)}</td>
        <td class="${valueClass(metric.longSwap)}">${formatJpy(metric.longSwap)}</td>
        <td class="${valueClass(metric.shortSwap)}">${formatJpy(metric.shortSwap)}</td>
        <td>${formatDate(metric.startDate)}</td>`;
      body.appendChild(row);
    }

    if (spotReference.length) {
      const last = spotReference.at(-1);
      const row = document.createElement("tr");
      row.className = "benchmark-row";
      row.innerHTML = `
        <td><div class="broker-cell"><span class="series-dot" style="--series-color:${SPOT_COLOR}"></span>Spot only</div></td>
        <td class="return-value ${valueClass(last.spotLongIndex - 100)}">${formatPct(last.spotLongIndex - 100)}</td>
        <td class="return-value ${valueClass(last.spotShortIndex - 100)}">${formatPct(last.spotShortIndex - 100)}</td>
        <td class="neutral">—</td><td class="neutral">—</td>
        <td>${formatDate(spotReference[0].date)}</td>`;
      body.appendChild(row);
    }
    bindTableSort();
    return;
  }

  const metrics = series.map((item) => metricsFor(item, state.side)).filter(Boolean);
  const keyMap = {
    total: "totalReturn",
    spot: "spotReturn",
    swapContribution: "swapContribution",
    cumulativeSwap: "cumulativeSwap",
    since: "since",
    broker: "broker",
  };
  const sorted = sortMetrics(
    metrics,
    keyMap[state.tableSort.key] || state.tableSort.key,
    state.tableSort.direction
  );

  head.innerHTML = `<tr>
    <th>${sortHeader("Broker", "broker")}</th>
    <th>${sortHeader("Total return", "total")}</th>
    <th>${sortHeader("Spot return", "spot")}</th>
    <th>${sortHeader("Swap contribution", "swapContribution")}</th>
    <th>${sortHeader("Cumulative swap", "cumulativeSwap")}</th>
    <th>${sortHeader("Since", "since")}</th>
  </tr>`;

  for (const metric of sorted) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(metric.broker)}"></span>${brokerName(metric.broker)}</div></td>
      <td class="return-value ${valueClass(metric.totalReturn)}">${formatPct(metric.totalReturn)}</td>
      <td class="${valueClass(metric.spotReturn)}">${formatPct(metric.spotReturn)}</td>
      <td class="${valueClass(metric.swapContribution)}">${formatPct(metric.swapContribution)}</td>
      <td class="${valueClass(metric.cumulativeSwap)}">${formatJpy(metric.cumulativeSwap)}</td>
      <td>${formatDate(metric.startDate)}</td>`;
    body.appendChild(row);
  }

  if (spotReference.length) {
    const last = spotReference.at(-1);
    const key = state.side === "long" ? "spotLongIndex" : "spotShortIndex";
    const spotReturn = last[key] - 100;
    const row = document.createElement("tr");
    row.className = "benchmark-row";
    row.innerHTML = `
      <td><div class="broker-cell"><span class="series-dot" style="--series-color:${SPOT_COLOR}"></span>Spot only</div></td>
      <td class="return-value ${valueClass(spotReturn)}">${formatPct(spotReturn)}</td>
      <td class="${valueClass(spotReturn)}">${formatPct(spotReturn)}</td>
      <td class="neutral">0.00%</td><td class="neutral">—</td>
      <td>${formatDate(spotReference[0].date)}</td>`;
    body.appendChild(row);
  }
  bindTableSort();
}

function renderChart(series, spotReference) {
  if (!window.echarts) throw new Error("EChartsを読み込めませんでした。");
  if (!state.chart) {
    state.chart = echarts.init($("chart"));
    window.addEventListener("resize", () => state.chart.resize());
  }

  const chartSeries = [];
  for (const item of series) {
    const name = brokerName(item.broker);
    const color = brokerColor(item.broker);
    if (state.side === "long" || state.side === "both") {
      chartSeries.push({
        name: `${name} Long`, type: "line", showSymbol: false, color,
        lineStyle: { width: 2.2, color }, emphasis: { focus: "series" },
        data: item.points.map((point) => [point.date, point.longIndex]),
      });
    }
    if (state.side === "short" || state.side === "both") {
      chartSeries.push({
        name: `${name} Short`, type: "line", showSymbol: false, color,
        lineStyle: { width: 1.8, type: "dashed", color, opacity: 0.86 },
        emphasis: { focus: "series" },
        data: item.points.map((point) => [point.date, point.shortIndex]),
      });
    }
  }

  if (spotReference.length) {
    if (state.side === "long" || state.side === "both") {
      chartSeries.push({
        name: state.side === "both" ? "Spot only Long" : "Spot only",
        type: "line", showSymbol: false, color: SPOT_COLOR,
        lineStyle: { width: 1.5, type: "dotted", color: SPOT_COLOR, opacity: 0.9 },
        data: spotReference.map((point) => [point.date, point.spotLongIndex]),
      });
    }
    if (state.side === "short" || state.side === "both") {
      chartSeries.push({
        name: state.side === "both" ? "Spot only Short" : "Spot only",
        type: "line", showSymbol: false, color: SPOT_COLOR,
        lineStyle: { width: 1.5, type: "dotted", color: SPOT_COLOR, opacity: 0.9 },
        data: spotReference.map((point) => [point.date, point.spotShortIndex]),
      });
    }
  }

  state.chart.setOption({
    backgroundColor: "transparent",
    animationDuration: 240,
    grid: { left: 62, right: 24, top: 56, bottom: 48 },
    legend: { top: 10, left: 14, itemWidth: 20, itemHeight: 7, textStyle: { color: "#7f8d9c", fontSize: 11 }, inactiveColor: "#3f4a56" },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "#344050", width: 1 } },
      backgroundColor: "rgba(9,13,18,.96)", borderColor: "#27313d", borderWidth: 1,
      textStyle: { color: "#e7edf4", fontSize: 11 },
      extraCssText: "box-shadow:0 14px 34px rgba(0,0,0,.32);border-radius:7px;",
      valueFormatter: (value) => Number(value).toFixed(2),
    },
    xAxis: { type: "time", boundaryGap: false, axisLine: { lineStyle: { color: "#24303b" } }, axisTick: { show: false }, axisLabel: { color: "#667382", fontSize: 10, hideOverlap: true }, splitLine: { show: false } },
    yAxis: { type: "value", scale: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#667382", fontSize: 10, formatter: (value) => value.toFixed(1) }, splitLine: { lineStyle: { color: "rgba(74,88,103,.16)" } } },
    dataZoom: [{ type: "inside", filterMode: "none", zoomOnMouseWheel: false, moveOnMouseMove: true, moveOnMouseWheel: false }],
    series: chartSeries,
  }, true);
}

function rankingPairCandidates(pair) {
  const pairSeries = state.data.series[pair] || {};
  const candidates = [];

  for (const [broker, item] of Object.entries(pairSeries)) {
    const points = periodPoints(item.points);
    if (points.length >= 2) candidates.push({ broker, points });
  }
  if (!candidates.length) return [];

  // Keep the longest available requested window for this pair. Brokers whose
  // history starts later do not shorten the ranking period for everyone else.
  const pairStart = candidates.map((item) => item.points[0].date).sort()[0];
  const eligible = candidates.filter((item) => item.points[0].date === pairStart);

  return eligible
    .map((item) => ({ broker: item.broker, points: rebase(item.points, pairStart) }))
    .filter((item) => item.points.length >= 2);
}

function bestBrokerForPair(pair, side) {
  const series = rankingPairCandidates(pair);
  if (!series.length) return null;
  const metricDef = RANKING_METRICS[state.rankingMetric];
  const rows = series.map((item) => metricsFor(item, side)).filter(Boolean);
  if (!rows.length) return null;

  rows.sort((a, b) => {
    const av = a[state.rankingMetric];
    const bv = b[state.rankingMetric];
    if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
    if (!Number.isFinite(av)) return 1;
    if (!Number.isFinite(bv)) return -1;
    return metricDef.best === "min" ? av - bv : bv - av;
  });

  return { pair, ...rows[0] };
}

function pairRankingRows(side) {
  const rows = state.data.pairs
    .map((pair) => bestBrokerForPair(pair, side))
    .filter(Boolean);

  rows.sort((a, b) => {
    const av = a[state.rankingMetric];
    const bv = b[state.rankingMetric];
    if (!Number.isFinite(av) && !Number.isFinite(bv)) return a.pair.localeCompare(b.pair);
    if (!Number.isFinite(av)) return 1;
    if (!Number.isFinite(bv)) return -1;
    return state.rankingDirection === "asc" ? av - bv : bv - av;
  });
  return rows;
}

function renderPairRankingColumn(side) {
  const metricDef = RANKING_METRICS[state.rankingMetric];
  const rows = pairRankingRows(side);
  const column = document.createElement("div");
  column.className = "pair-ranking-column";
  column.innerHTML = `
    <div class="pair-ranking-side">
      <strong>${side.toUpperCase()}</strong>
      <span>Each pair uses its best ${metricDef.label} broker</span>
    </div>
    <div class="table-scroll">
      <table class="pair-ranking-table">
        <thead>
          <tr>
            <th>#</th><th>Pair</th><th>Best broker</th>
            <th>${metricDef.label}</th><th>Total Return</th><th>Swap</th>
            <th>Max DD</th><th>Volatility</th><th>Since</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>`;

  const body = column.querySelector("tbody");
  rows.forEach((metric, index) => {
    const row = document.createElement("tr");
    row.title = `Open ${metric.pair} in Dashboard`;
    row.innerHTML = `
      <td class="pair-rank">#${index + 1}</td>
      <td class="pair-name">${metric.pair}</td>
      <td><span class="best-broker"><span class="series-dot" style="--series-color:${brokerColor(metric.broker)}"></span>${brokerName(metric.broker)}</span></td>
      <td class="metric-primary ${valueClass(metric[state.rankingMetric])}">${metricDef.format(metric[state.rankingMetric])}</td>
      <td class="${valueClass(metric.totalReturn)}">${formatPct(metric.totalReturn)}</td>
      <td class="${valueClass(metric.swapContribution)}">${formatPct(metric.swapContribution)}</td>
      <td class="${valueClass(metric.maxDrawdown)}">${formatPct(metric.maxDrawdown)}</td>
      <td>${formatPct(metric.volatility)}</td>
      <td class="coverage-note">${formatDate(metric.startDate)}</td>`;
    row.addEventListener("click", () => openPairInDashboard(metric.pair));
    body.appendChild(row);
  });

  if (!rows.length) {
    column.innerHTML += '<div class="ranking-empty">No comparable pairs for this range.</div>';
  }
  return column;
}

function renderPairRanking() {
  document.querySelectorAll("#rankingTabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.rankingMetric === state.rankingMetric);
  });
  const metricDef = RANKING_METRICS[state.rankingMetric];
  $("rankingDirection").textContent = state.rankingDirection === "desc" ? "High → Low" : "Low → High";
  const rangeLabel = state.customStart ? `From ${formatDate(state.customStart)}` : state.period;
  $("rankingContext").textContent = `${state.side.toUpperCase()} · ${rangeLabel} · ${metricDef.label}`;

  const content = $("pairRankingContent");
  content.innerHTML = "";
  content.classList.toggle("both", state.side === "both");

  if (state.side === "both") {
    content.appendChild(renderPairRankingColumn("long"));
    content.appendChild(renderPairRankingColumn("short"));
  } else {
    content.appendChild(renderPairRankingColumn(state.side));
  }
}

function renderPeriodState() {
  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.classList.toggle("active", !state.customStart && button.dataset.period === state.period);
  });
}

function resetSortsForSide() {
  state.tableSort = state.side === "both"
    ? { key: "longReturn", direction: "desc" }
    : { key: "total", direction: "desc" };
}

function renderDashboard() {
  renderBrokerButtons();
  const comparisonSeries = comparisonBrokerSeries();
  const chartSeries = chartBrokerSeries();
  const spotReference = longestSpotReference();

  renderPerformanceTable(comparisonSeries, spotReference);
  renderChart(chartSeries, spotReference);
  renderRangeSummary(chartSeries, comparisonSeries);

  const rangeLabel = state.customStart ? `From ${formatDate(state.customStart)}` : state.period;
  $("chartTitle").textContent = `${state.pair} · ${state.side.toUpperCase()} · ${rangeLabel}`;
}

function renderView() {
  const ranking = state.view === "ranking";
  document.body.classList.toggle("ranking-mode", ranking);
  $("dashboardView").hidden = ranking;
  $("rankingView").hidden = !ranking;
  $("pairField").hidden = ranking;
  $("brokerFilterStrip").hidden = ranking;

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });

  renderPeriodState();
  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.side === state.side);
  });

  if (ranking) {
    updateDateBounds();
    renderPairRanking();
  } else {
    updateDateBounds();
    renderDashboard();
    requestAnimationFrame(() => state.chart?.resize());
  }
}

function openPairInDashboard(pair) {
  state.pair = pair;
  $("pairSelect").value = pair;
  state.view = "dashboard";
  const available = Object.keys(state.data.series[pair] || {});
  state.brokers = new Set(available);
  updateDateBounds();
  resetSortsForSide();
  renderView();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateDateBounds() {
  const input = $("customStartDate");
  const starts = [];
  const ends = [];

  if (state.view === "ranking") {
    for (const pairSeries of Object.values(state.data.series)) {
      for (const item of Object.values(pairSeries)) {
        if (item?.points?.length) {
          starts.push(item.points[0].date);
          ends.push(item.points.at(-1).date);
        }
      }
    }
  } else {
    const pairSeries = state.data.series[state.pair] || {};
    for (const item of Object.values(pairSeries)) {
      if (item?.points?.length) {
        starts.push(item.points[0].date);
        ends.push(item.points.at(-1).date);
      }
    }
  }

  input.min = starts.length ? starts.sort()[0] : "";
  input.max = ends.length ? ends.sort().at(-1) : "";
}

function setupControls() {
  const pairSelect = $("pairSelect");
  for (const pair of state.data.pairs) {
    const option = document.createElement("option");
    option.value = pair;
    option.textContent = pair;
    pairSelect.appendChild(option);
  }

  const preferred = ["USD/JPY", "TRY/JPY", "CHF/TRY", "USD/CHF"];
  state.pair = preferred.find((pair) => state.data.pairs.includes(pair)) || state.data.pairs[0];
  pairSelect.value = state.pair;
  state.brokers = new Set(Object.keys(state.data.series[state.pair] || {}));

  pairSelect.addEventListener("change", () => {
    state.pair = pairSelect.value;
    state.customStart = null;
    $("customStartDate").value = "";
    state.brokers = new Set(Object.keys(state.data.series[state.pair] || {}));
    resetSortsForSide();
    updateDateBounds();
    renderView();
  });

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      updateDateBounds();
      renderView();
    });
  });

  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.side = button.dataset.side;
      resetSortsForSide();
      renderView();
    });
  });

  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      state.customStart = null;
      $("customStartDate").value = "";
      renderView();
    });
  });

  document.querySelectorAll("#rankingTabs button").forEach((button) => {
    button.addEventListener("click", () => {
      state.rankingMetric = button.dataset.rankingMetric;
      state.rankingDirection = RANKING_METRICS[state.rankingMetric].defaultDirection;
      renderPairRanking();
    });
  });

  $("rankingDirection").addEventListener("click", () => {
    state.rankingDirection = state.rankingDirection === "desc" ? "asc" : "desc";
    renderPairRanking();
  });

  $("customStartDate").addEventListener("change", (event) => {
    state.customStart = event.target.value || null;
    if (!state.customStart) state.period = "1Y";
    renderView();
  });

  $("clearCustomDate").addEventListener("click", () => {
    state.customStart = null;
    state.period = "1Y";
    $("customStartDate").value = "";
    renderView();
  });

  state.rankingDirection = RANKING_METRICS[state.rankingMetric].defaultDirection;
  resetSortsForSide();
  updateDateBounds();
}

async function boot() {
  try {
    const response = await fetch("./data/site-data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`data HTTP ${response.status}`);
    state.data = await response.json();
    if (!state.data.pairs?.length) throw new Error("表示できる通貨ペアがありません。");

    $("unitLabel").textContent = Number(state.data.metadata.unit).toLocaleString("ja-JP");
    const generated = new Date(state.data.metadata.generated_at);
    $("updatedAt").textContent = generated.toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit",
    });

    setupControls();
    renderView();
  } catch (error) {
    console.error(error);
    $("errorState").hidden = false;
    $("errorState").textContent = `TrueRateの読み込みに失敗しました: ${error.message}`;
  }
}

boot();
