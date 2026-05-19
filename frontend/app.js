// Automatically uses the same domain whether localhost or Render
const API_BASE = window.location.origin;

// DOM References
const clockEl = document.getElementById('clock');
const countRoundsEl = document.getElementById('count-rounds');
const accSizeEl = document.getElementById('acc-size');
const accColorEl = document.getElementById('acc-color');
const fillSizeEl = document.getElementById('fill-size');
const fillColorEl = document.getElementById('fill-color');
const toggleBtn = document.getElementById('btn-toggle-prediction');
const toggleText = document.getElementById('toggle-text');
const dateContainer = document.getElementById('date-chips');
const accordionContainer = document.getElementById('history-accordion');

let isPredictionActive = false;
let currentTotalIngested = 0;
let activeDateString = null;
let activeSelectedHour = null; // Remembers which hour's sidebar is currently active!
let activeTab = 'core';


// 📊 Analytical Sidebar DOM References
const sidebar10Empty = document.getElementById('empty-10min');
const sidebar10Content = document.getElementById('content-10min');
const sidebarConfEmpty = document.getElementById('empty-conf');
const sidebarConfContent = document.getElementById('content-conf');

// 🕒 Clock Update
setInterval(() => {
    clockEl.textContent = new Date().toLocaleTimeString();
}, 1000);

// Dom Refs for Prediction Box (Separated Gauges)
const predPeriodEl = document.getElementById('pred-period-id');


// 📈 Fetch Stats
async function fetchStats() {
    try {
        const res = await fetch(`${API_BASE}/api/dashboard-stats`);
        const data = await res.json();
        
        const newTotal = parseInt(data.total_ingested);
        const dataGrown = currentTotalIngested > 0 && newTotal !== currentTotalIngested;
        currentTotalIngested = newTotal;
        
        countRoundsEl.textContent = currentTotalIngested.toLocaleString();
        
        // Update Live Prediction Elements
        predPeriodEl.textContent = `PERIOD: ...${data.next_period.toString().slice(-6)}`;
        const fore = data.forecast;
        
        // 1. Update AI Machine Learning Elements
        const fSizeMl = document.getElementById('forecast-size-ml');
        const fColorMl = document.getElementById('forecast-color-ml');
        const confBarSizeMl = document.getElementById('conf-bar-size-ml');
        const confTextSizeMl = document.getElementById('conf-pct-size-ml');
        const confBarColorMl = document.getElementById('conf-bar-color-ml');
        const confTextColorMl = document.getElementById('conf-pct-color-ml');
        
        if (fSizeMl && fore.ml_size) {
            fSizeMl.textContent = fore.ml_size.toUpperCase();
            fSizeMl.className = `forecast-bubble ${fore.ml_size.toLowerCase()}`;
        }
        if (fColorMl && fore.ml_color) {
            fColorMl.textContent = fore.ml_color.toUpperCase();
            fColorMl.className = `forecast-bubble ${fore.ml_color.toLowerCase()}`;
        }
        if (confBarSizeMl) confBarSizeMl.style.width = `${fore.ml_size_confidence}%`;
        if (confTextSizeMl) confTextSizeMl.textContent = `${fore.ml_size_confidence}% MATCH`;
        if (confBarColorMl) confBarColorMl.style.width = `${fore.ml_color_confidence}%`;
        if (confTextColorMl) confTextColorMl.textContent = `${fore.ml_color_confidence}% MATCH`;
        
        // 2. Update Mathematical Heuristic Elements
        const fSizeHeu = document.getElementById('forecast-size-heu');
        const fColorHeu = document.getElementById('forecast-color-heu');
        const confBarSizeHeu = document.getElementById('conf-bar-size-heu');
        const confTextSizeHeu = document.getElementById('conf-pct-size-heu');
        const confBarColorHeu = document.getElementById('conf-bar-color-heu');
        const confTextColorHeu = document.getElementById('conf-pct-color-heu');
        
        if (fSizeHeu && fore.heu_size) {
            fSizeHeu.textContent = fore.heu_size.toUpperCase();
            fSizeHeu.className = `forecast-bubble ${fore.heu_size.toLowerCase()}`;
        }
        if (fColorHeu && fore.heu_color) {
            fColorHeu.textContent = fore.heu_color.toUpperCase();
            fColorHeu.className = `forecast-bubble ${fore.heu_color.toLowerCase()}`;
        }
        if (confBarSizeHeu) confBarSizeHeu.style.width = `${fore.heu_size_confidence}%`;
        if (confTextSizeHeu) confTextSizeHeu.textContent = `${fore.heu_size_confidence}% MATCH`;
        if (confBarColorHeu) confBarColorHeu.style.width = `${fore.heu_color_confidence}%`;
        if (confTextColorHeu) confTextColorHeu.textContent = `${fore.heu_color_confidence}% MATCH`;


        // Process overall accuracy
        const stats = data.stats;
        const total = stats.total_preds || 0;
        
        const sizePct = total > 0 ? Math.round((stats.size_wins / total) * 100) : 0;
        const colorPct = total > 0 ? Math.round((stats.color_wins / total) * 100) : 0;
        
        accSizeEl.textContent = `${sizePct}%`;
        fillSizeEl.style.width = `${sizePct}%`;
        
        accColorEl.textContent = `${colorPct}%`;
        fillColorEl.style.width = `${colorPct}%`;

        // Set toggle state
        updateToggleButton(data.prediction_enabled);

        // Background auto-refresh for 10-Period Scalper when tab is active!
        if (activeTab === 'scalper') {
            fetchScalperStats();
        }

        // SILENT AUTO-REFRESH TRIGGER: If round count increments, push seamless update to UI!
        if (dataGrown && activeDateString) {
            console.log("🔄 New data ingestion detected. Performing seamless timeline hot-swap...");
            loadTimeline(activeDateString, true);
        }
    } catch (err) {
        console.error("Stat fetch failure:", err);
    }
}


// ⏯ Toggle Handler
function updateToggleButton(active) {
    isPredictionActive = active;
    if (active) {
        toggleBtn.classList.remove('is-stopped');
        toggleBtn.classList.add('is-running');
        toggleBtn.innerHTML = `<span class="material-symbols-rounded">stop</span><span>STOP PREDICTION</span>`;
    } else {
        toggleBtn.classList.remove('is-running');
        toggleBtn.classList.add('is-stopped');
        toggleBtn.innerHTML = `<span class="material-symbols-rounded">play_arrow</span><span>START PREDICTION</span>`;
    }
}

toggleBtn.addEventListener('click', async () => {
    const newState = !isPredictionActive;
    try {
        const res = await fetch(`${API_BASE}/api/prediction/toggle?status=${newState}`, { method: 'POST' });
        if (res.ok) {
            updateToggleButton(newState);
        }
    } catch (err) {
        alert("Server connection failed. Make sure Backend is running!");
    }
});

// 📅 Fetch Date List
async function fetchDates() {
    try {
        const res = await fetch(`${API_BASE}/api/available-dates`);
        const dates = await res.json();
        
        dateContainer.innerHTML = '';
        
        if (dates.length === 0) {
            dateContainer.innerHTML = '<p style="color: #666;">No history mined yet.</p>';
            return;
        }

        dates.forEach((dateStr, idx) => {
            const chip = document.createElement('div');
            chip.className = `date-chip ${idx === 0 ? 'active' : ''}`;
            chip.textContent = new Date(dateStr).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
            chip.dataset.raw = dateStr;
            
            chip.addEventListener('click', () => {
                document.querySelectorAll('.date-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                activeDateString = dateStr;
                loadTimeline(dateStr, false); // Explicit click gets animation
            });
            
            dateContainer.appendChild(chip);
        });

        // Load latest date by default
        if (dates[0]) {
            activeDateString = dates[0];
            loadTimeline(dates[0], false);
        }

    } catch (err) {
        dateContainer.innerHTML = '<p style="color:#ff007f">Offline</p>';
    }
}

// 📊 Load Hourly Timeline (with Intelligent State preservation for silent swaps)
async function loadTimeline(dateStr, isSilent = false) {
    // If silent, we do NOT clear DOM or show loading animations to avoid UI flashes!
    if (!isSilent) {
        accordionContainer.innerHTML = '<div class="empty-state"><div class="loading-spinner"></div><p>Decompressing hourly data...</p></div>';
    }
    
    try {
        // 1. RECORD USER CONTEXT: Remember which cards were expanded so they stay open!
        const expandedHours = Array.from(document.querySelectorAll('.hour-card.expanded'))
            .map(card => card.getAttribute('data-hour'));

        const res = await fetch(`${API_BASE}/api/history/date/${dateStr}`);
        const groupedData = await res.json(); 
        
        const tempContainer = document.createDocumentFragment();
        
        if (!groupedData || groupedData.length === 0) {
            accordionContainer.innerHTML = '<div class="empty-state"><p>No records for this date.</p></div>';
            return;
        }

        groupedData.forEach(item => {
            const card = document.createElement('div');
            const hourString = item.hour.toString();
            card.className = 'hour-card';
            card.setAttribute('data-hour', hourString);
            
            // 2. RESTORE USER CONTEXT: Reapply expanded token if user had it open
            if (expandedHours.includes(hourString)) {
                card.classList.add('expanded');
            }
            
            // RE-HIGHLIGHT: Keep active highlight if this hour has active sidebars
            if (activeSelectedHour === hourString) {
                card.classList.add('active-selection');
                // Render sidebars immediately with fresh live data
                setTimeout(() => renderSidebars(item.rounds, displayTime), 0);
            }
            
            const hourInt = parseInt(item.hour);
            const displayTime = formatHour(hourInt);

            // Calculate hourly predictive performance
            const hasPreds = item.total_preds > 0;
            const sPct = hasPreds ? Math.round((item.size_wins / item.total_preds) * 100) : 0;
            const cPct = hasPreds ? Math.round((item.color_wins / item.total_preds) * 100) : 0;
            
            const winRateHtml = hasPreds 
                ? `<span class="hour-win-rate" style="border-color:rgba(0, 242, 255, 0.2); color:rgba(255,255,255,0.9);">🎯 SIZE: <strong style="color:var(--accent-cyan); margin-left:4px;">${sPct}% WIN</strong></span>
                   <span class="hour-win-rate" style="border-color:rgba(255, 0, 127, 0.2); color:rgba(255,255,255,0.9);">🎨 COLOR: <strong style="color:var(--accent-pink); margin-left:4px;">${cPct}% WIN</strong></span>`
                : '';

            card.innerHTML = `
                <div class="hour-header">
                    <div class="hour-title">
                        <span class="material-symbols-rounded" style="color: var(--accent-cyan)">schedule</span>
                        ${displayTime} 
                        <span class="hour-count">${item.count} Rounds</span>
                        ${winRateHtml}
                    </div>
                    <span class="material-symbols-rounded chevron">expand_more</span>
                </div>
                <div class="hour-content">
                    <div class="rounds-table-wrapper">
                        <table>
                            <thead>
                                <tr>
                                    <th>Period</th>
                                    <th>Time</th>
                                    <th>Num</th>
                                    <th>Actual Size</th>
                                    <th>Size Pred.</th>
                                    <th>Size Result</th>
                                    <th>Actual Color</th>
                                    <th>Color Pred.</th>
                                    <th>Color Result</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${item.rounds.map(r => {
                                    const sizePred = r.p_size ? `<span class="pred-tag">${r.p_size.toUpperCase()}</span>` : '-';
                                    const colorPred = r.p_color ? `<span class="pred-tag">${r.p_color.toUpperCase()}</span>` : '-';
                                    
                                    const sizeResClass = r.r_size === 'WIN' ? 'res-win' : r.r_size === 'LOSS' ? 'res-loss' : '';
                                    const colorResClass = r.r_color === 'WIN' ? 'res-win' : r.r_color === 'LOSS' ? 'res-loss' : '';
                                    
                                    const sizeResHtml = r.r_size ? `<span class="outcome-badge ${sizeResClass}">${r.r_size === 'WIN'?'✓':'✕'} ${r.r_size}</span>` : '<span style="color:#555">-</span>';
                                    const colorResHtml = r.r_color ? `<span class="outcome-badge ${colorResClass}">${r.r_color === 'WIN'?'✓':'✕'} ${r.r_color}</span>` : '<span style="color:#555">-</span>';

                                    return `
                                    <tr>
                                        <td style="font-weight:bold; color: white;">...${r.period_id.toString().slice(-5)}</td>
                                        <td style="color: #888; font-size:12px;">${r.time.split('.')[0]}</td>
                                        <td style="font-size: 16px; font-weight:bold;">${r.number}</td>
                                        <td><span class="badge-res ${r.size.toLowerCase() === 'big' ? 'b-big' : 'b-small'}">${r.size.toUpperCase()}</span></td>
                                        <td>${sizePred}</td>
                                        <td>${sizeResHtml}</td>
                                        <td class="${getColorClass(r.color)}">${r.color}</td>
                                        <td>${colorPred}</td>
                                        <td>${colorResHtml}</td>
                                    </tr>
                                `;}).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            // Toggle Functionality
            card.querySelector('.hour-header').addEventListener('click', () => {
                const wasExpanded = card.classList.contains('expanded');
                
                // Collapse all other highlights
                document.querySelectorAll('.hour-card').forEach(c => {
                    c.classList.remove('expanded');
                    c.classList.remove('active-selection');
                });

                if (!wasExpanded) {
                    card.classList.add('expanded');
                    card.classList.add('active-selection');
                    activeSelectedHour = hourString;
                    renderSidebars(item.rounds, displayTime);
                } else {
                    clearSidebars();
                }
            });

            tempContainer.appendChild(card);
        });

        // Perform final unified DOM swap to prevent paint flickering
        accordionContainer.innerHTML = '';
        accordionContainer.appendChild(tempContainer);

    } catch (err) {
        if (!isSilent) {
            accordionContainer.innerHTML = '<div class="empty-state"><p style="color:#ff007f">Failed to stream history cache.</p></div>';
        }
    }
}

// ==========================================================================
// ANALYTICAL SIDEBAR RENDERING ENGINE
// ==========================================================================

function renderSidebars(rounds, label) {
    render10MinAnalysis(rounds, label);
    renderConfidenceAnalysis(rounds, label);
}

function clearSidebars() {
    sidebar10Content.style.display = 'none';
    sidebar10Empty.style.display = 'flex';
    sidebarConfContent.style.display = 'none';
    sidebarConfEmpty.style.display = 'flex';
    activeSelectedHour = null;
    
    // Ensure styling highlights are purged
    document.querySelectorAll('.hour-card').forEach(c => {
        c.classList.remove('active-selection');
    });
}

// 🕒 LEFT SIDEBAR: 10-Min Minute-wise Range Aggregator
function render10MinAnalysis(rounds, hourLabel) {
    const buckets = [
        { range: '00 - 10 MIN', start: 0, end: 10, total: 0, sWins: 0, cWins: 0 },
        { range: '11 - 20 MIN', start: 11, end: 20, total: 0, sWins: 0, cWins: 0 },
        { range: '21 - 30 MIN', start: 21, end: 30, total: 0, sWins: 0, cWins: 0 },
        { range: '31 - 40 MIN', start: 31, end: 40, total: 0, sWins: 0, cWins: 0 },
        { range: '41 - 50 MIN', start: 41, end: 50, total: 0, sWins: 0, cWins: 0 },
        { range: '51 - 60 MIN', start: 51, end: 60, total: 0, sWins: 0, cWins: 0 },
    ];

    rounds.forEach(r => {
        const parts = r.time.split(':');
        if (parts.length < 2) return;
        const minute = parseInt(parts[1]);
        
        const b = buckets.find(x => minute >= x.start && minute <= x.end);
        if (b && (r.p_size || r.p_color)) {
            b.total++;
            if (r.r_size === 'WIN') b.sWins++;
            if (r.r_color === 'WIN') b.cWins++;
        }
    });

    let html = `<div class="sidebar-meta-header">${hourLabel}</div>`;
    
    buckets.forEach(b => {
        const sPct = b.total > 0 ? Math.round((b.sWins / b.total) * 100) : 0;
        const cPct = b.total > 0 ? Math.round((b.cWins / b.total) * 100) : 0;
        
        html += `
            <div class="micro-row">
                <div class="micro-row-header">
                    <span>${b.range}</span>
                    <span class="micro-count-tag">${b.total} PRED</span>
                </div>
                <div class="micro-bars">
                    <div class="micro-bar-item">
                        <span class="micro-bar-label">SIZE</span>
                        <div class="micro-bar-track"><div class="micro-bar-fill bg-cyan" style="width:${sPct}%;"></div></div>
                        <span class="micro-val text-cyan">${sPct}%</span>
                    </div>
                    <div class="micro-bar-item">
                        <span class="micro-bar-label">COLOR</span>
                        <div class="micro-bar-track"><div class="micro-bar-fill bg-pink" style="width:${cPct}%;"></div></div>
                        <span class="micro-val text-pink">${cPct}%</span>
                    </div>
                </div>
            </div>
        `;
    });

    sidebar10Content.innerHTML = html;
    sidebar10Empty.style.display = 'none';
    sidebar10Content.style.display = 'flex';
}

// 📊 RIGHT SIDEBAR: 5% Confidence Accuracy Calibration Engine
function renderConfidenceAnalysis(rounds, hourLabel) {
    const buckets = [
        { label: '96 - 100% CONF', start: 96, end: 100, total: 0, wins: 0 },
        { label: '91 - 95% CONF', start: 91, end: 95, total: 0, wins: 0 },
        { label: '86 - 90% CONF', start: 86, end: 90, total: 0, wins: 0 },
        { label: '81 - 85% CONF', start: 81, end: 85, total: 0, wins: 0 },
        { label: '76 - 80% CONF', start: 76, end: 80, total: 0, wins: 0 },
        { label: '71 - 75% CONF', start: 71, end: 75, total: 0, wins: 0 },
        { label: '66 - 70% CONF', start: 66, end: 70, total: 0, wins: 0 },
        { label: '61 - 65% CONF', start: 61, end: 65, total: 0, wins: 0 },
        { label: '56 - 60% CONF', start: 56, end: 60, total: 0, wins: 0 },
        { label: '50 - 55% CONF', start: 50, end: 55, total: 0, wins: 0 },
    ];

    rounds.forEach(r => {
        // Track Size calibration sample
        if (r.p_size_conf) {
            const confVal = Math.round(parseFloat(r.p_size_conf));
            const b = buckets.find(x => confVal >= x.start && confVal <= x.end);
            if (b) {
                b.total++;
                if (r.r_size === 'WIN') b.wins++;
            }
        }
        // Track Color calibration sample
        if (r.p_color_conf) {
            const confVal = Math.round(parseFloat(r.p_color_conf));
            const b = buckets.find(x => confVal >= x.start && confVal <= x.end);
            if (b) {
                b.total++;
                if (r.r_color === 'WIN') b.wins++;
            }
        }
    });

    let html = `<div class="sidebar-meta-header">${hourLabel}</div>`;
    
    buckets.forEach(b => {
        const winPct = b.total > 0 ? Math.round((b.wins / b.total) * 100) : 0;
        // Standard cyan if calibrated > 70%, otherwise secondary text
        const fillClass = winPct >= 70 ? 'bg-cyan' : 'bg-pink';
        const textClass = winPct >= 70 ? 'text-cyan' : 'text-pink';
        
        html += `
            <div class="micro-row">
                <div class="micro-row-header">
                    <span>${b.label}</span>
                    <span class="micro-count-tag">${b.total} VOL</span>
                </div>
                <div class="micro-bars">
                    <div class="micro-bar-item">
                        <span class="micro-bar-label">ACC</span>
                        <div class="micro-bar-track"><div class="micro-bar-fill ${fillClass}" style="width:${winPct}%;"></div></div>
                        <span class="micro-val ${textClass}">${winPct}%</span>
                    </div>
                </div>
            </div>
        `;
    });

    sidebarConfContent.innerHTML = html;
    sidebarConfEmpty.style.display = 'none';
    sidebarConfContent.style.display = 'flex';
}

// Helpers
function formatHour(h) {
    const period = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    const nextH = (h + 1) % 12 || 12;
    const nextPeriod = (h + 1) >= 24 ? 'AM' : (h+1) >= 12 ? 'PM' : 'AM';
    return `${h12} ${period} - ${nextH} ${nextPeriod}`;
}

function getColorClass(color) {
    const low = color.toLowerCase();
    if (low.includes('violet') && low.includes('red')) return 'c-mix';
    if (low.includes('violet') && low.includes('green')) return 'c-mix';
    if (low.includes('red')) return 'c-red';
    if (low.includes('green')) return 'c-green';
    return '';
}

// Init
fetchStats();
fetchDates();

// Continuous background polling for stats every 2 seconds (Handles instant silent table refreshes)
setInterval(fetchStats, 2000);

// 🔮 Fetch 10-Period Scalper Stats
async function fetchScalperStats() {
    try {
        const res = await fetch(`${API_BASE}/api/scalper-stats`);
        if (!res.ok) return;
        const data = await res.json();
        
        // 1. Update Next Forecast UI elements
        const scalperPeriodEl = document.getElementById('scalper-period-id');
        const fSizeScalper = document.getElementById('scalper-forecast-size');
        const fColorScalper = document.getElementById('scalper-forecast-color');
        
        const confBarSizeScalper = document.getElementById('scalper-conf-size');
        const confTextSizeScalper = document.getElementById('scalper-conf-pct-size');
        const confBarColorScalper = document.getElementById('scalper-conf-color');
        const confTextColorScalper = document.getElementById('scalper-conf-pct-color');
        
        // Get next forthcoming period ID dynamically
        const nextPeriodId = currentTotalIngested > 0 ? (currentTotalIngested + 1) : "...";
        scalperPeriodEl.textContent = `PERIOD: ...${nextPeriodId.toString().slice(-6)}`;
        
        const fore = data.next_forecast;
        if (fore) {
            fSizeScalper.textContent = fore.size.toUpperCase();
            fSizeScalper.className = `forecast-bubble ${fore.size.toLowerCase()}`;
            
            fColorScalper.textContent = fore.color.toUpperCase();
            fColorScalper.className = `forecast-bubble ${fore.color.toLowerCase()}`;
            
            confBarSizeScalper.style.width = `${fore.size_confidence}%`;
            confTextSizeScalper.textContent = `${fore.size_confidence}% MATCH`;
            
            confBarColorScalper.style.width = `${fore.color_confidence}%`;
            confTextColorScalper.textContent = `${fore.color_confidence}% MATCH`;
        }
        
        // 2. Render Backtest Performance Table Rows
        const tbody = document.getElementById('scalper-table-body');
        if (!tbody) return;
        
        if (!data.history || data.history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 30px; color: #64748b;">Waiting for data ingestion...</td></tr>`;
            return;
        }
        
        let html = '';
        data.history.forEach(row => {
            const sizeBadge = row.size_result === 'WIN' ? '<span class="badge win">WIN</span>' : '<span class="badge loss">LOSS</span>';
            const colorBadge = row.color_result === 'WIN' ? '<span class="badge win">WIN</span>' : '<span class="badge loss">LOSS</span>';
            
            const numColorClass = getColorClass(row.actual_color);
            
            html += `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04); height: 55px; vertical-align: middle;">
                    <td style="padding: 12px; font-weight: 700; color: #cbd5e1;">...${row.period_id.toString().slice(-6)}</td>
                    <td style="padding: 12px;"><span class="num-circle ${numColorClass}">${row.number}</span></td>
                    <td style="padding: 12px; text-align: center;"><span class="forecast-bubble ${row.actual_size.toLowerCase()}" style="font-size: 10px; padding: 4px 10px;">${row.actual_size.toUpperCase()}</span></td>
                    <td style="padding: 12px; text-align: center;"><span class="forecast-bubble ${row.pred_size.toLowerCase()}" style="font-size: 10px; padding: 4px 10px;">${row.pred_size.toUpperCase()}</span></td>
                    <td style="padding: 12px; text-align: center;">${sizeBadge}</td>
                    <td style="padding: 12px; text-align: center;"><span class="forecast-bubble ${row.actual_color.toLowerCase()}" style="font-size: 10px; padding: 4px 10px;">${row.actual_color.toUpperCase()}</span></td>
                    <td style="padding: 12px; text-align: center;"><span class="forecast-bubble ${row.pred_color.toLowerCase()}" style="font-size: 10px; padding: 4px 10px;">${row.pred_color.toUpperCase()}</span></td>
                    <td style="padding: 12px; text-align: center;">${colorBadge}</td>
                </tr>
            `;
        });
        
        tbody.innerHTML = html;
        
        // 3. Compute and update Scalper Accuracy stats dynamically (mirroring the main dashboard)
        const totalWins = data.history.length;
        const sizeWins = data.history.filter(row => row.size_result === 'WIN').length;
        const colorWins = data.history.filter(row => row.color_result === 'WIN').length;
        
        const sizePct = totalWins > 0 ? Math.round((sizeWins / totalWins) * 100) : 0;
        const colorPct = totalWins > 0 ? Math.round((colorWins / totalWins) * 100) : 0;
        
        const countScalperRoundsEl = document.getElementById('count-scalper-rounds');
        const accScalperSizeEl = document.getElementById('acc-scalper-size');
        const fillScalperSizeEl = document.getElementById('fill-scalper-size');
        const accScalperColorEl = document.getElementById('acc-scalper-color');
        const fillScalperColorEl = document.getElementById('fill-scalper-color');
        
        if (countScalperRoundsEl) countScalperRoundsEl.textContent = totalWins.toString();
        if (accScalperSizeEl) accScalperSizeEl.textContent = `${sizePct}%`;
        if (fillScalperSizeEl) fillScalperSizeEl.style.width = `${sizePct}%`;
        if (accScalperColorEl) accScalperColorEl.textContent = `${colorPct}%`;
        if (fillScalperColorEl) fillScalperColorEl.style.width = `${colorPct}%`;
        
    } catch (err) {
        console.error("Scalper fetch error:", err);
    }
}


// 🔀 Switch Navigation Tabs
function switchTab(tabId) {
    activeTab = tabId;
    const btnCore = document.getElementById('btn-tab-core');
    const btnScalper = document.getElementById('btn-tab-scalper');
    const viewCore = document.getElementById('view-core');
    const viewScalper = document.getElementById('view-scalper');
    
    if (tabId === 'core') {
        btnCore.classList.add('active');
        btnScalper.classList.remove('active');
        viewCore.style.display = 'flex';
        viewScalper.style.display = 'none';
    } else {
        btnCore.classList.remove('active');
        btnScalper.classList.add('active');
        viewCore.style.display = 'none';
        viewScalper.style.display = 'flex';
        
        // Instant data population
        fetchScalperStats();
    }
}
window.switchTab = switchTab;

