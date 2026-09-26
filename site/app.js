const state = {
  data: null,
  pair: null,
  side: "long",
  period: "1Y",
  brokers: new Set(),
  chart: null,
};

const $ = (id) => document.getElementById(id);

function brokerName(id) {
  return state.data.brokers.find((broker) => broker.id === id)?.name || id;
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
  return "";
}

function cutoffFor(points) {
  if (!points.length || state.period === "MAX") return null;
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

function activeBrokerSeries() {
  const candidates = activeBrokerCandidates();
  if (!candidates.length) return [];

  // Broker-to-broker comparison uses one identical visible holding period.
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

function longestSpotReference() {
  const candidates = activeBrokerCandidates();
  if (!candidates.length) return [];

  // Spot-only is independent from the broker overlap window. Use the active
  // broker with the earliest available date so MAX can always show the
  // longest available market-only history.
  const longest = candidates.reduce((best, item) => {
    if (!best) return item;
    return item.points[0].date < best.points[0].date ? item : best;
  }, null);

  return rebase(longest.points);
}

function renderBrokerButtons() {
  const pairSeries = state.data.series[state.pair] || {};
  const container = $("brokerButtons");
  container.innerHTML = "";

  for (const broker of state.data.brokers) {
    if (!pairSeries[broker.id]) continue;
    const button = document.createElement("button");
    button.textContent = broker.name;
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

function renderMetrics(series) {
  const container = $("metrics");
  container.innerHTML = "";
  if (!series.length) return;

  const metrics = [];
  for (const item of series) {
    const last = item.points[item.points.length - 1];
    const name = brokerName(item.broker);

    if (state.side === "long" || state.side === "both") {
      metrics.push({
        label: `${name} Long`,
        value: last.longIndex - 100,
        display: formatPct(last.longIndex - 100),
        sub: `Swap ${formatJpy(last.longSwapJpy)} · 為替 + 買いスワップ`,
      });
    }
    if (state.side === "short" || state.side === "both") {
      metrics.push({
        label: `${name} Short`,
        value: last.shortIndex - 100,
        display: formatPct(last.shortIndex - 100),
        sub: `Swap ${formatJpy(last.shortSwapJpy)} · 為替 + 売りスワップ`,
      });
    }
  }

  for (const metric of metrics) {
    const card = document.createElement("article");
    card.className = "metric card";
    card.innerHTML = `
      <div class="label">${metric.label}</div>
      <div class="value ${valueClass(metric.value)}">${metric.display}</div>
      <div class="sub">${metric.sub}</div>
    `;
    container.appendChild(card);
  }
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
    if (state.side === "long" || state.side === "both") {
      chartSeries.push({
        name: `${name} Long`,
        type: "line",
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 2.4 },
        data: item.points.map((point) => [point.date, point.longIndex]),
      });
    }
    if (state.side === "short" || state.side === "both") {
      chartSeries.push({
        name: `${name} Short`,
        type: "line",
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 2.1, type: "dashed" },
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
        lineStyle: { width: 1.4, type: "dotted", opacity: 0.75 },
        data: spotReference.map((point) => [point.date, point.spotLongIndex]),
      });
    }
    if (state.side === "short" || state.side === "both") {
      chartSeries.push({
        name: state.side === "both" ? "Spot only Short" : "Spot only",
        type: "line",
        showSymbol: false,
        lineStyle: { width: 1.4, type: "dotted", opacity: 0.75 },
        data: spotReference.map((point) => [point.date, point.spotShortIndex]),
      });
    }
  }

  state.chart.setOption(
    {
      backgroundColor: "transparent",
      animationDuration: 350,
      color: ["#72f0c4", "#74b9ff", "#ffb86c", "#c7a6ff", "#ff8e9e", "#88d498"],
      grid: { left: 58, right: 22, top: 62, bottom: 52 },
      legend: {
        top: 12,
        left: 8,
        textStyle: { color: "#9db2bf" },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#0a151e",
        borderColor: "rgba(164,196,217,.22)",
        textStyle: { color: "#eef6fb" },
        valueFormatter: (value) => Number(value).toFixed(2),
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: "rgba(164,196,217,.18)" } },
        axisLabel: { color: "#78909e" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: {
          color: "#78909e",
          formatter: (value) => value.toFixed(1),
        },
        splitLine: { lineStyle: { color: "rgba(164,196,217,.08)" } },
      },
      series: chartSeries,
    },
    true
  );
}

function render() {
  renderBrokerButtons();
  const series = activeBrokerSeries();
  const spotReference = longestSpotReference();
  renderMetrics(series);
  renderChart(series, spotReference);
  $("chartTitle").textContent = `${state.pair} · ${state.side.toUpperCase()} · ${state.period}`;

  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.side === state.side);
  });
  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.period === state.period);
  });
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

  const preferred = ["USD/JPY", "TRY/JPY", "USD/CHF"];
  state.pair = preferred.find((pair) => state.data.pairs.includes(pair)) || state.data.pairs[0];
  pairSelect.value = state.pair;
  pairSelect.addEventListener("change", () => {
    state.pair = pairSelect.value;
    const available = Object.keys(state.data.series[state.pair] || {});
    state.brokers = new Set(available);
    render();
  });

  document.querySelectorAll("#sideButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.side = button.dataset.side;
      render();
    });
  });

  document.querySelectorAll("#periodButtons button").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      render();
    });
  });

  const initialBrokers = Object.keys(state.data.series[state.pair] || {});
  state.brokers = new Set(initialBrokers);
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
