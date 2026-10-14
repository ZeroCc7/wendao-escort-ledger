const icon = (name) => `<img src="${window.ESCORT_ICONS?.[name] || ""}" alt="">`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const fmt = (value) => Number(value || 0).toLocaleString("zh-CN");
const time = (seconds) => {
  if (seconds == null) return "—";
  const n = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(n / 3600)).padStart(2, "0")}:${String(Math.floor(n % 3600 / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
};
const durationShort = (seconds) => seconds == null ? "—" : `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
const zeroTotals = {coins: 0, vouchers: 0, completed_rounds: 0, elapsed_seconds: 0, average_seconds: 0, coins_per_hour: 0, vouchers_per_hour: 0, luck_count: 0, luck_rounds: 0};
const today = new Date().toLocaleDateString("sv-SE");
const previewState = {game_dir: "D:\\asktao", chat_dir: "D:\\asktao\\chat", chat_exists: true, auto_scan: false, days: [], selected_day: today, day: null, history: []};
let data = previewState;
let page = "overview";
let detail = "roles";
let roundRole = "all";
let selectedTeam = "all";
let chartMode = "duration";
let earningsUnit = "coins";
let chartSelection = null;
let historyRange = "30d";
let historyView = "bars";
let historyMetric = "rounds";
let selectedLog = null;
let busy = false;

const content = document.getElementById("content");
const statusLine = document.getElementById("status-line");
const roleDialog = document.getElementById("role-dialog");
document.querySelectorAll('img[src^="icons/"]').forEach(image => {
  const name = image.getAttribute("src").split("/").pop().replace(/\.svg$/, "");
  image.src = window.ESCORT_ICONS?.[name] || "";
});

function setStatus(message) {
  statusLine.textContent = message;
}

function dateOptions() {
  if (!data.days.length) return `<option value="${esc(data.selected_day)}">${esc(data.selected_day)}</option>`;
  return data.days.map(day => `<option value="${esc(day)}" ${day === data.selected_day ? "selected" : ""}>${esc(day)}</option>`).join("");
}

function dateSelect() {
  return `<select id="day-select" class="day-select" aria-label="选择统计日期" ${data.days.length ? "" : "disabled"}>${dateOptions()}</select>`;
}

function currentView() {
  return (data.day?.teams || []).find(team => team.id === selectedTeam) || data.day;
}

function teamSelect() {
  const teams = data.day?.teams || [];
  return `<select id="team-select" class="day-select" aria-label="选择队伍" ${teams.length ? "" : "disabled"}><option value="all">全部队伍（${teams.length}）</option>${teams.map(team => `<option value="${team.id}" ${selectedTeam === team.id ? "selected" : ""}>${esc(team.name)} · ${team.logs.length} 人 · ${team.started_at.slice(11, 16)}${team.leader_name ? ` · 队长 ${esc(team.leader_name)}` : ""}</option>`).join("")}</select>`;
}

function filters() {
  return `<div class="view-filters">${dateSelect()}${teamSelect()}</div>`;
}

function roleLabel(role) {
  return `${selectedTeam === "all" ? `${esc(role.team_name)} · ` : ""}${esc(displayName(role))}`;
}

function displayName(role) {
  return role.character_name ? `${role.character_name}（角色${role.role_id}${role.name_source === "队伍排除" ? "·推定" : ""}）` : `角色${role.role_id}`;
}

function extraDetail(turn) {
  const items = new Map();
  for (const reward of turn.pirate_rewards || []) items.set(reward.reward, (items.get(reward.reward) || 0) + 1);
  const parts = [...items].map(([name, count]) => `瓢把子：${name}${count > 1 ? `×${count}` : ""}`);
  if (turn.reputation) parts.push(`声望+${turn.reputation}`);
  if (turn.medicine_count) parts.push(`药品×${turn.medicine_count}`);
  if (turn.talisman_durability) parts.push(`八卦耐久−${turn.talisman_durability}`);
  if (turn.encounters) parts.push(`震慑触发${turn.encounters}次`);
  return parts.join("、");
}

function sectionHeading(title, symbol, trailing = "") {
  return `<div class="section-bar"><h2><span class="heading-icon">${icon(symbol)}</span>${title}</h2>${trailing}</div>`;
}

function metric(label, value, unit, sub, symbol) {
  return `<div class="metric metric-${symbol}"><img class="metric-icon" src="art/icon-${symbol}.png" alt=""><div class="metric-copy"><div class="metric-label">${label}</div><div class="metric-value">${value}<small> ${unit}</small></div><div class="metric-sub">${sub}</div></div></div>`;
}

function durationChart(rounds) {
  const completed = rounds.filter(round => round.seconds != null);
  if (!completed.length) return `<div class="chart-empty chart-empty-duration"><img src="art/timer.webp" alt=""><strong>暂无耗时数据</strong><span>扫描日志后自动生成趋势图</span></div><div class="chart-legend"><span><i></i>普通趟次</span><span class="gold"><i></i>选择碰碰运气</span></div>`;
  const max = Math.max(300, ...completed.map(round => round.seconds));
  const bars = completed.map((round, index) => {
    const blessed = round.luck_selected;
    const height = Math.max(2, round.seconds / max * 100);
    return `<button type="button" class="duration-bar ${blessed ? "blessed" : ""} ${chartSelection === index ? "selected" : ""}" data-chart-point="${index}" style="height:${height.toFixed(1)}%" aria-label="${esc(round.team_name)} 第${round.number}趟，耗时${durationShort(round.seconds)}${blessed ? "，选择碰碰运气" : ""}" title="点击查看第${round.number}趟耗时">${index === 0 || index === completed.length - 1 || (index + 1) % 4 === 0 ? `<span>${round.number}</span>` : ""}</button>`;
  }).join("");
  const average = completed.reduce((sum, round) => sum + round.seconds, 0) / completed.length;
  const chosen = completed[chartSelection];
  return `<div class="chart-insight"><span>已完成 <strong>${completed.length}</strong> 趟</span><span>平均耗时 <strong>${durationShort(average)}</strong></span><span>最短 <strong>${durationShort(Math.min(...completed.map(round => round.seconds)))}</strong></span></div><div class="duration-chart" aria-label="${completed.length}趟押镖耗时图"><div class="duration-axis"><span>${Math.ceil(max / 60)}分</span><span>${Math.round(max / 120)}分</span><span>0</span></div><div class="duration-plot" style="grid-template-columns:repeat(${completed.length},minmax(0,1fr))">${bars}</div></div><div class="chart-legend"><span><i></i>普通趟次</span><span class="gold"><i></i>选择碰碰运气</span></div>${chosen ? `<div class="chart-point-detail"><span>${esc(chosen.team_name)} · 第${chosen.number}趟</span><strong>耗时 ${durationShort(chosen.seconds)}</strong><small>${chosen.luck_selected ? "选择碰碰运气" : "普通收益"}</small></div>` : `<div class="chart-point-hint">点击柱子查看每趟准确耗时</div>`}`;
}

function gradeChart(rounds) {
  const completed = rounds.filter(round => round.settled_at);
  if (!completed.length) return `<div class="chart-empty"><img src="art/icon-flag.png" alt=""><strong>暂无镖级数据</strong><span>完成押镖后显示结构分布</span></div>`;
  const counts = new Map();
  for (const round of completed) {
    const grade = ["A级镖", "B级镖", "C级镖"].includes(round.grade) ? round.grade : "未知镖级";
    counts.set(grade, (counts.get(grade) || 0) + 1);
  }
  const colors = {"A级镖": "#d6a04e", "B级镖": "#298f77", "C级镖": "#8dbfb1", "未知镖级": "#a8b4ae"};
  const grades = ["A级镖", "B级镖", "C级镖", "未知镖级"].filter(grade => counts.has(grade));
  let start = 0;
  const stops = grades.map(grade => {
    const end = start + counts.get(grade) / completed.length * 100;
    const stop = `${colors[grade]} ${start}% ${end}%`;
    start = end;
    return stop;
  }).join(",");
  const rows = grades.map(grade => `<button type="button" class="grade-key ${chartSelection === grade ? "selected" : ""}" data-chart-grade="${grade}" data-chart-count="${counts.get(grade)}"><i style="background:${colors[grade]}"></i><span>${esc(grade.replace("级镖", "级"))}</span><strong>${counts.get(grade)} 趟</strong><small>${Math.round(counts.get(grade) / completed.length * 100)}%</small></button>`).join("");
  const chosen = counts.has(chartSelection) ? chartSelection : null;
  return `<div class="grade-layout"><div class="grade-donut" data-chart-donut role="button" tabindex="0" style="background:conic-gradient(${stops})" aria-label="点击圆环或图例查看镖级，完成${completed.length}趟"><div class="grade-donut-center"><strong>${completed.length}</strong><span>完成趟数</span></div></div><div class="grade-breakdown"><span class="grade-caption">点击圆环或图例查看数值</span>${rows}</div></div>${chosen ? `<div class="chart-point-detail"><span>${esc(chosen)}</span><strong>${counts.get(chosen)} 趟</strong><small>占全部完成趟数 ${Math.round(counts.get(chosen) / completed.length * 100)}%</small></div>` : ""}`;
}

function earningsChart(rounds) {
  const completed = rounds.filter(round => round.settled_at);
  const label = earningsUnit === "coins" ? "游戏币" : "代金券";
  const switcher = `<div class="chart-unit-switch" aria-label="收益单位"><button type="button" data-earnings-unit="coins" aria-pressed="${earningsUnit === "coins"}" class="${earningsUnit === "coins" ? "active" : ""}">游戏币</button><button type="button" data-earnings-unit="vouchers" aria-pressed="${earningsUnit === "vouchers"}" class="${earningsUnit === "vouchers" ? "active" : ""}">代金券</button></div>`;
  if (!completed.length) return `${switcher}<div class="chart-empty"><img src="art/icon-coins.png" alt=""><strong>暂无收益数据</strong><span>完成押镖后显示每趟收益走势</span></div>`;
  const values = completed.map(round => (round.roles || []).reduce((sum, role) => sum + Number(role[earningsUnit] || 0), 0));
  const max = Math.max(1, ...values);
  const points = values.map((value, index) => ({x: 50 + (completed.length === 1 ? 360 : index * 720 / (completed.length - 1)), y: 183 - value / max * 150, value}));
  const line = points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const area = `${line} L${points.at(-1).x.toFixed(1)} 183 L${points[0].x.toFixed(1)} 183 Z`;
  const dots = points.map((point, index) => `<g class="earnings-point ${chartSelection === index ? "selected" : ""}" data-chart-point="${index}" role="button" tabindex="0" aria-label="${esc(completed[index].team_name)} 第${completed[index].number}趟，${label}${fmt(point.value)}文"><circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="13" class="earnings-hit"/><circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="5" class="earnings-dot"/><title>点击查看第${completed[index].number}趟${label}</title></g>`).join("");
  const ticks = completed.map((round, index) => index === 0 || index === completed.length - 1 || (index + 1) % 4 === 0 ? `<text x="${points[index].x.toFixed(1)}" y="212" text-anchor="middle">${round.number}</text>` : "").join("");
  const chosen = completed[chartSelection];
  return `${switcher}<div class="chart-insight"><span>总收益 <strong>${fmt(values.reduce((sum, value) => sum + value, 0))}</strong> 文</span><span>单趟最高 <strong>${fmt(max)}</strong> 文</span><span>按 ${completed.length} 趟完成记录</span></div><div class="earnings-chart" aria-label="每趟${label}收益走势"><svg viewBox="0 0 820 222" preserveAspectRatio="none"><defs><linearGradient id="earnings-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#3aab86" stop-opacity=".3"/><stop offset="100%" stop-color="#3aab86" stop-opacity="0"/></linearGradient></defs><line x1="50" x2="770" y1="33" y2="33"/><line x1="50" x2="770" y1="108" y2="108"/><line x1="50" x2="770" y1="183" y2="183"/><text x="41" y="37" text-anchor="end">${fmt(max)}</text><text x="41" y="112" text-anchor="end">${fmt(Math.round(max / 2))}</text><text x="41" y="187" text-anchor="end">0</text><path class="earnings-area" d="${area}"/><path class="earnings-line" d="${line}"/>${dots}${ticks}</svg></div><div class="chart-legend"><span><i></i>${label} · 每趟收益</span><span>横轴为趟次</span></div>${chosen ? `<div class="chart-point-detail"><span>${esc(chosen.team_name)} · 第${chosen.number}趟</span><strong>${label} ${fmt(values[chartSelection])} 文</strong><small>完成收益</small></div>` : `<div class="chart-point-hint">点击曲线节点查看每趟准确收益</div>`}`;
}

function chartDashboard(rounds) {
  const options = [["duration", "每趟耗时", "icon-timer.png"], ["earnings", "收益走势", "icon-coins.png"], ["grade", "镖级结构", "icon-flag.png"], ["history", "押镖记录", "icon-history.png"]];
  const charts = {duration: () => durationChart(rounds), earnings: () => earningsChart(rounds), grade: () => gradeChart(rounds), history: recentHistory};
  return `<section class="chart chart-workbench" aria-label="图表看板"><div class="chart-mode-switch" aria-label="切换图表">${options.map(([mode, label, image]) => `<button type="button" data-chart-mode="${mode}" aria-pressed="${chartMode === mode}" class="${chartMode === mode ? "active" : ""}"><img src="art/${image}" alt="">${label}</button>`).join("")}</div><div class="chart-stage">${chartMode === "history" ? "" : `<div class="chart-stage-head"><div><span class="chart-eyebrow">${esc(data.selected_day)} · ${selectedTeam === "all" ? "全部队伍" : esc(currentView()?.name || "当前队伍")}</span><h3>${options.find(([mode]) => mode === chartMode)[1]}</h3></div><span>${chartMode === "duration" ? "分钟 · 趟次" : chartMode === "earnings" ? "文 · 趟次" : "完成趟数"}</span></div>`}${charts[chartMode]()}</div></section>`;
}

function historyGrades(item) {
  const counts = item?.grade_counts || {};
  const grades = ["A级镖", "B级镖", "C级镖"];
  const known = grades.reduce((sum, grade) => sum + Number(counts[grade] || 0), 0);
  return {...Object.fromEntries(grades.map(grade => [grade, Number(counts[grade] || 0)])), "未知镖级": Math.max(Number(counts["未知镖级"] || 0), Number(item?.completed_rounds || 0) - known)};
}

function chartScale(value) {
  if (value >= 100000000) return `${(value / 100000000).toFixed(1)}亿`;
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  return fmt(value);
}

function historyBars(days) {
  const values = days.flatMap(({item}) => historyMetric === "amount" ? [item?.coins || 0, item?.vouchers || 0] : [item?.completed_rounds || 0]);
  const max = Math.max(1, ...values);
  const bars = days.map(({date, item}) => {
    const label = item ? `${date}：${item.completed_rounds || 0} 趟，游戏币 ${fmt(item.coins)} 文，代金券 ${fmt(item.vouchers)} 文` : `${date}：无记录`;
    const grades = historyGrades(item);
    const body = historyMetric === "amount"
      ? `<span class="history-bar-pair"><i class="coins" style="height:${item?.coins ? Math.max(3, item.coins / max * 90) : 0}px"></i><i class="vouchers" style="height:${item?.vouchers ? Math.max(3, item.vouchers / max * 90) : 0}px"></i></span>`
      : `<span class="history-bar-stack" style="height:${item?.completed_rounds ? Math.max(4, item.completed_rounds / max * 90) : 0}px">${["C级镖", "B级镖", "A级镖", "未知镖级"].filter(grade => grades[grade]).map(grade => `<i class="${{"A级镖": "grade-a", "B级镖": "grade-b", "C级镖": "grade-c", "未知镖级": "grade-unknown"}[grade]}" style="flex:${grades[grade]}"></i>`).join("")}</span>`;
    return item
      ? `<button type="button" class="history-day ${date === (chartSelection || data.selected_day) ? "selected" : ""}" data-chart-history="${date}" aria-label="${label}" title="点击查看${date}数值">${body}<span class="history-date">${historyRange === "all" ? date.slice(days.length > 30 ? 5 : 2) : date.slice(8)}</span></button>`
      : `<span class="history-day empty" title="${label}"><span class="history-bar-empty"></span><span class="history-date">${date.slice(8)}</span></span>`;
  }).join("");
  return `<div class="history-scroll"><div class="history-days" style="grid-template-columns:repeat(${days.length},minmax(${historyRange === "all" ? 30 : 0}px,1fr));min-width:${days.length * (historyRange === "all" ? 39 : 20)}px" aria-label="点击有记录的日期查看准确数值">${bars}</div></div>`;
}

function historyTrend(days) {
  const width = Math.max(820, days.length * 30);
  const series = historyMetric === "amount"
    ? [["游戏币", "coins"], ["代金券", "vouchers"]]
    : [["完成趟数", "completed_rounds"], ["碰碰运气", "luck_rounds"]];
  const max = Math.max(1, ...days.flatMap(({item}) => series.map(([, key]) => Number(item?.[key] || 0))));
  const points = days.map(({date, item}, index) => ({date, item, x: 62 + (days.length === 1 ? (width - 96) / 2 : index * (width - 96) / (days.length - 1))}));
  const plots = series.map(([label, key], seriesIndex) => {
    const line = points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)} ${(153 - Number(point.item?.[key] || 0) / max * 120).toFixed(1)}`).join(" ");
    const area = seriesIndex === 0 ? `<path class="history-area" d="${line} L${points.at(-1).x.toFixed(1)} 153 L${points[0].x.toFixed(1)} 153 Z"/>` : "";
    const nodes = points.map(point => point.item ? `<g class="history-point series-${seriesIndex} ${chartSelection === point.date ? "selected" : ""}" data-chart-history="${point.date}" role="button" tabindex="0" aria-label="${point.date}，${label}${fmt(point.item[key])}${historyMetric === "amount" ? "文" : "趟"}"><circle cx="${point.x.toFixed(1)}" cy="${(153 - Number(point.item[key] || 0) / max * 120).toFixed(1)}" r="12" class="history-hit"/><circle cx="${point.x.toFixed(1)}" cy="${(153 - Number(point.item[key] || 0) / max * 120).toFixed(1)}" r="4.5" class="history-dot"/></g>` : "").join("");
    return `${area}<path class="history-line series-${seriesIndex}" d="${line}"/>${nodes}`;
  }).join("");
  const interval = Math.max(1, Math.ceil(days.length / 7));
  const dates = points.map((point, index) => index === 0 || index === days.length - 1 || index % interval === 0 ? `<text x="${point.x.toFixed(1)}" y="185" text-anchor="middle">${historyRange === "all" ? point.date.slice(2) : point.date.slice(5)}</text>` : "").join("");
  return `<div class="history-scroll"><div class="history-trend" style="min-width:${historyRange === "all" && days.length > 30 ? width : 0}px" aria-label="${series.map(([label]) => label).join("与")}双趋势图"><svg viewBox="0 0 ${width} 196" preserveAspectRatio="none"><defs><linearGradient id="history-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#3da989" stop-opacity=".22"/><stop offset="100%" stop-color="#3da989" stop-opacity="0"/></linearGradient></defs><line x1="62" x2="${width - 34}" y1="33" y2="33"/><line x1="62" x2="${width - 34}" y1="93" y2="93"/><line x1="62" x2="${width - 34}" y1="153" y2="153"/><text x="52" y="37" text-anchor="end">${chartScale(max)}</text><text x="52" y="97" text-anchor="end">${chartScale(max / 2)}</text><text x="52" y="157" text-anchor="end">0</text>${plots}${dates}</svg></div></div>`;
}

function recentHistory() {
  const end = new Date(`${data.selected_day}T00:00:00Z`);
  const history = new Map(data.history.map(item => [item.date, item]));
  const allDays = [...history.values()].sort((a, b) => a.date.localeCompare(b.date)).map(item => ({date: item.date, item}));
  const days = historyRange === "all" ? allDays : Array.from({length: 30}, (_, index) => {
    const date = new Date(end);
    date.setUTCDate(end.getUTCDate() - 29 + index);
    const key = date.toISOString().slice(0, 10);
    return {date: key, item: history.get(key)};
  });
  const recorded = days.filter(day => day.item);
  const rounds = recorded.reduce((sum, day) => sum + (day.item.completed_rounds || 0), 0);
  const coins = recorded.reduce((sum, day) => sum + (day.item.coins || 0), 0);
  const vouchers = recorded.reduce((sum, day) => sum + (day.item.vouchers || 0), 0);
  const chosen = recorded.find(day => day.date === chartSelection)?.item;
  const grades = historyGrades(chosen);
  const rangeLabel = historyRange === "all" ? (days.length ? `${days[0].date} — ${days.at(-1).date}` : "全部记录") : `${days[0].date} — ${data.selected_day}`;
  const controls = `<div class="history-controls"><div class="history-toggle" aria-label="记录范围"><button type="button" data-history-range="30d" aria-pressed="${historyRange === "30d"}" class="${historyRange === "30d" ? "active" : ""}">近30天</button><button type="button" data-history-range="all" aria-pressed="${historyRange === "all"}" class="${historyRange === "all" ? "active" : ""}">全部记录</button></div><div class="history-toggle" aria-label="图表指标"><button type="button" data-history-metric="rounds" aria-pressed="${historyMetric === "rounds"}" class="${historyMetric === "rounds" ? "active" : ""}">趟数</button><button type="button" data-history-metric="amount" aria-pressed="${historyMetric === "amount"}" class="${historyMetric === "amount" ? "active" : ""}">金额</button></div><div class="history-toggle" aria-label="图表类型"><button type="button" data-history-view="bars" aria-pressed="${historyView === "bars"}" class="${historyView === "bars" ? "active" : ""}">柱状图</button><button type="button" data-history-view="trend" aria-pressed="${historyView === "trend"}" class="${historyView === "trend" ? "active" : ""}">趋势图</button></div></div>`;
  const legendItems = historyMetric === "amount" ? [["coins", "游戏币"], ["vouchers", "代金券"]] : historyView === "trend" ? [["grade-b", "完成趟数"], ["grade-a", "碰碰运气趟数"]] : [["grade-a", "A级镖"], ["grade-b", "B级镖"], ["grade-c", "C级镖"], ["grade-unknown", "未知镖级"]];
  const legend = `<div class="history-legend">${legendItems.map(([color, label]) => `<span><i class="${color}"></i>${label}</span>`).join("")}</div>`;
  const chart = !recorded.length ? "" : historyView === "trend" ? historyTrend(days) : historyBars(days);
  const gradeDetails = [["A级", grades["A级镖"]], ["B级", grades["B级镖"]], ["C级", grades["C级镖"]], ["未知", grades["未知镖级"]]].filter(([, count]) => count).map(([grade, count]) => `${grade} ${count}`).join(" · ");
  const details = chosen ? `<div class="chart-point-detail"><span>${esc(chosen.date)}</span><strong>${historyMetric === "amount" ? `游戏币 ${fmt(chosen.coins)} 文` : `${chosen.completed_rounds || 0} 趟`}</strong><small>${historyMetric === "amount" ? `代金券 ${fmt(chosen.vouchers)} 文 · 完成 ${chosen.completed_rounds || 0} 趟` : `${gradeDetails || "暂无完成镖级"} · 碰碰运气 ${chosen.luck_rounds || 0} 趟`}</small><button type="button" data-open-day="${esc(chosen.date)}">查看当日明细</button></div>` : `<div class="chart-point-hint">点击${historyView === "trend" ? "曲线节点" : "柱子"}查看当天准确数值</div>`;
  const footnote = historyView === "trend" ? (historyRange === "all" ? "按有记录的日期顺序连线" : "无记录日期按 0 显示") : historyMetric === "amount" ? "两根柱分别表示游戏币与代金券收益" : "每根柱按镖级分段，柱高为完成趟数";
  return `<div class="history-chart" aria-label="押镖历史图表"><div class="chart-stage-head"><div><span class="chart-eyebrow">${esc(rangeLabel)} · 全部队伍</span><h3>${historyRange === "all" ? "全部押镖记录" : "近30天押镖记录"}</h3></div><span>${historyMetric === "amount" ? "按收益金额" : "按完成趟数"}</span></div>${controls}<div class="history-stats"><span>有记录 <strong>${recorded.length}</strong> 天</span><span>完成 <strong>${rounds}</strong> 趟</span><span><img src="art/icon-coins.png" alt="">${fmt(coins)} 文</span><span><img src="art/icon-ticket.png" alt="">${fmt(vouchers)} 文</span></div>${recorded.length ? `${legend}${chart}<div class="history-chart-foot"><span>${footnote}</span><button type="button" class="table-action" data-page="history">查看全部历史</button></div>${details}` : `<div class="history-empty">${historyRange === "all" ? "暂无押镖记录" : "近30天暂无押镖记录"}</div>`}</div>`;
}

function selectHistoryDate(date) {
  const scrollLeft = document.querySelector(".history-scroll")?.scrollLeft || 0;
  chartSelection = date;
  render();
  const chart = document.querySelector(".history-scroll");
  if (chart) chart.scrollLeft = scrollLeft;
}

function table(headers, rows, emptyText, emptyHint = "") {
  return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map(([label, number]) => `<th class="${number ? "number" : ""}">${label}</th>`).join("")}</tr></thead><tbody>${rows || `<tr><td class="row-empty" colspan="${headers.length}"><div class="table-empty"><img src="art/folder.webp" alt=""><div><strong>${emptyText}</strong>${emptyHint ? `<span>${emptyHint}</span>` : ""}</div></div></td></tr>`}</tbody></table></div>`;
}

function roleRows(summary) {
  if (!summary) return "";
  return summary.roles.map(role => `<tr><td><span class="role-name"><span class="role-avatar">${role.role_id}</span>${roleLabel(role)}</span></td><td class="number">${role.level_estimate ? `${role.level_estimate}级*` : "—"}</td><td class="number">${fmt(role.coins)}</td><td class="number">${fmt(role.vouchers)}</td><td class="number">${role.completed_rounds}</td><td class="number">${role.luck_count}</td><td class="number">${role.pirate_reward_count || 0}</td><td class="number">${role.medicine_count || 0}</td></tr>`).join("");
}

function roundCards(summary) {
  if (!summary) return "";
  return summary.rounds.map(round => {
    const turns = roundRole === "all" ? round.roles : round.roles.filter(turn => `${round.team_id}:${turn.role_id}` === roundRole);
    if (!turns.length) return "";
    const results = turns.filter(turn => turn.reward_choice === "碰碰运气");
    const normalCount = turns.filter(turn => turn.reward_choice === "普通收益").length;
    const extrasCount = turns.filter(turn => extraDetail(turn)).length;
    const outcome = results.length
      ? results.map(turn => `<span class="round-outcome"><b>${esc(displayName(turn))}</b>${esc(turn.luck_result || "结果未记录")}</span>`).join("")
      : `<span class="round-outcome">${normalCount ? "普通收益" : "未记录收益选择"}</span>`;
    const members = turns.map(turn => `<div class="round-member"><div class="round-member-name"><span class="role-avatar">${turn.role_id}</span><strong>${esc(displayName(turn))}</strong></div><div class="round-member-amount">${fmt(turn.coins)} 文 <span>游戏币</span> · ${fmt(turn.vouchers)} 文 <span>代金券</span></div><div class="round-member-note">${esc([turn.reward_choice === "碰碰运气" ? `碰碰运气：${turn.luck_result || "结果未记录"}` : turn.reward_choice || "未记录收益选择", extraDetail(turn)].filter(Boolean).join(" · "))}</div></div>`).join("");
    return `<article class="round-card"><div class="round-card-head"><div class="round-identity"><span class="round-index">第 ${String(round.number).padStart(2, "0")} 趟</span><strong>${esc(round.team_name)}</strong><span class="round-grade">${esc(round.grade)}</span></div><div class="round-meta"><span>${esc(round.started_at.slice(11, 19))} 开始</span><span>耗时 ${durationShort(round.seconds)}</span><span class="${round.settled_at ? "result-done" : "result-open"}">${round.settled_at ? "已完成" : "未完成"}${round.incomplete ? " · 日志不全" : ""}</span></div></div><div class="round-card-body"><div class="round-amount"><span>游戏币</span><strong>${fmt(turns.reduce((total, turn) => total + turn.coins, 0))}</strong><small>文</small></div><div class="round-amount"><span>代金券</span><strong>${fmt(turns.reduce((total, turn) => total + turn.vouchers, 0))}</strong><small>文</small></div><div class="round-highlights"><span class="round-highlights-label">收益结果</span><div>${outcome}</div>${extrasCount ? `<small>${extrasCount} 位角色有额外奖励或消耗</small>` : ""}</div></div><details class="round-details"><summary>查看 ${turns.length} 位角色明细</summary><div class="round-members">${members}</div></details></article>`;
  }).join("") || `<div class="round-empty">暂无轮次记录</div>`;
}

function overview() {
  const day = currentView();
  const summary = day?.summary;
  const totals = summary?.totals || zeroTotals;
  const rounds = summary?.rounds || [];
  const roleCount = day?.logs?.length || 0;
  const heroTitle = roleCount ? `${selectedTeam === "all" ? `${data.day.teams.length} 支队伍` : day.name} · ${totals.completed_rounds} 趟完成` : "尚无押镖记录";
  const teamContext = selectedTeam === "all" ? "" : [day?.server_name, day?.leader_name ? `队长 ${day.leader_name}` : ""].filter(Boolean).join(" · ");
  const tabs = `<div class="tabs" role="tablist" aria-label="统计明细"><button type="button" data-detail="roles" class="${detail === "roles" ? "active" : ""}" aria-selected="${detail === "roles"}">角色收益</button><button type="button" data-detail="rounds" class="${detail === "rounds" ? "active" : ""}" aria-selected="${detail === "rounds"}">每轮明细</button></div>`;
  const tableHtml = detail === "roles"
    ? table([["角色"], ["推算等级", true], ["游戏币", true], ["代金券", true], ["完成趟数", true], ["碰碰运气", true], ["瓢把子奖励", true], ["药品", true]], roleRows(summary), "本地账本已就绪，暂无角色数据", "扫描日志后将在这里显示各角色收益统计")
    : `<div class="page-top round-toolbar"><span>按时间查看每趟收益与角色记录</span><select id="role-filter" aria-label="筛选角色"><option value="all">全部角色</option>${(summary?.roles || []).map(role => `<option value="${role.team_id}:${role.role_id}" ${roundRole === `${role.team_id}:${role.role_id}` ? "selected" : ""}>${roleLabel(role)}</option>`).join("")}</select></div><section class="round-list" aria-label="每轮记录">${roundCards(summary)}</section>`;
  return `<section class="hero"><div class="hero-content"><div class="hero-eyebrow">${esc(data.selected_day)} · 押镖统计</div><div class="hero-title">${heroTitle}</div><div class="hero-meta">${icon("sparkles")}${summary ? `选择碰碰运气 ${totals.luck_rounds || 0} 趟${teamContext ? ` · ${esc(teamContext)}` : ""}` : "今日暂无数据，扫描日志即可开始"}</div></div><div class="hero-right"><span>${summary ? `总耗时 ${time(totals.elapsed_seconds)}` : "等待日志数据"}</span></div></section>
    ${sectionHeading("收益与效率", "coins", filters())}
    <section class="metrics" aria-label="收益与效率指标">
      ${metric("游戏币收益", fmt(totals.coins), "文", `${fmt(totals.coins_per_hour)} 文 / 小时`, "coins")}
      ${metric("代金券收益", fmt(totals.vouchers), "文", `${fmt(totals.vouchers_per_hour)} 文 / 小时`, "ticket")}
      ${metric("完成趟数", fmt(totals.completed_rounds), "趟", `${roleCount} 个角色`, "flag")}
      ${metric("总耗时", time(totals.elapsed_seconds), "", `${selectedTeam === "all" ? "各队用时合计 · " : ""}平均单趟 ${time(totals.average_seconds)}`, "timer")}
    </section>
    ${sectionHeading("图表看板", "chart-no-axes-combined", `<span class="section-sub">当天趋势与近30天记录</span>`)}
    ${chartDashboard(rounds)}
    ${tabs}${tableHtml}<div class="inline-note">${icon("circle-check")}*等级按押金规则推算；震慑是触发次数；药品与耐久无价格，未计入净收益；倍率不重复计算</div>
    ${day?.warnings?.length ? `<div class="notice">${esc(day.warnings.slice(0, 3).join("\n"))}</div>` : ""}`;
}

function logsPage() {
  const allLogs = data.day?.logs || [];
  const logs = allLogs.map((log, index) => ({log, index})).filter(({log}) => selectedTeam === "all" || log.team_id === selectedTeam);
  const rows = logs.map(({log, index}) => `<tr><td title="${esc(log.path)}">${esc(log.filename)}</td><td><span class="role-name"><span class="role-avatar">${log.role_id}</span>${roleLabel(log)}</span></td><td class="number">${log.parsed.turns.length}</td><td class="number">${log.parsed.turns.filter(turn => turn.reward_choice === "碰碰运气").length}</td><td><button type="button" class="table-action" data-role-index="${index}">更改队内编号</button></td></tr>`).join("");
  return `<div class="page-intro"><div><h2>日志文件</h2><p>有五人名单和入队记录佐证时显示姓名；其余保留队内编号</p></div>${filters()}</div><section class="list-panel"><div class="list-panel-head"><strong>日志清单</strong><span>${logs.length} 个队内角色</span></div>${table([["文件名"], ["队伍 / 角色"], ["有效轮次", true], ["碰碰运气", true], [""]], rows, "当前日期暂无押镖日志", "扫描日志后将在这里列出原始文件")}</section>${currentView()?.warnings?.length ? `<div class="notice">${esc(currentView().warnings.join("\n"))}</div>` : ""}`;
}

function historyPage() {
  const rows = data.history.map(item => `<tr><td>${esc(item.date)}</td><td class="number">${item.teams}</td><td class="number">${item.roles}</td><td class="number">${item.completed_rounds || 0}</td><td class="number">${fmt(item.coins)}</td><td class="number">${fmt(item.vouchers)}</td><td class="number">${time(item.elapsed_seconds || 0)}</td><td class="number">${item.luck_rounds || 0}</td><td><button type="button" class="table-action" data-open-day="${esc(item.date)}">查看</button></td></tr>`).join("");
  return `<div class="page-intro"><div><h2>每日押镖记录</h2><p>按日期查看各队伍的收益与耗时</p></div><span class="record-count">共 ${data.history.length} 天记录</span></div><section class="list-panel"><div class="list-panel-head"><strong>每日汇总</strong><span>耗时为各队用时合计</span></div>${table([["日期"], ["队伍", true], ["角色", true], ["完成趟数", true], ["游戏币", true], ["代金券", true], ["耗时", true], ["碰碰运气趟数", true], [""]], rows, "暂无历史记录", "扫描日志后将在这里保留每日统计")}</section>`;
}

function settingsPage() {
  return `<div class="page-intro"><div><h2>本地偏好</h2><p>目录与日志扫描设置</p></div></div><div class="settings-grid"><section class="settings-card"><h2><span class="heading-icon">${icon("folder-open")}</span>日志目录</h2><div class="settings-row settings-row-stack"><label class="field-label" for="game-dir">asktao 游戏目录</label><div class="field-row"><input type="text" id="game-dir" value="${esc(data.game_dir)}" spellcheck="false" autocomplete="off"><button type="button" class="outline-button" data-action="browse">${icon("folder-open")}浏览</button></div><div class="settings-path">实际读取：${esc(data.chat_dir)}</div></div><button type="button" class="primary-button settings-save" data-action="save-settings">保存目录</button></section><section class="settings-card"><h2><span class="heading-icon">${icon("scan-line")}</span>日志扫描</h2><div class="settings-row"><div><strong>启动时自动扫描</strong><span>打开押镖账本时读取日志目录</span></div><label class="switch"><input type="checkbox" id="auto-scan" aria-label="启动时自动扫描" ${data.auto_scan ? "checked" : ""}><span></span></label></div><div class="settings-row"><div><strong>手动扫描</strong><span>随时读取游戏目录中的最新日志</span></div><button type="button" class="outline-button" data-action="scan-now">${icon("refresh-cw")}立即扫描</button></div></section><section class="settings-card settings-info"><h2><span class="heading-icon">${icon("hard-drive")}</span>本地数据</h2><p>统计历史保存在此电脑；原始日志仍保留在游戏目录中。应用不会上传日志。</p></section></div>`;
}

function render() {
  if (!(data.day?.teams || []).some(team => team.id === selectedTeam)) selectedTeam = "all";
  const pageTitles = {overview: ["统计总览", "本地押镖记录"], logs: ["日志文件", "角色与原始文件"], history: ["历史记录", "按日期查看押镖收益"], settings: ["设置", "目录与扫描偏好"]};
  document.getElementById("page-title").textContent = pageTitles[page][0];
  document.getElementById("page-subtitle").textContent = pageTitles[page][1];
  document.getElementById("chat-path").textContent = data.chat_dir;
  document.getElementById("choose-button").title = `更改日志目录：${data.chat_dir}`;
  const source = document.getElementById("source-status");
  source.textContent = data.chat_exists ? (data.days.length ? `${data.days.length} 天记录` : "暂无押镖日志") : "目录未找到";
  source.className = `source-status ${data.chat_exists ? data.days.length ? "ready" : "" : "missing"}`;
  document.querySelectorAll(".nav-item[data-page]").forEach(button => button.classList.toggle("active", button.dataset.page === page));
  document.getElementById("scan-button").disabled = busy;
  content.innerHTML = ({overview, logs: logsPage, history: historyPage, settings: settingsPage})[page]();
}

async function loadState(day = "") {
  if (!window.pywebview?.api) {
    render();
    return;
  }
  try {
    data = await window.pywebview.api.get_state(day);
    render();
  } catch (error) {
    setStatus(`读取本地账本失败：${error.message || error}`);
  }
}

async function scan() {
  if (busy) return;
  if (!window.pywebview?.api) {
    setStatus("界面预览未连接本地扫描器");
    return;
  }
  const gameDir = document.getElementById("game-dir")?.value.trim() || data.game_dir;
  busy = true;
  setStatus("正在扫描日志…");
  render();
  try {
    const result = await window.pywebview.api.scan(gameDir);
    data = result.state;
    const report = result.scan;
    setStatus(`扫描 ${report.scanned} 份文本，保存 ${report.saved} 份押镖日志，跳过 ${report.skipped} 份${report.warnings.length ? `；提示 ${report.warnings.length} 条` : ""}`);
  } catch (error) {
    setStatus(`扫描失败：${error.message || error}`);
  } finally {
    busy = false;
    render();
  }
}

async function browse() {
  if (!window.pywebview?.api) {
    setStatus("界面预览未连接目录选择器");
    return;
  }
  try {
    const selected = await window.pywebview.api.choose_directory();
    if (!selected) return;
    const auto = document.getElementById("auto-scan")?.checked ?? data.auto_scan;
    data = await window.pywebview.api.save_settings(selected, auto);
    render();
    setStatus(`已选择 ${data.chat_dir}`);
  } catch (error) {
    setStatus(`选择目录失败：${error.message || error}`);
  }
}

async function saveSettings() {
  const gameDir = document.getElementById("game-dir")?.value.trim();
  const auto = document.getElementById("auto-scan")?.checked ?? data.auto_scan;
  if (!gameDir) return setStatus("请输入游戏目录");
  if (!window.pywebview?.api) return setStatus("界面预览未连接本地设置");
  try {
    data = await window.pywebview.api.save_settings(gameDir, auto);
    render();
    setStatus("设置已保存在本机");
  } catch (error) {
    setStatus(`保存失败：${error.message || error}`);
  }
}

document.addEventListener("click", async (event) => {
  const point = event.target.closest("[data-chart-point]");
  if (point) { chartSelection = Number(point.dataset.chartPoint); render(); return; }
  const historyPoint = event.target.closest("[data-chart-history]");
  if (historyPoint) { selectHistoryDate(historyPoint.dataset.chartHistory); return; }
  const donut = event.target.closest("[data-chart-donut]");
  if (donut) {
    const rect = donut.getBoundingClientRect();
    const angle = (Math.atan2(event.clientX - rect.left - rect.width / 2, rect.top + rect.height / 2 - event.clientY) + Math.PI * 2) % (Math.PI * 2);
    const grades = [...donut.parentElement.querySelectorAll("[data-chart-grade]")];
    const total = grades.reduce((sum, grade) => sum + Number(grade.dataset.chartCount), 0);
    let end = 0;
    chartSelection = (grades.find(grade => (end += Number(grade.dataset.chartCount) / total * Math.PI * 2) >= angle) || grades.at(-1)).dataset.chartGrade;
    render();
    return;
  }
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.page) { page = button.dataset.page; render(); return; }
  if (button.dataset.detail) { detail = button.dataset.detail; render(); return; }
  if (button.dataset.chartMode) { chartMode = button.dataset.chartMode; chartSelection = null; render(); return; }
  if (button.dataset.earningsUnit) { earningsUnit = button.dataset.earningsUnit; render(); return; }
  if (button.dataset.chartGrade) { chartSelection = button.dataset.chartGrade; render(); return; }
  if (button.dataset.historyRange) { historyRange = button.dataset.historyRange; chartSelection = null; render(); return; }
  if (button.dataset.historyMetric) { historyMetric = button.dataset.historyMetric; render(); return; }
  if (button.dataset.historyView) { historyView = button.dataset.historyView; render(); return; }
  if (button.dataset.openDay) { page = "overview"; selectedTeam = "all"; roundRole = "all"; chartSelection = null; await loadState(button.dataset.openDay); content.scrollTo({top: 0}); return; }
  if (button.dataset.roleIndex != null) {
    selectedLog = data.day.logs[Number(button.dataset.roleIndex)];
    document.getElementById("role-file").textContent = `${selectedLog.team_name} · ${selectedLog.filename}`;
    document.getElementById("role-number").max = data.day.teams.find(team => team.id === selectedLog.team_id).logs.length;
    document.getElementById("role-number").value = selectedLog.role_id;
    roleDialog.showModal();
    return;
  }
  if (button.id === "scan-button") return scan();
  if (button.id === "refresh-button") return loadState(data.selected_day);
  if (button.id === "choose-button" || button.dataset.action === "browse") return browse();
  if (button.dataset.action === "save-settings") return saveSettings();
  if (button.dataset.action === "scan-now") return scan();
  if (button.id === "close-dialog") return roleDialog.close();
  if (button.id === "save-role") {
    const roleId = Number(document.getElementById("role-number").value);
    if (!Number.isInteger(roleId) || roleId < 1 || roleId > Number(document.getElementById("role-number").max)) return setStatus("请输入本队已有的角色编号");
    try {
      data = await window.pywebview.api.set_role(selectedLog.source_key, roleId, data.selected_day, selectedLog.team_id);
      roleDialog.close();
      render();
      setStatus("角色编号已更新");
    } catch (error) {
      setStatus(`编号更新失败：${error.message || error}`);
    }
  }
});

document.addEventListener("change", async (event) => {
  if (event.target.id === "day-select") { selectedTeam = "all"; roundRole = "all"; chartSelection = null; await loadState(event.target.value); }
  if (event.target.id === "team-select") { selectedTeam = event.target.value; roundRole = "all"; chartSelection = null; render(); }
  if (event.target.id === "role-filter") { roundRole = event.target.value; render(); }
  if (event.target.id === "auto-scan") saveSettings();
});

document.addEventListener("keydown", (event) => {
  const point = event.target.closest('.earnings-point[data-chart-point]');
  if (point && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); chartSelection = Number(point.dataset.chartPoint); render(); }
  const historyPoint = event.target.closest('.history-point[data-chart-history]');
  if (historyPoint && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); selectHistoryDate(historyPoint.dataset.chartHistory); }
  const donut = event.target.closest('[data-chart-donut]');
  if (donut && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    const grades = [...donut.parentElement.querySelectorAll("[data-chart-grade]")];
    chartSelection = grades[(grades.findIndex(grade => grade.dataset.chartGrade === chartSelection) + 1) % grades.length].dataset.chartGrade;
    render();
  }
});

async function initialize() {
  await loadState();
  if (data.auto_scan && data.chat_exists) scan();
}
if (window.pywebview?.api) initialize();
else window.addEventListener("pywebviewready", initialize, {once: true});
render();
