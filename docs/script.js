/**
 * TW Stock Alpha - Integrated Version
 */

let ratioChart = null;
let useLogScale = false;
let allBrokersData = {}; // 全市場搜尋快取

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();

    // --- Institutional Controls ---
    const input = document.getElementById("stockInput");
    const loadBtn = document.getElementById("loadBtn");
    const logCb = document.getElementById("logScaleCheckbox");
    const sortSel = document.getElementById("sortFilter");

    if (loadBtn) loadBtn.addEventListener("click", () => loadStock(input.value));
    if (input) {
        input.addEventListener("keyup", (e) => {
            if (e.key === "Enter") loadStock(input.value);
        });
    }
    if (logCb) {
        logCb.addEventListener("change", () => {
            useLogScale = logCb.checked;
            loadStock(input.value || "2330");
        });
    }
    if (sortSel) {
        sortSel.addEventListener("change", loadInstRanking);
    }

    // --- Init Loads ---
    loadStock("2330");
    loadInstRanking();

    // 預先載入搜尋數據 (Block 3)
    initBrokerSearch();
});

// ==================================================
//  Navigation
// ==================================================
function initNavigation() {
    const navBtns = document.querySelectorAll(".nav-btn");
    const sections = document.querySelectorAll(".section");

    navBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = btn.dataset.section;
            navBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            sections.forEach(sec => {
                sec.classList.remove("active");
                if (sec.id === targetId) sec.classList.add("active");
            });

            // 當切換到券商分點頁籤時，載入相關數據
            if (targetId === "broker") {
                loadHallOfFameList();    // Block B
                loadHallOfFameActions(); // Block A
            }
        });
    });
}

// ==================================================
//  PART 1: Institutional (法人) - 維持原樣
// ==================================================

async function loadStock(code) {
    code = (code || "").trim();
    if (!code) return;
    const statusText = document.getElementById("statusText");
    const chartTitle = document.getElementById("chartTitle");
    if(statusText) statusText.textContent = "載入中...";

    try {
        const res = await fetch(`data/timeseries/${code}.json`);
        if (!res.ok) throw new Error("查無資料");
        const raw = await res.json();
        const data = Array.isArray(raw) ? raw : (raw.data || []);
        if (data.length === 0) throw new Error("資料為空");

        const last = data[data.length - 1];
        if(chartTitle) chartTitle.textContent = `${code} ${last.name} - 三大法人累計買賣超`;
        if(statusText) statusText.textContent = `日期: ${last.date}`;
        renderMainChart(data);
    } catch (e) {
        console.error(e);
        if(statusText) statusText.textContent = "無此股票資料";
    }
}

function renderMainChart(data) {
    const ctx = document.getElementById("ratioChart");
    if (!ctx) return;
    if (ratioChart) ratioChart.destroy();

    let accForeign = 0, accTrust = 0, accDealer = 0;
    const foreignTrend = data.map(d => { accForeign += (d.foreign_net || 0); return accForeign; });
    const trustTrend   = data.map(d => { accTrust += (d.trust_net || 0); return accTrust; });
    const dealerTrend  = data.map(d => { accDealer += (d.dealer_net || 0); return accDealer; });

    ratioChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [
                { label: '外資累計', data: foreignTrend, borderColor: '#ff6b6b', borderWidth: 2, pointRadius: 0, tension: 0.1 },
                { label: '投信累計', data: trustTrend, borderColor: '#4ecdc4', borderWidth: 2, pointRadius: 0, tension: 0.1 },
                { label: '自營累計', data: dealerTrend, borderColor: '#ffe66d', borderWidth: 2, pointRadius: 0, tension: 0.1 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b8b9e', maxTicksLimit: 8 } },
                y: { 
                    type: useLogScale ? 'logarithmic' : 'linear',
                    grid: { color: 'rgba(255,255,255,0.05)' }, 
                    ticks: { color: '#8b8b9e' }
                }
            }
        }
    });
}

async function loadInstRanking() {
    const tbody = document.querySelector("#rankTable tbody");
    const sortValue = document.getElementById("sortFilter").value;
    if (!tbody) return;

    try {
        const res = await fetch("data/stock_three_inst_latest.json");
        const data = await res.json();
        const [role, direction] = sortValue.split('_');
        let sortKey = 'trust_net';
        if (role === 'foreign') sortKey = 'foreign_net';
        if (role === 'dealer') sortKey = 'dealer_net';

        data.sort((a, b) => {
             const valA = a[sortKey] || 0;
             const valB = b[sortKey] || 0;
             return direction === 'buy' ? valB - valA : valA - valB;
        });

        tbody.innerHTML = "";
        data.slice(0, 50).forEach((row, idx) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>
                    <span style="color:#e94560; font-weight:bold; cursor:pointer;" onclick="loadStock('${row.code}')">${row.code}</span>
                    <br><small style="color:#8b8b9e">${row.name}</small>
                </td>
                <td class="${getColor(row.foreign_net)}">${formatMini(row.foreign_net)}</td>
                <td><div style="width:70px; height:30px;"><canvas id="spark-f-${idx}"></canvas></div></td>
                <td class="${getColor(row.trust_net)}">${formatMini(row.trust_net)}</td>
                <td><div style="width:70px; height:30px;"><canvas id="spark-t-${idx}"></canvas></div></td>
                <td class="${getColor(row.dealer_net)}">${formatMini(row.dealer_net)}</td>
                <td><div style="width:70px; height:30px;"><canvas id="spark-z-${idx}"></canvas></div></td>
            `;
            tbody.appendChild(tr);
            setTimeout(() => {
                if (row.history) {
                    drawSparkline(`spark-f-${idx}`, row.history, 'f');
                    drawSparkline(`spark-t-${idx}`, row.history, 't');
                    drawSparkline(`spark-z-${idx}`, row.history, 'z');
                }
            }, 0);
        });
    } catch (e) { console.error(e); }
}

function drawSparkline(id, history, type) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    const vals = history.map(h => type === 'f' ? h.f : (type === 't' ? h.t : h.z));
    let baseColor = type === 't' ? '#4ecdc4' : (type === 'z' ? '#ffe66d' : '#ff4757');
    const colors = vals.map(v => v >= 0 ? baseColor : '#2f3542');
    new Chart(ctx, {
        type: 'bar',
        data: { labels: history.map(h => h.d), datasets: [{ data: vals, backgroundColor: colors, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: false, tooltip: false }, scales: { x: { display: false }, y: { display: false } }, animation: false }
    });
}

// ==================================================
//  PART 2: Broker (券商) - 新版整合功能
// ==================================================
const DATA_PATH = "data/";

// 1. 名人堂列表 (Hall of Fame List)
async function loadHallOfFameList() {
    const tbody = document.getElementById("hof-tbody");
    if (!tbody) return;
    
    try {
        const response = await fetch(`${DATA_PATH}hall_of_fame_list.json`);
        if (!response.ok) throw new Error("無數據");
        const json = await response.json();
        const data = json.data || [];

        tbody.innerHTML = "";
        if (data.length === 0) {
            tbody.innerHTML = "<tr><td colspan='5' style='text-align:center;'>暫無符合條件的分點</td></tr>";
            return;
        }

        data.forEach((broker, index) => {
            const tr = document.createElement("tr");
            const profitClass = broker.total_profit > 0 ? "text-red" : "text-green";
            const profitStr = Math.round(broker.total_profit).toLocaleString();
            
            // 處理名次顯示
            let rankDisp = index + 1;
            if (index === 0) rankDisp = "🥇";
            if (index === 1) rankDisp = "🥈";
            if (index === 2) rankDisp = "🥉";

            tr.innerHTML = `
                <td>${rankDisp}</td>
                <td class="fw-bold">${broker.broker_name}</td>
                <td>${broker.win_rate}%</td>
                <td class="${profitClass}">${profitStr}</td>
                <td>${broker.total_trades}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error(e);
        tbody.innerHTML = "<tr><td colspan='5' style='text-align:center; color:red;'>讀取失敗或尚未執行更新</td></tr>";
    }
}

// 2. 贏家今日動向 (Winner Actions)
async function loadHallOfFameActions() {
    const container = document.getElementById("hof-actions-container");
    if (!container) return;

    try {
        const response = await fetch(`${DATA_PATH}hall_of_fame_today.json`);
        if (!response.ok) throw new Error("無數據");
        const json = await response.json();
        const data = json.data || [];

        container.innerHTML = "";

        if (data.length === 0) {
            container.innerHTML = "<p style='padding:20px; text-align:center;'>今日名人堂分點無交易紀錄。</p>";
            return;
        }

        data.forEach(item => {
            // 建立卡片
            const card = document.createElement("div");
            card.className = "broker-action-card";

            const header = document.createElement("div");
            header.style.marginBottom = "10px";
            header.style.borderBottom = "1px solid #2a2a42";
            header.style.paddingBottom = "5px";
            header.innerHTML = `
                <span style="font-size:1.1em; color:#fff; font-weight:bold;">${item.broker_name}</span>
                <span style="font-size:0.8em; color:#888; margin-left:10px;">勝率 ${item.stats.win_rate}%</span>
            `;
            card.appendChild(header);

            const actionList = document.createElement("div");
            item.today_actions.forEach(action => {
                const badge = document.createElement("span");
                const isBuy = action.net_vol > 0;
                badge.className = isBuy ? "badge-buy" : "badge-sell";
                badge.innerHTML = `
                    ${action.stock_code} 
                    ${isBuy ? "買" : "賣"} 
                    ${Math.abs(action.net_vol)}
                `;
                actionList.appendChild(badge);
            });
            card.appendChild(actionList);
            container.appendChild(card);
        });

    } catch (e) {
        console.error(e);
        container.innerHTML = "<p style='padding:20px; text-align:center; color:red;'>資料讀取失敗</p>";
    }
}

// 3. 全市場搜尋 (Broker Search)
async function initBrokerSearch() {
    try {
        const response = await fetch(`${DATA_PATH}all_broker_daily_summary.json`);
        if (!response.ok) return; // 沒資料就不做動作
        const json = await response.json();
        allBrokersData = json.brokers || {};

        const datalist = document.getElementById("broker-list-suggestions");
        if (datalist) {
            Object.keys(allBrokersData).forEach(name => {
                const opt = document.createElement("option");
                opt.value = name;
                datalist.appendChild(opt);
            });
        }
    } catch (e) { console.error("搜尋數據載入失敗", e); }
}

function searchBroker() {
    const input = document.getElementById("broker-search-input").value.trim();
    const resultDiv = document.getElementById("search-result-table");
    const title = document.getElementById("search-result-title");
    const tbody = document.getElementById("search-result-tbody");

    if (!input || !allBrokersData[input]) {
        title.innerText = "找不到此券商或今日無交易";
        resultDiv.style.display = "none";
        return;
    }

    const trades = allBrokersData[input];
    title.innerText = `${input} 今日交易明細`;
    resultDiv.style.display = "table";
    tbody.innerHTML = "";

    trades.forEach(t => {
        const tr = document.createElement("tr");
        const isBuy = t.net_vol > 0;
        tr.innerHTML = `
            <td><span class="badge" style="background:#333; color:#fff;">${t.stock_code}</span></td>
            <td style="color:${isBuy ? '#ff6b6b' : '#4ecdc4'}">${isBuy ? '買超' : '賣超'}</td>
            <td>${Math.abs(t.net_vol)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Helpers
const formatMini = (val) => {
    if(!val) return '-';
    if(Math.abs(val) > 1000) return (val/1000).toFixed(1) + 'k';
    return val;
};
const getColor = val => val > 0 ? 'text-red' : (val < 0 ? 'text-green' : '');