const state = {
  data: null,
  pair: null,
  side: "long",
  period: "1Y",
  customStart: null,
  brokers: new Set(),
  chart: null,
};

const BROKER_COLORS = {
  gaitame_com: "#57e3b4",
  gmo_gaika: "#60a5fa",
  gmo_click: "#f2b45f",
  triauto: "#b991ff",
};

const SPOT_COLOR = "#94a3b8";

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

function activeBrokerSeries() {
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

function longestSpotReference() {
  const candidates = activeBrokerCandidates();
  if (!candidates.length) return [];

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

function renderRangeSummary(series, spotReference) {
  const comparison = $("comparisonRange");
  const spot = $("spotRange");

  if (series.length) {
    const start = series[0].points[0]?.date;
    const end = series[0].points.at(-1)?.date;
    comparison.textContent = `Brokers  ${formatDate(start)} → ${formatDate(end)}`;
  } else {
    comparison.textContent = "Brokers —";
  }

  if (spotReference.length) {
    const start = spotReference[0]?.date;
    const end = spotReference.at(-1)?.date;
    spot.textContent = `Spot  ${formatDate(start)} → ${formatDate(end)}`;
  } else {
    spot.textContent = "";
  }
}

function renderPerformanceTable(series, spotReference) {
  const head = $("performanceHead");
  const body = $("performanceBody");
  head.innerHTML = "";
  body.innerHTML = "";

  if (state.side === "both") {
    head.innerHTML = `
      <tr>
        <th>Broker</th>
        <th>Long return</th>
        <th>Short return</th>
        <th>Long swap</th>
        <th>Short swap</th>
        <th>Since</th>
      </tr>
    `;

    for (const item of series) {
      const last = item.points.at(-1);
      const row = document.createElement("tr");
      row.innerHTML = `
        <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(item.broker)}"></span>${brokerName(item.broker)}</div></td>
        <td class="return-value ${valueClass(last.longIndex - 100)}">${formatPct(last.longIndex - 100)}</td>
        <td class="return-value ${valueClass(last.shortIndex - 100)}">${formatPct(last.shortIndex - 100)}</td>
        <td class="${valueClass(last.longSwapJpy)}">${formatJpy(last.longSwapJpy)}</td>
        <td class="${valueClass(last.shortSwapJpy)}">${formatJpy(last.shortSwapJpy)}</td>
        <td>${formatDate(item.points[0].date)}</td>
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
    return;
  }

  const sideKey = state.side === "long"
    ? { index: "longIndex", spot: "spotLongIndex", swap: "longSwapJpy" }
    : { index: "shortIndex", spot: "spotShortIndex", swap: "shortSwapJpy" };

  head.innerHTML = `
    <tr>
      <th>Broker</th>
      <th>Total return</th>
      <th>Spot return</th>
      <th>Swap contribution</th>
      <th>Cumulative swap</th>
      <th>Since</th>
    </tr>
  `;

  for (const item of series) {
    const last = item.points.at(-1);
    const total = last[sideKey.index] - 100;
    const spotReturn = last[sideKey.spot] - 100;
    const swapContribution = total - spotReturn;
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><div class="broker-cell"><span class="series-dot" style="--series-color:${brokerColor(item.broker)}"></span>${brokerName(item.broker)}</div></td>
      <td class="return-value ${valueClass(total)}">${formatPct(total)}</td>
      <td class="${valueClass(spotReturn)}">${formatPct(spotReturn)}</td>
      <td class="${valueClass(swapContribution)}">${formatPct(swapContribution)}</td>
      <td class="${valueClass(last[sideKey.swap])}">${formatJpy(last[sideKey.swap])}</td>
      <td>${formatDate(item.points[0].date)}</td>
    `;
    body.appendChild(row);
  }

  if (spotReference.length) {
    const last = spotReference.at(-1);
    const spotReturn = last[sideKey.spot] - 100;
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

function render() {
  renderBrokerButtons();
  renderPeriodState();

  const series = activeBrokerSeries();
  const spotReference = longestSpotReference();

  renderPerformanceTable(series, spotReference);
  renderChart(series, spotReference);
  renderRangeSummary(series, spotReference);

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
      state.customStart = null;
      $("customStartDate").value = "";
      render();
    });
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
