const state = {
  data: null,
  view: "dashboard",
  pair: null,
  side: "long",
  period: "1Y",
  customStart: null,
  brokers: new Set(),
  brokerSelectionDirty: false,
  chart: null,
  detailCharts: {},
  rankingMetric: "totalReturn",
  rankingDirection: "desc",
  arbitrageDirection: "desc",
  tableSort: { key: "total", direction: "desc" },
};

const BROKER_COLORS = {
  click365: "#c084fc",
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

function dailySwapPoints(rawPoints) {
  if (!rawPoints?.length) return [];
  const cutoff = cutoffFor(rawPoints);
  let startIndex = 0;
  if (cutoff) {
    const found = rawPoints.findIndex((point) => point.date >= cutoff);
    if (found < 0) return [];
    startIndex = found;
  }

  const result = [];
  for (let i = startIndex; i < rawPoints.length; i += 1) {
    const current = rawPoints[i];
    const previous = i > 0 ? rawPoints[i - 1] : null;
    const longSwap = previous
      ? current.cum_long_swap_jpy - previous.cum_long_swap_jpy
      : 0;
    const shortSwap = previous
      ? current.cum_short_swap_jpy - previous.cum_short_swap_jpy
      : 0;
    result.push({
      date: current.date,
      base_jpy: current.base_jpy,
      longSwap,
      shortSwap,
    });
  }
  return result;
}

function pairDailyBrokerSeries(pair = state.pair) {
  const pairSeries = state.data.series[pair] || {};
  return Object.entries(pairSeries)
    .map(([broker, item]) => ({
      broker,
      points: dailySwapPoints(item.points || []),
      rawPoints: item.points || [],
    }))
    .filter((item) => item.points.length);
}

function ensureDetailChart(id) {
  if (!window.echarts) throw new Error("EChartsを読み込めませんでした。");
  if (!state.detailCharts[id]) {
    state.detailCharts[id] = echarts.init($(id));
  }
  return state.detailCharts[id];
}

function detailLineChartOption(series, valueLabel = "JPY") {
  return {
    backgroundColor: "transparent",
    animationDuration: 200,
    grid: { left: 58, right: 20, top: 44, bottom: 42 },
    legend: {
      top: 8,
      left: 10,
      itemWidth: 18,
      itemHeight: 7,
      textStyle: { color: "#7f8d9c", fontSize: 10 },
      type: "scroll",
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "#344050", width: 1 } },
      backgroundColor: "rgba(9,13,18,.96)",
      borderColor: "#27313d",
      borderWidth: 1,
      textStyle: { color: "#e7edf4", fontSize: 11 },
      valueFormatter: (value) => `${Number(value).toFixed(2)} ${valueLabel}`,
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
      axisLabel: { color: "#667382", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(74,88,103,.16)" } },
    },
    dataZoom: [{ type: "inside", filterMode: "none" }],
    series,
  };
}

function fixedArbitrageCombinations(pair = state.pair) {
  const series = arbitragePairCandidates(pair);
  if (series.length < 2) return [];

  const legs = series.map((item) => ({
    broker: item.broker,
    points: item.points,
    long: metricsFor(item, "long"),
    short: metricsFor(item, "short"),
  })).filter((item) => item.long && item.short);

  const rows = [];
  for (const buy of legs) {
    for (const sell of legs) {
      if (buy.broker === sell.broker) continue;
      const buySwap = buy.long.cumulativeSwap;
      const sellSwap = sell.short.cumulativeSwap;
      const netSwap = buySwap + sellSwap;
      const first = buy.points[0];
      const last = buy.points.at(-1);
      const holdingDays = Math.max(1, daysBetween(first.date, last.date));
      const initialNotionalJpy = state.data.metadata.unit * first.base_jpy;
      const spreadPct = initialNotionalJpy > 0 ? (netSwap / initialNotionalJpy) * 100 : null;
      rows.push({
        buyBroker: buy.broker,
        sellBroker: sell.broker,
        buySwap,
        sellSwap,
        netSwap,
        annualizedSpread: Number.isFinite(spreadPct)
          ? spreadPct * (365 / holdingDays)
          : null,
        startDate: first.date,
        endDate: last.date,
      });
    }
  }
  return rows.sort((a, b) => b.netSwap - a.netSwap);
}

function dailyPairDispersion(pair = state.pair) {
  const brokers = pairDailyBrokerSeries(pair);
  const byDate = new Map();

  for (const item of brokers) {
    for (const point of item.points) {
      if (!byDate.has(point.date)) byDate.set(point.date, []);
      byDate.get(point.date).push({
        broker: item.broker,
        longSwap: point.longSwap,
        shortSwap: point.shortSwap,
      });
    }
  }

  const rows = [];
  for (const [date, legs] of [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (legs.length < 2) continue;
    const longValues = legs.map((x) => x.longSwap).filter(Number.isFinite);
    const shortValues = legs.map((x) => x.shortSwap).filter(Number.isFinite);
    if (!longValues.length || !shortValues.length) continue;

    let bestArb = null;
    for (const buy of legs) {
      for (const sell of legs) {
        if (buy.broker === sell.broker) continue;
        const net = buy.longSwap + sell.shortSwap;
        if (!bestArb || net > bestArb.net) {
          bestArb = {
            net,
            buyBroker: buy.broker,
            sellBroker: sell.broker,
          };
        }
      }
    }

    rows.push({
      date,
      buyRange: Math.max(...longValues) - Math.min(...longValues),
      sellRange: Math.max(...shortValues) - Math.min(...shortValues),
      arbNet: bestArb?.net ?? null,
      buyBroker: bestArb?.buyBroker ?? null,
      sellBroker: bestArb?.sellBroker ?? null,
    });
  }
  return rows;
}

function renderPairDetail() {
  const pairSeries = state.data.series[state.pair] || {};
  const brokers = pairDailyBrokerSeries();
  const rangeLabel = state.customStart ? `From ${formatDate(state.customStart)}` : state.period;
  $("pairDetailTitle").textContent = `${state.pair} · Swap detail`;
  $("pairDetailRange").textContent = rangeLabel;

  const buySeries = brokers.map((item) => ({
    name: brokerName(item.broker),
    type: "line",
    showSymbol: false,
    connectNulls: false,
    color: brokerColor(item.broker),
    lineStyle: { width: 1.7, color: brokerColor(item.broker) },
    emphasis: { focus: "series" },
    data: item.points.map((point) => [point.date, point.longSwap]),
  }));
  const sellSeries = brokers.map((item) => ({
    name: brokerName(item.broker),
    type: "line",
    showSymbol: false,
    connectNulls: false,
    color: brokerColor(item.broker),
    lineStyle: { width: 1.7, color: brokerColor(item.broker) },
    emphasis: { focus: "series" },
    data: item.points.map((point) => [point.date, point.shortSwap]),
  }));

  ensureDetailChart("buySwapChart").setOption(detailLineChartOption(buySeries), true);
  ensureDetailChart("sellSwapChart").setOption(detailLineChartOption(sellSeries), true);

  const dispersion = dailyPairDispersion();
  const spreadSeries = [
    {
      name: "Best arb net",
      type: "line",
      showSymbol: false,
      lineStyle: { width: 2.2 },
      data: dispersion.map((row) => [row.date, row.arbNet]),
    },
    {
      name: "Buy broker range",
      type: "line",
      showSymbol: false,
      lineStyle: { width: 1.4, type: "dashed" },
      data: dispersion.map((row) => [row.date, row.buyRange]),
    },
    {
      name: "Sell broker range",
      type: "line",
      showSymbol: false,
      lineStyle: { width: 1.4, type: "dashed" },
      data: dispersion.map((row) => [row.date, row.sellRange]),
    },
  ];
  ensureDetailChart("spreadChart").setOption(detailLineChartOption(spreadSeries), true);

  const combinations = fixedArbitrageCombinations();
  const best = combinations[0] || null;
  $("detailBestBuy").textContent = best ? brokerName(best.buyBroker) : "—";
  $("detailBestSell").textContent = best ? brokerName(best.sellBroker) : "—";
  $("detailNetSwap").textContent = best ? formatJpy(best.netSwap) : "—";
  $("detailNetSwap").className = best ? valueClass(best.netSwap) : "";
  $("detailAnnualizedSpread").textContent = best ? formatPct(best.annualizedSpread) : "—";
  $("detailAnnualizedSpread").className = best ? valueClass(best.annualizedSpread) : "";

  const positiveDays = dispersion.filter((row) => Number.isFinite(row.arbNet) && row.arbNet > 0).length;
  const comparableDays = dispersion.filter((row) => Number.isFinite(row.arbNet)).length;
  $("detailPositiveDays").textContent = comparableDays
    ? `${positiveDays} / ${comparableDays}`
    : "—";

  const arbBody = $("pairArbitrageBody");
  arbBody.innerHTML = "";
  combinations.slice(0, 12).forEach((rowData, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="pair-rank">#${index + 1}</td>
      <td><span class="best-broker"><span class="series-dot" style="--series-color:${brokerColor(rowData.buyBroker)}"></span>${brokerName(rowData.buyBroker)}</span></td>
      <td><span class="best-broker"><span class="series-dot" style="--series-color:${brokerColor(rowData.sellBroker)}"></span>${brokerName(rowData.sellBroker)}</span></td>
      <td class="${valueClass(rowData.buySwap)}">${formatJpy(rowData.buySwap)}</td>
      <td class="${valueClass(rowData.sellSwap)}">${formatJpy(rowData.sellSwap)}</td>
      <td class="return-value ${valueClass(rowData.netSwap)}">${formatJpy(rowData.netSwap)}</td>
      <td class="${valueClass(rowData.annualizedSpread)}">${formatPct(rowData.annualizedSpread)}</td>
      <td>${formatDate(rowData.startDate)}</td>`;
    arbBody.appendChild(row);
  });
  if (!combinations.length) {
    arbBody.innerHTML = '<tr><td colspan="8" class="ranking-empty">No cross-broker overlap for this range.</td></tr>';
  }

  const summaryBody = $("pairBrokerSummaryBody");
  summaryBody.innerHTML = "";
  const summaryRows = Object.entries(pairSeries).map(([broker, item]) => {
    const points = periodPoints(item.points || []);
    if (points.length < 2) return null;
    const rebased = rebase(points);
    if (rebased.length < 2) return null;
    const last = rebased.at(-1);
    const days = Math.max(1, daysBetween(rebased[0].date, last.date));
    return {
      broker,
      buyTotal: last.longSwapJpy,
      sellTotal: last.shortSwapJpy,
      buyAvg: last.longSwapJpy / days,
      sellAvg: last.shortSwapJpy / days,
      startDate: rebased[0].date,
    };
  }).filter(Boolean).sort((a, b) => b.buyTotal - a.buyTotal);

  summaryRows.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(item.broker)}"></span>${brokerName(item.broker)}</div></td>
      <td class="${valueClass(item.buyTotal)}">${formatJpy(item.buyTotal)}</td>
      <td class="${valueClass(item.sellTotal)}">${formatJpy(item.sellTotal)}</td>
      <td class="${valueClass(item.buyAvg)}">${formatJpy(item.buyAvg)}</td>
      <td class="${valueClass(item.sellAvg)}">${formatJpy(item.sellAvg)}</td>
      <td>${formatDate(item.startDate)}</td>`;
    summaryBody.appendChild(row);
  });

  requestAnimationFrame(() => {
    Object.values(state.detailCharts).forEach((chart) => chart.resize());
  });
}

function updatePairHash() {
  if (state.view === "pairdetail") {
    const next = `#pair=${encodeURIComponent(state.pair)}`;
    if (window.location.hash !== next) history.replaceState(null, "", next);
  } else if (window.location.hash.startsWith("#pair=")) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}

function pairFromHash() {
  const match = window.location.hash.match(/^#pair=(.+)$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

function openPairDetail(pair) {
  if (!state.data.pairs.includes(pair)) return;
  state.pair = pair;
  $("pairSelect").value = pair;
  state.view = "pairdetail";
  state.brokerSelectionDirty = false;
  updateDateBounds();
  renderView();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function defaultBrokerSelection() {
  const pairSeries = state.data.series[state.pair] || {};
  const entries = Object.entries(pairSeries);
  if (!entries.length) return new Set();

  let longestBroker = null;
  let longestDays = -1;
  let bestSwapBroker = null;
  let bestSwapPerDay = -Infinity;

  for (const [broker, item] of entries) {
    const rawPoints = item.points || [];
    if (!rawPoints.length) continue;

    const historyDays = daysBetween(rawPoints[0].date, rawPoints.at(-1).date);
    if (historyDays > longestDays) {
      longestDays = historyDays;
      longestBroker = broker;
    }

    const points = periodPoints(rawPoints);
    if (points.length < 2) continue;
    const first = points[0];
    const last = points.at(-1);
    const holdingDays = Math.max(1, daysBetween(first.date, last.date));
    const longSwapPerDay =
      (last.cum_long_swap_jpy - first.cum_long_swap_jpy) / holdingDays;
    const shortSwapPerDay =
      (last.cum_short_swap_jpy - first.cum_short_swap_jpy) / holdingDays;
    const candidateSwapPerDay =
      state.side === "long" ? longSwapPerDay :
      state.side === "short" ? shortSwapPerDay :
      Math.max(longSwapPerDay, shortSwapPerDay);

    if (Number.isFinite(candidateSwapPerDay) && candidateSwapPerDay > bestSwapPerDay) {
      bestSwapPerDay = candidateSwapPerDay;
      bestSwapBroker = broker;
    }
  }

  const selected = new Set();
  if (bestSwapBroker) selected.add(bestSwapBroker);
  if (longestBroker) selected.add(longestBroker);

  // If one broker is both best-swap and longest-history, showing one line is
  // intentional; the user can add any other broker manually.
  if (!selected.size && entries[0]) selected.add(entries[0][0]);
  return selected;
}

function resetDefaultBrokers() {
  state.brokerSelectionDirty = false;
  state.brokers = defaultBrokerSelection();
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
      state.brokerSelectionDirty = true;
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
    window.addEventListener("resize", () => {
      state.chart.resize();
      Object.values(state.detailCharts).forEach((chart) => chart.resize());
    });
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

  // Keep the longest available requested window for Ranking.
  const pairStart = candidates.map((item) => item.points[0].date).sort()[0];
  const eligible = candidates.filter((item) => item.points[0].date === pairStart);

  return eligible
    .map((item) => ({ broker: item.broker, points: rebase(item.points, pairStart) }))
    .filter((item) => item.points.length >= 2);
}

function metricComesFirst(a, b, key, best) {
  const av = a?.[key];
  const bv = b?.[key];
  if (!Number.isFinite(av)) return false;
  if (!Number.isFinite(bv)) return true;
  return best === "min" ? av < bv : av > bv;
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

function bestDirectionForPair(pair) {
  const metricDef = RANKING_METRICS[state.rankingMetric];
  const long = bestBrokerForPair(pair, "long");
  const short = bestBrokerForPair(pair, "short");
  if (!long) return short;
  if (!short) return long;
  return metricComesFirst(short, long, state.rankingMetric, metricDef.best) ? short : long;
}

function pairRankingRows(side) {
  const rows = state.data.pairs
    .map((pair) => side === "both" ? bestDirectionForPair(pair) : bestBrokerForPair(pair, side))
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

function sideBadge(side) {
  const sell = side === "short";
  return `<span class="side-badge ${sell ? "sell" : "buy"}">${sell ? "SELL" : "BUY"}</span>`;
}

function renderPairRankingColumn(side) {
  const metricDef = RANKING_METRICS[state.rankingMetric];
  const rows = pairRankingRows(side);
  const column = document.createElement("div");
  column.className = "pair-ranking-column";
  const scopeText = side === "both"
    ? `Each pair uses its best broker + BUY/SELL for ${metricDef.label}`
    : `Each pair uses its best ${side === "long" ? "BUY" : "SELL"} broker for ${metricDef.label}`;
  column.innerHTML = `
    <div class="pair-ranking-side">
      <strong>${side === "both" ? "BUY + SELL" : (side === "long" ? "BUY" : "SELL")}</strong>
      <span>${scopeText}</span>
    </div>
    <div class="table-scroll">
      <table class="pair-ranking-table">
        <thead>
          <tr>
            <th>#</th><th>Pair</th><th>Side</th><th>Best broker</th>
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
      <td>${sideBadge(metric.side)}</td>
      <td><span class="best-broker"><span class="series-dot" style="--series-color:${brokerColor(metric.broker)}"></span>${brokerName(metric.broker)}</span></td>
      <td class="metric-primary ${valueClass(metric[state.rankingMetric])}">${metricDef.format(metric[state.rankingMetric])}</td>
      <td class="${valueClass(metric.totalReturn)}">${formatPct(metric.totalReturn)}</td>
      <td class="${valueClass(metric.swapContribution)}">${formatPct(metric.swapContribution)}</td>
      <td class="${valueClass(metric.maxDrawdown)}">${formatPct(metric.maxDrawdown)}</td>
      <td>${formatPct(metric.volatility)}</td>
      <td class="coverage-note">${formatDate(metric.startDate)}</td>`;
    row.addEventListener("click", () => openPairDetail(metric.pair));
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
  content.classList.remove("both");
  content.appendChild(renderPairRankingColumn(state.side));
}

function arbitragePairCandidates(pair) {
  const pairSeries = state.data.series[pair] || {};
  const candidates = [];

  for (const [broker, item] of Object.entries(pairSeries)) {
    const points = periodPoints(item.points);
    if (points.length >= 2) candidates.push({ broker, points });
  }
  if (candidates.length < 2) return [];

  // Arbitrage legs must cover the same requested window.
  const pairStart = candidates.map((item) => item.points[0].date).sort()[0];
  const latestEnd = candidates.map((item) => item.points.at(-1).date).sort().at(-1);
  return candidates
    .filter(
      (item) => item.points[0].date === pairStart && item.points.at(-1).date === latestEnd
    )
    .map((item) => ({ broker: item.broker, points: rebase(item.points, pairStart) }))
    .filter((item) => item.points.length >= 2);
}

function arbitrageForPair(pair) {
  const series = arbitragePairCandidates(pair);
  if (series.length < 2) return null;

  const legs = series
    .map((item) => ({
      broker: item.broker,
      points: item.points,
      long: metricsFor(item, "long"),
      short: metricsFor(item, "short"),
    }))
    .filter((item) => item.long && item.short);

  let best = null;
  for (const buy of legs) {
    for (const sell of legs) {
      if (buy.broker === sell.broker) continue;

      const buySwap = buy.long.cumulativeSwap;
      const sellSwap = sell.short.cumulativeSwap;
      const netSwap = buySwap + sellSwap;
      const startPoint = buy.points[0];
      const endPoint = buy.points.at(-1);
      const holdingDays = Math.max(1, daysBetween(startPoint.date, endPoint.date));
      const initialNotionalJpy = state.data.metadata.unit * startPoint.base_jpy;
      const spreadPct = initialNotionalJpy > 0 ? (netSwap / initialNotionalJpy) * 100 : null;
      const annualizedSpread = Number.isFinite(spreadPct)
        ? spreadPct * (365 / holdingDays)
        : null;

      const candidate = {
        pair,
        buyBroker: buy.broker,
        sellBroker: sell.broker,
        buySwap,
        sellSwap,
        netSwap,
        annualizedSpread,
        startDate: startPoint.date,
        endDate: endPoint.date,
        holdingDays,
      };
      if (!best || candidate.netSwap > best.netSwap) best = candidate;
    }
  }
  return best;
}

function arbitrageRows() {
  const rows = state.data.pairs
    .map(arbitrageForPair)
    .filter(Boolean);

  rows.sort((a, b) => {
    const av = a.annualizedSpread;
    const bv = b.annualizedSpread;
    if (!Number.isFinite(av) && !Number.isFinite(bv)) return a.pair.localeCompare(b.pair);
    if (!Number.isFinite(av)) return 1;
    if (!Number.isFinite(bv)) return -1;
    return state.arbitrageDirection === "asc" ? av - bv : bv - av;
  });
  return rows;
}

function renderArbitrage() {
  const rows = arbitrageRows();
  const body = $("arbitrageBody");
  body.innerHTML = "";

  const rangeLabel = state.customStart ? `From ${formatDate(state.customStart)}` : state.period;
  $("arbitrageContext").textContent = `${rangeLabel} · best cross-broker pair`;
  $("arbitrageDirection").textContent =
    state.arbitrageDirection === "desc" ? "High → Low" : "Low → High";

  rows.forEach((item, index) => {
    const row = document.createElement("tr");
    row.title = `Open ${item.pair} in Dashboard`;
    row.innerHTML = `
      <td class="pair-rank">#${index + 1}</td>
      <td class="pair-name">${item.pair}</td>
      <td><span class="best-broker"><span class="series-dot" style="--series-color:${brokerColor(item.buyBroker)}"></span>${brokerName(item.buyBroker)}</span></td>
      <td><span class="best-broker"><span class="series-dot" style="--series-color:${brokerColor(item.sellBroker)}"></span>${brokerName(item.sellBroker)}</span></td>
      <td class="${valueClass(item.buySwap)}">${formatJpy(item.buySwap)}</td>
      <td class="${valueClass(item.sellSwap)}">${formatJpy(item.sellSwap)}</td>
      <td class="metric-primary ${valueClass(item.netSwap)}">${formatJpy(item.netSwap)}</td>
      <td class="${valueClass(item.annualizedSpread)}">${formatPct(item.annualizedSpread)}</td>
      <td class="coverage-note">${formatDate(item.startDate)}</td>`;
    row.addEventListener("click", () => openPairDetail(item.pair));
    body.appendChild(row);
  });

  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="9" class="ranking-empty">No cross-broker overlap for this range.</td></tr>';
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
  const arbitrage = state.view === "arbitrage";
  const pairdetail = state.view === "pairdetail";
  document.body.classList.toggle("ranking-mode", ranking);
  document.body.classList.toggle("arbitrage-mode", arbitrage);
  document.body.classList.toggle("pair-detail-mode", pairdetail);
  $("dashboardView").hidden = ranking || arbitrage || pairdetail;
  $("rankingView").hidden = !ranking;
  $("arbitrageView").hidden = !arbitrage;
  $("pairDetailView").hidden = !pairdetail;
  $("pairField").hidden = ranking || arbitrage;
  $("sideField").hidden = arbitrage || pairdetail;
  $("brokerFilterStrip").hidden = ranking || arbitrage || pairdetail;

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });

  renderPeriodState();
  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.side === state.side);
  });

  updateDateBounds();
  updatePairHash();
  if (ranking) {
    renderPairRanking();
  } else if (arbitrage) {
    renderArbitrage();
  } else if (pairdetail) {
    renderPairDetail();
  } else {
    renderDashboard();
    requestAnimationFrame(() => state.chart?.resize());
  }
}

function openPairInDashboard(pair) {
  state.pair = pair;
  $("pairSelect").value = pair;
  state.view = "dashboard";
  resetDefaultBrokers();
  updateDateBounds();
  resetSortsForSide();
  renderView();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateDateBounds() {
  const input = $("customStartDate");
  const starts = [];
  const ends = [];

  if (state.view === "ranking" || state.view === "arbitrage") {
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
  const hashedPair = pairFromHash();
  state.pair = hashedPair && state.data.pairs.includes(hashedPair)
    ? hashedPair
    : (preferred.find((pair) => state.data.pairs.includes(pair)) || state.data.pairs[0]);
  if (hashedPair && state.data.pairs.includes(hashedPair)) state.view = "pairdetail";
  pairSelect.value = state.pair;
  resetDefaultBrokers();

  pairSelect.addEventListener("change", () => {
    state.pair = pairSelect.value;
    state.customStart = null;
    $("customStartDate").value = "";
    resetDefaultBrokers();
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
      if (state.view === "dashboard" && !state.brokerSelectionDirty) {
        state.brokers = defaultBrokerSelection();
      }
      renderView();
    });
  });

  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      state.customStart = null;
      $("customStartDate").value = "";
      if (state.view === "dashboard" && !state.brokerSelectionDirty) {
        state.brokers = defaultBrokerSelection();
      }
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

  $("arbitrageDirection").addEventListener("click", () => {
    state.arbitrageDirection = state.arbitrageDirection === "desc" ? "asc" : "desc";
    renderArbitrage();
  });

  $("customStartDate").addEventListener("change", (event) => {
    state.customStart = event.target.value || null;
    if (!state.customStart) state.period = "1Y";
    if (state.view === "dashboard" && !state.brokerSelectionDirty) {
      state.brokers = defaultBrokerSelection();
    }
    renderView();
  });

  $("clearCustomDate").addEventListener("click", () => {
    state.customStart = null;
    state.period = "1Y";
    $("customStartDate").value = "";
    if (state.view === "dashboard" && !state.brokerSelectionDirty) {
      state.brokers = defaultBrokerSelection();
    }
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
    window.addEventListener("hashchange", () => {
      const pair = pairFromHash();
      if (pair && state.data.pairs.includes(pair)) {
        state.pair = pair;
        $("pairSelect").value = pair;
        state.view = "pairdetail";
        renderView();
      }
    });
    renderView();
  } catch (error) {
    console.error(error);
    $("errorState").hidden = false;
    $("errorState").textContent = `TrueRateの読み込みに失敗しました: ${error.message}`;
  }
}

boot();
