// CheapestFlight 前端（F1）：搜索 → 卡片 → 四种排序 + 直飞/中转筛选
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let flights = [];              // 当前搜索结果（归一化航班）
let sortKey = "price", sortAsc = true;
let filter = "all";

// ---- 初始化 ----
(function init() {
  // 默认日期＝明天
  const d = new Date(); d.setDate(d.getDate() + 1);
  $("#date").value = d.toISOString().slice(0, 10);
  loadCities();
  checkLogin();

  $("#searchBtn").onclick = doSearch;
  $("#loginBtn").onclick = doLogin;
  $("#swap").onclick = () => { const a = $("#dep").value; $("#dep").value = $("#arr").value; $("#arr").value = a; };
  $$(".sort").forEach(b => b.onclick = () => onSort(b.dataset.key));
  $$(".filt").forEach(b => b.onclick = () => onFilter(b.dataset.f));
  $("#dep").addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });
  $("#arr").addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });
  $("#source").onchange = checkLogin;
})();

function source() { return $("#source").value; }

async function loadCities() {
  try {
    const list = await (await fetch("/api/cities")).json();
    $("#cities").innerHTML = list.map(c => `<option value="${c.name}">${c.code}${c.intl ? " · 国际" : ""}</option>`).join("");
  } catch (e) { /* 忽略 */ }
}

async function checkLogin() {
  if (source() !== "fliggy") { $("#loginBanner").classList.add("hidden"); return; }
  try {
    const s = await (await fetch("/api/login-status?source=fliggy")).json();
    $("#loginBanner").classList.toggle("hidden", !!s.logged_in);
  } catch (e) { /* 首次浏览器还在起，忽略 */ }
}

async function doLogin() {
  $("#loginBtn").disabled = true;
  try {
    const r = await (await fetch("/api/login", { method: "POST" })).json();
    setStatus(r.msg || "已打开登录页");
  } finally { $("#loginBtn").disabled = false; }
}

async function doSearch() {
  const dep = $("#dep").value.trim(), arr = $("#arr").value.trim(), date = $("#date").value;
  if (!dep || !arr || !date) { setStatus("请填写出发地、到达地和日期"); return; }
  $("#searchBtn").disabled = true;
  const tip = source() === "fliggy"
    ? `正在驱动登录态浏览器搜索 ${dep} → ${arr} …（约 10–30 秒）`
    : `正在搜索 ${dep} → ${arr} …`;
  setStatus(`<span class="spin"></span>${tip}`);
  $("#results").innerHTML = "";
  $("#controls").classList.add("hidden");
  try {
    const q = new URLSearchParams({ dep, arr, date, source: source() });
    const res = await (await fetch("/api/search?" + q)).json();
    if (res.error) { setStatus("❌ " + res.error); return; }
    if (res.login_needed) {
      $("#loginBanner").classList.remove("hidden");
      setStatus("需要登录淘宝后才能搜索，请点上方「打开登录」。");
      return;
    }
    flights = res.flights || [];
    if (!flights.length) { setStatus("没搜到航班（可能该日期无直达/中转，或需换个日期）。"); return; }
    $("#loginBanner").classList.add("hidden");
    $("#controls").classList.remove("hidden");
    const low = res.lowestPrice != null ? `最低 <b>¥${res.lowestPrice}</b> · ` : "";
    $("#summary").innerHTML = `${low}共 ${flights.length} 个航班`;
    setStatus("");
    render();
  } catch (e) {
    setStatus("❌ 请求失败：" + e.message);
  } finally { $("#searchBtn").disabled = false; }
}

function onSort(key) {
  if (sortKey === key) sortAsc = !sortAsc; else { sortKey = key; sortAsc = true; }
  $$(".sort").forEach(b => {
    const on = b.dataset.key === sortKey;
    b.classList.toggle("active", on);
    b.querySelector("i").textContent = on ? (sortAsc ? "↑" : "↓") : "";
  });
  render();
}

function onFilter(f) {
  filter = f;
  $$(".filt").forEach(b => b.classList.toggle("active", b.dataset.f === f));
  render();
}

function sortVal(f) {
  switch (sortKey) {
    case "dep": return f.depTime || "";
    case "arr": return f.arrTime || "";
    case "dur": return f.durationMin ?? 1e9;
    case "price": default: return f.price ?? 1e9;
  }
}

function render() {
  let list = flights.slice();
  if (filter === "direct") list = list.filter(f => f.type === "direct");
  else if (filter === "transfer") list = list.filter(f => f.type === "transfer");
  list.sort((a, b) => {
    const va = sortVal(a), vb = sortVal(b);
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });
  $("#results").innerHTML = list.map(card).join("") ||
    `<div class="status">当前筛选没有航班</div>`;
}

function hm(min) {
  if (min == null) return "";
  return `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}m`;
}
function tt(s) { return s ? s.slice(11, 16) : ""; }

function card(f) {
  const cross = f.crossDays > 0 ? `<span class="cross">+${f.crossDays}天</span>` : "";
  const badge = f.type === "direct"
    ? `<div class="badge direct">直飞</div>`
    : `<div class="badge transfer">中转${f.transferCount} · ${f.stops.map(s => s.cityName).join("/")}</div>`;
  const depAp = `${f.dep.airportShortName || f.dep.airportName || ""}${f.dep.term || ""}`;
  const arrAp = `${f.arr.airportShortName || f.arr.airportName || ""}${f.arr.term || ""}`;
  const airline = f.airlines.join("/");
  return `
  <div class="card">
    <div class="leg">
      <div class="time"><div class="t">${tt(f.depTime)}</div><div class="ap">${depAp}</div></div>
      <div class="mid">
        <div class="dur">${hm(f.durationMin)}</div>
        <div class="bar"></div>
        ${badge}
      </div>
      <div class="time"><div class="t">${tt(f.arrTime)}${cross}</div><div class="ap">${arrAp}</div></div>
    </div>
    <div class="airlines"><span class="no">${f.flightNos || ""}</span><br>${airline}</div>
    <div class="price"><div class="p"><small>¥</small>${f.price ?? "—"}</div>${f.tax != null ? `<div class="tax">含税约¥${(f.price || 0) + (f.tax || 0)}</div>` : ""}</div>
  </div>`;
}

function setStatus(html) { $("#status").innerHTML = html; }
