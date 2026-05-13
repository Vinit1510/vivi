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

// 🕒 Clock Update
setInterval(() => {
    clockEl.textContent = new Date().toLocaleTimeString();
}, 1000);

// Dom Refs for Prediction Box (Separated Gauges)
const predPeriodEl = document.getElementById('pred-period-id');
const fSizeEl = document.getElementById('forecast-size');
const fColorEl = document.getElementById('forecast-color');

const confBarSizeEl = document.getElementById('conf-bar-size');
const confTextSizeEl = document.getElementById('conf-pct-size');
const confBarColorEl = document.getElementById('conf-bar-color');
const confTextColorEl = document.getElementById('conf-pct-color');

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
        
        fSizeEl.textContent = fore.size.toUpperCase();
        fSizeEl.className = `forecast-bubble ${fore.size.toLowerCase()}`;
        
        fColorEl.textContent = fore.color.toUpperCase();
        fColorEl.className = `forecast-bubble ${fore.color.toLowerCase()}`;
        
        // Set granular meters
        confBarSizeEl.style.width = `${fore.size_confidence}%`;
        confTextSizeEl.textContent = `${fore.size_confidence}% MATCH`;
        
        confBarColorEl.style.width = `${fore.color_confidence}%`;
        confTextColorEl.textContent = `${fore.color_confidence}% MATCH`;

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
                card.classList.toggle('expanded');
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
