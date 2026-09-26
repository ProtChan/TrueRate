const state = {
  data: null,
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
  gaitame_com: "#57e3b4",
  gmo_gaika: "#60a5fa",
  gmo_click: "#f2b45f",
  triauto: "#b991ff",
};

const SPOT_COLOR = "#94a3b8";

const RANKING_METRICS = {
  totalReturn: {
    label: "Total Return",
    defaultDirection: "desc",
    format: formatPct,
  },
  annualizedReturn: {
    label: "Annualized Return",
    defaultDirection: "desc",
    format: formatPct,
  },
  swapContribution: {
    label: "Swap Contribution",
    defaultDirection: "desc",
    format: formatPct,
  },
  annualizedSwap: {
    label: "Annualized Swap",
    defaultDirection: "desc",
    format: formatPct,
  },
  maxDrawdown: {
    label: "Max Drawdown",
    defaultDirection: "desc",
    format: formatPct,
  },
  volatility: {
    label: "Volatility",
    defaultDirection: "asc",
    format: formatPct,
  },
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
  const startMs = Date.parse(`${start}T00:00:00Z`);
  const endMs = Date.parse(`${end}T00:00:00Z`);
  return Math.max(0, Math.round((endMs - startMs) / 86400000));
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

function rebase(points, commonStartDate = null) {
  if (!points?.length) return [];
  const aligned = commonStartDate
    ? points.filter((point) => point.date >= commonStartDate)
    : points;
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

  const commonStartDate = candidates
    .map((item) => item.points[0].date)
    .sort()
    .at(-1);

  return candidates
    .map((item) => ({
      broker: item.broker,
      points: rebase(item.points, commonStartDate),
    }))
    .filter((item) => item.points.length);
}

function chartBrokerSeries() {
  return activeBrokerCandidates()
    .map((item) => ({
      broker: item.broker,
      points: rebase(item.points),
    }))
    .filter((item) => item.points.length);
}

function longestSpotReference() {
  const candidates = activeBrokerCandidates();
  if (!candidates.length) return [];

  const oldestBrokerStart = candidates
    .map((item) => item.points[0].date)
    .sort()[0];

  const longest = candidates.reduce((best, item) => {
    if (!best) return item;
    return item.points[0].date < best.points[0].date ? item : best;
  }, null);

  const clamped = longest.points.filter((point) => point.date >= oldestBrokerStart);
  return rebase(clamped);
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
  const points = item.points;
  const keys = sideKeys(side);
  if (!points.length) return null;

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
      render();
    });

    container.appendChild(button);
  }
}

function renderRangeSummary(chartSeries, comparisonSeries, spotReference) {
  const comparison = $("comparisonRange");
  const spot = $("spotRange");

  if (chartSeries.length) {
    const starts = chartSeries.map((item) => item.points[0]?.date).filter(Boolean).sort();
    const ends = chartSeries.map((item) => item.points.at(-1)?.date).filter(Boolean).sort();
    const chartStart = starts[0];
    const chartEnd = ends.at(-1);
    comparison.textContent = `Chart  ${formatDate(chartStart)} → ${formatDate(chartEnd)}`;
  } else {
    comparison.textContent = "Chart —";
  }

  if (comparisonSeries.length) {
    const start = comparisonSeries[0].points[0]?.date;
    const end = comparisonSeries[0].points.at(-1)?.date;
    spot.textContent = `Comparison  ${formatDate(start)} → ${formatDate(end)}`;
  } else if (spotReference.length) {
    const start = spotReference[0]?.date;
    const end = spotReference.at(-1)?.date;
    spot.textContent = `Spot  ${formatDate(start)} → ${formatDate(end)}`;
  } else {
    spot.textContent = "";
  }
}

function defaultRankingDirection(metric) {
  return RANKING_METRICS[metric]?.defaultDirection || "desc";
}

function rankingRows(series, side) {
  return series
    .map((item) => metricsFor(item, side))
    .filter(Boolean)
    .sort((a, b) => {
      const key = state.rankingMetric;
      const av = a[key];
      const bv = b[key];
      if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
      if (!Number.isFinite(av)) return 1;
      if (!Number.isFinite(bv)) return -1;
      return state.rankingDirection === "asc" ? av - bv : bv - av;
    });
}

function renderRankingColumn(side, series) {
  const metric = RANKING_METRICS[state.rankingMetric];
  const rows = rankingRows(series, side);
  const column = document.createElement("div");
  column.className = "ranking-column";
  column.innerHTML = `
    <div class="ranking-column-header">
      <strong>${side.toUpperCase()}</strong>
      <span>${metric.label}</span>
    </div>
    <ol class="ranking-list"></ol>
  `;

  const list = column.querySelector(".ranking-list");
  rows.forEach((row, index) => {
    const item = document.createElement("li");
    item.className = "ranking-row";
    const value = row[state.rankingMetric];
    item.innerHTML = `
      <span class="rank-number">#${index + 1}</span>
      <div class="ranking-broker">
        <span class="series-dot" style="--series-color:${brokerColor(row.broker)}"></span>
        <span>${brokerName(row.broker)}</span>
      </div>
      <span class="ranking-value ${valueClass(value)}">${metric.format(value)}</span>
    `;
    list.appendChild(item);
  });

  return column;
}

function renderRanking(series) {
  const tabs = document.querySelectorAll("#rankingTabs button");
  tabs.forEach((button) => {
    button.classList.toggle("active", button.dataset.rankingMetric === state.rankingMetric);
  });

  const metric = RANKING_METRICS[state.rankingMetric];
  $("rankingDirection").textContent = state.rankingDirection === "desc"
    ? "High → Low"
    : "Low → High";
  $("rankingContext").textContent = `${state.pair} · ${state.side.toUpperCase()} · ${metric.label}`;

  const content = $("rankingContent");
  content.innerHTML = "";
  content.classList.toggle("both", state.side === "both");

  if (state.side === "both") {
    content.appendChild(renderRankingColumn("long", series));
    content.appendChild(renderRankingColumn("short", series));
  } else {
    content.appendChild(renderRankingColumn(state.side, series));
  }
}

function sortMetrics(rows, key, direction) {
  return rows.slice().sort((a, b) => {
    if (key === "broker") {
      const av = brokerName(a.broker);
      const bv = brokerName(b.broker);
      return direction === "asc"
        ? av.localeCompare(bv, "ja")
        : bv.localeCompare(av, "ja");
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
  return `
    <button class="sort-header-button ${active ? "active-sort" : ""}" data-table-sort="${key}">
      ${label}<span class="sort-marker">${marker}</span>
    </button>
  `;
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
      render();
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
        since: long.startDate,
        startDate: long.startDate,
      };
    });

    const sorted = sortMetrics(rows, state.tableSort.key, state.tableSort.direction);

    head.innerHTML = `
      <tr>
        <th>${sortHeader("Broker", "broker")}</th>
        <th>${sortHeader("Long return", "longReturn")}</th>
        <th>${sortHeader("Short return", "shortReturn")}</th>
        <th>${sortHeader("Long swap", "longSwap")}</th>
        <th>${sortHeader("Short swap", "shortSwap")}</th>
        <th>${sortHeader("Since", "since")}</th>
      </tr>
    `;

    for (const rowData of sorted) {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(rowData.broker)}"></span>${brokerName(rowData.broker)}</div></td>
        <td class="return-value ${valueClass(rowData.longReturn)}">${formatPct(rowData.longReturn)}</td>
        <td class="return-value ${valueClass(rowData.shortReturn)}">${formatPct(rowData.shortReturn)}</td>
        <td class="${valueClass(rowData.longSwap)}">${formatJpy(rowData.longSwap)}</td>
        <td class="${valueClass(rowData.shortSwap)}">${formatJpy(rowData.shortSwap)}</td>
        <td>${formatDate(rowData.startDate)}</td>
      `;
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
        <td class="neutral">—</td>
        <td class="neutral">—</td>
        <td>${formatDate(spotReference[0].date)}</td>
      `;
      body.appendChild(row);
    }

    bindTableSort();
    return;
  }

  const metrics = series
    .map((item) => metricsFor(item, state.side))
    .filter(Boolean);
  const sortKeyMap = {
    total: "totalReturn",
    spot: "spotReturn",
    swapContribution: "swapContribution",
    cumulativeSwap: "cumulativeSwap",
    since: "since",
    broker: "broker",
  };
  const mappedSortKey = sortKeyMap[state.tableSort.key] || state.tableSort.key;
  const sorted = sortMetrics(metrics, mappedSortKey, state.tableSort.direction);

  head.innerHTML = `
    <tr>
      <th>${sortHeader("Broker", "broker")}</th>
      <th>${sortHeader("Total return", "total")}</th>
      <th>${sortHeader("Spot return", "spot")}</th>
      <th>${sortHeader("Swap contribution", "swapContribution")}</th>
      <th>${sortHeader("Cumulative swap", "cumulativeSwap")}</th>
      <th>${sortHeader("Since", "since")}</th>
    </tr>
  `;

  for (const metric of sorted) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(metric.broker)}"></span>${brokerName(metric.broker)}</div></td>
      <td class="return-value ${valueClass(metric.totalReturn)}">${formatPct(metric.totalReturn)}</td>
      <td class="${valueClass(metric.spotReturn)}">${formatPct(metric.spotReturn)}</td>
      <td class="${valueClass(metric.swapContribution)}">${formatPct(metric.swapContribution)}</td>
      <td class="${valueClass(metric.cumulativeSwap)}">${formatJpy(metric.cumulativeSwap)}</td>
      <td>${formatDate(metric.startDate)}</td>
    `;
    body.appendChild(row);
  }

  if (spotReference.length) {
    const last = spotReference.at(-1);
    const spotKey = state.side === "long" ? "spotLongIndex" : "spotShortIndex";
    const spotReturn = last[spotKey] - 100;
    const row = document.createElement("tr");
    row.className = "benchmark-row";
    row.innerHTML = `
      <td><div class="broker-cell"><span class="series-dot" style="--series-color:${SPOT_COLOR}"></span>Spot only</div></td>
      <td class="return-value ${valueClass(spotReturn)}">${formatPct(spotReturn)}</td>
      <td class="${valueClass(spotReturn)}">${formatPct(spotReturn)}</td>
      <td class="neutral">0.00%</td>
      <td class="neutral">—</td>
      <td>${formatDate(spotReference[0].date)}</td>
    `;
    body.appendChild(row);
  }

  bindTableSort();
}

function renderChart(series, spotReference) {
  if (!window.echarts) {
    throw new Error("EChartsを読み込めませんでした。ネットワーク接続を確認してください。");
  }
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
        name: `${name} Long`,
        type: "line",
        showSymbol: false,
        smooth: false,
        color,
        lineStyle: { width: 2.2, color },
        emphasis: { focus: "series" },
        data: item.points.map((point) => [point.date, point.longIndex]),
      });
    }

    if (state.side === "short" || state.side === "both") {
      chartSeries.push({
        name: `${name} Short`,
        type: "line",
        showSymbol: false,
        smooth: false,
        color,
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
        type: "line",
        showSymbol: false,
        color: SPOT_COLOR,
        lineStyle: { width: 1.5, type: "dotted", color: SPOT_COLOR, opacity: 0.9 },
        data: spotReference.map((point) => [point.date, point.spotLongIndex]),
      });
    }

    if (state.side === "short" || state.side === "both") {
      chartSeries.push({
        name: state.side === "both" ? "Spot only Short" : "Spot only",
        type: "line",
        showSymbol: false,
        color: SPOT_COLOR,
        lineStyle: { width: 1.5, type: "dotted", color: SPOT_COLOR, opacity: 0.9 },
        data: spotReference.map((point) => [point.date, point.spotShortIndex]),
      });
    }
  }

  state.chart.setOption(
    {
      backgroundColor: "transparent",
      animationDuration: 240,
      grid: { left: 62, right: 24, top: 56, bottom: 48 },
      legend: {
        top: 10,
        left: 14,
        itemWidth: 20,
        itemHeight: 7,
        textStyle: { color: "#7f8d9c", fontSize: 11 },
        inactiveColor: "#3f4a56",
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: "#344050", width: 1 } },
        backgroundColor: "rgba(9, 13, 18, 0.96)",
        borderColor: "#27313d",
        borderWidth: 1,
        textStyle: { color: "#e7edf4", fontSize: 11 },
        extraCssText: "box-shadow:0 14px 34px rgba(0,0,0,.32);border-radius:7px;",
        valueFormatter: (value) => Number(value).toFixed(2),
      },
      xAxis: {
        type: "time",
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#24303b" } },
        axisTick: { show: false },
        axisLabel: { color: "#667382", fontSize: 10, hideOverlap: true },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: "#667382",
          fontSize: 10,
          formatter: (value) => value.toFixed(1),
        },
        splitLine: { lineStyle: { color: "rgba(74, 88, 103, 0.16)" } },
      },
      dataZoom: [
        {
          type: "inside",
          filterMode: "none",
          zoomOnMouseWheel: false,
          moveOnMouseMove: true,
          moveOnMouseWheel: false,
        },
      ],
      series: chartSeries,
    },
    true
  );
}

function renderPeriodState() {
  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.classList.toggle(
      "active",
      !state.customStart && button.dataset.period === state.period
    );
  });
}

function resetSortsForSide() {
  state.tableSort = state.side === "both"
    ? { key: "longReturn", direction: "desc" }
    : { key: "total", direction: "desc" };
}

function render() {
  renderBrokerButtons();
  renderPeriodState();

  const comparisonSeries = comparisonBrokerSeries();
  const chartSeries = chartBrokerSeries();
  const spotReference = longestSpotReference();

  renderRanking(comparisonSeries);
  renderPerformanceTable(comparisonSeries, spotReference);
  renderChart(chartSeries, spotReference);
  renderRangeSummary(chartSeries, comparisonSeries, spotReference);

  const rangeLabel = state.customStart
    ? `From ${formatDate(state.customStart)}`
    : state.period;
  $("chartTitle").textContent = `${state.pair} · ${state.side.toUpperCase()} · ${rangeLabel}`;

  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.side === state.side);
  });
}

function updateDateBounds() {
  const pairSeries = state.data.series[state.pair] || {};
  const starts = [];
  const ends = [];

  for (const item of Object.values(pairSeries)) {
    if (item?.points?.length) {
      starts.push(item.points[0].date);
      ends.push(item.points.at(-1).date);
    }
  }

  const input = $("customStartDate");
  input.min = starts.length ? starts.sort()[0] : "";
  input.max = ends.length ? ends.sort().at(-1) : "";
}

function setupControls() {
  const pairSelect = $("pairSelect");
  pairSelect.innerHTML = "";

  for (const pair of state.data.pairs) {
    const option = document.createElement("option");
    option.value = pair;
    option.textContent = pair;
    pairSelect.appendChild(option);
  }

  const preferred = ["USD/JPY", "TRY/JPY", "CHF/TRY", "USD/CHF"];
  state.pair = preferred.find((pair) => state.data.pairs.includes(pair)) || state.data.pairs[0];
  pairSelect.value = state.pair;

  pairSelect.addEventListener("change", () => {
    state.pair = pairSelect.value;
    state.customStart = null;
    $("customStartDate").value = "";
    const available = Object.keys(state.data.series[state.pair] || {});
    state.brokers = new Set(available);
    updateDateBounds();
    resetSortsForSide();
    render();
  });

  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.side = button.dataset.side;
      resetSortsForSide();
      render();
    });
  });

  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      state.customStart = null;
      $("customStartDate").value = "";
      render();
    });
  });

  document.querySelectorAll("#rankingTabs button").forEach((button) => {
    button.addEventListener("click", () => {
      state.rankingMetric = button.dataset.rankingMetric;
      state.rankingDirection = defaultRankingDirection(state.rankingMetric);
      render();
    });
  });

  $("rankingDirection").addEventListener("click", () => {
    state.rankingDirection = state.rankingDirection === "desc" ? "asc" : "desc";
    render();
  });

  $("customStartDate").addEventListener("change", (event) => {
    const value = event.target.value;
    state.customStart = value || null;
    if (!value) state.period = "1Y";
    render();
  });

  $("clearCustomDate").addEventListener("click", () => {
    state.customStart = null;
    state.period = "1Y";
    $("customStartDate").value = "";
    render();
  });

  const initialBrokers = Object.keys(state.data.series[state.pair] || {});
  state.brokers = new Set(initialBrokers);
  updateDateBounds();
  state.rankingDirection = defaultRankingDirection(state.rankingMetric);
  resetSortsForSide();
}

async function boot() {
  try {
    const response = await fetch("./data/site-data.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`data HTTP ${response.status}`);
    state.data = await response.json();

    if (!state.data.pairs?.length) {
      throw new Error("表示できる通貨ペアがまだありません。データ更新workflowを実行してください。");
    }

    $("unitLabel").textContent = Number(state.data.metadata.unit).toLocaleString("ja-JP");
    const generated = new Date(state.data.metadata.generated_at);
    $("updatedAt").textContent = generated.toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });

    setupControls();
    render();
  } catch (error) {
    console.error(error);
    const box = $("errorState");
    box.hidden = false;
    box.textContent = `TrueRateの読み込みに失敗しました: ${error.message}`;
  }
}

boot();
