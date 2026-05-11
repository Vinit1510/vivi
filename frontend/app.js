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

// 🕒 Clock Update
setInterval(() => {
    clockEl.textContent = new Date().toLocaleTimeString();
}, 1000);

// 📈 Fetch Stats
async function fetchStats() {
    try {
        const res = await fetch(`${API_BASE}/api/dashboard-stats`);
        const data = await res.json();
        
        countRoundsEl.textContent = parseInt(data.total_ingested).toLocaleString();
        
        // Process accuracy
        const stats = data.stats;
        const total = stats.total_preds || 0;
        
        const sizePct = total > 0 ? Math.round((stats.size_wins / total) * 100) : 0;
        const colorPct = total > 0 ? Math.round((stats.color_wins / total) * 100) : 0;
        
        accSizeEl.textContent = `${sizePct}%`;
        fillSizeEl.style.width = `${sizePct}%`;
        fillSizeEl.style.color = sizePct > 70 ? '#00ff88' : '#ff007f'; // dynamically adjust color 

        accColorEl.textContent = `${colorPct}%`;
        fillColorEl.style.width = `${colorPct}%`;
        fillColorEl.style.color = colorPct > 70 ? '#00ff88' : '#ff007f';

        // Set toggle state
        updateToggleButton(data.prediction_enabled);
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
                loadTimeline(dateStr);
            });
            
            dateContainer.appendChild(chip);
        });

        // Load latest date by default
        if (dates[0]) loadTimeline(dates[0]);

    } catch (err) {
        dateContainer.innerHTML = '<p style="color:#ff007f">Offline</p>';
    }
}

// 📊 Load Hourly Timeline
async function loadTimeline(dateStr) {
    accordionContainer.innerHTML = '<div class="empty-state"><div class="loading-spinner"></div><p>Decompressing hourly data...</p></div>';
    
    try {
        const res = await fetch(`${API_BASE}/api/history/date/${dateStr}`);
        const groupedData = await res.json(); // Array of {hour, count, rounds:[]}
        
        accordionContainer.innerHTML = '';
        
        if (!groupedData || groupedData.length === 0) {
            accordionContainer.innerHTML = '<div class="empty-state"><p>No records for this date.</p></div>';
            return;
        }

        groupedData.forEach(item => {
            const card = document.createElement('div');
            card.className = 'hour-card';
            
            // Format hour nicely (00 to 24) -> 12 AM format
            const hourInt = parseInt(item.hour);
            const displayTime = formatHour(hourInt);

            card.innerHTML = `
                <div class="hour-header">
                    <div class="hour-title">
                        <span class="material-symbols-rounded" style="color: var(--accent-cyan)">schedule</span>
                        ${displayTime} 
                        <span class="hour-count">${item.count} Rounds</span>
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
                                    <th>Number</th>
                                    <th>Size</th>
                                    <th>Color</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${item.rounds.map(r => `
                                    <tr>
                                        <td style="font-weight:bold; color: white;">...${r.period_id.toString().slice(-5)}</td>
                                        <td style="color: #888;">${r.time.split('.')[0]}</td>
                                        <td style="font-size: 18px;">${r.number}</td>
                                        <td><span class="badge-res ${r.size.toLowerCase() === 'big' ? 'b-big' : 'b-small'}">${r.size.toUpperCase()}</span></td>
                                        <td class="${getColorClass(r.color)}">${r.color}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            // Toggle Functionality
            card.querySelector('.hour-header').addEventListener('click', () => {
                card.classList.toggle('expanded');
            });

            accordionContainer.appendChild(card);
        });

    } catch (err) {
        accordionContainer.innerHTML = '<div class="empty-state"><p style="color:#ff007f">Failed to stream history cache.</p></div>';
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

// Continuous background polling for stats every 10 seconds
setInterval(fetchStats, 10000);
