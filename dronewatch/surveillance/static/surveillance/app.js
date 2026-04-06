/* =========================================================
   DroneWatch Dashboard — Client Application
   WebSocket connections, Chart.js charts, alert management
   ========================================================= */

// ========================= CONFIGURATION =========================

const WS_HOST = window.location.host;
const WS_VIDEO_URL = `ws://${WS_HOST}/ws/video`;
const WS_DATA_URL = `ws://${WS_HOST}/ws/data`;
const API_BASE = `http://${WS_HOST}`;

const RECONNECT_DELAY = 2000;
const MAX_CHART_POINTS = 60;

// ========================= DOM REFERENCES =========================

const DOM = {
    videoFeed: document.getElementById('video-feed'),
    videoOverlay: document.getElementById('video-overlay'),
    alertFlash: document.getElementById('alert-flash'),
    connectionStatus: document.getElementById('connection-status'),
    statusText: document.querySelector('.status-text'),
    fpsBadge: document.getElementById('fps-badge'),
    uptimeValue: document.getElementById('uptime-value'),

    // Stats
    statCurrentCount: document.getElementById('stat-current-count'),
    statCumulativeCount: document.getElementById('stat-cumulative-count'),
    statBattery: document.getElementById('stat-battery'),
    statAltitude: document.getElementById('stat-altitude'),
    batteryFill: document.getElementById('battery-fill'),
    cardPeople: document.getElementById('card-people'),

    // Charts
    chartPeopleCanvas: document.getElementById('chart-people'),
    chartAlertsCanvas: document.getElementById('chart-alerts'),
    chartConfidenceCanvas: document.getElementById('chart-confidence'),
    modeBadge: document.getElementById('mode-badge'),

    // Alerts
    alertList: document.getElementById('alert-list'),
    totalAlertCount: document.getElementById('total-alert-count'),

    // Footer
    footerMode: document.getElementById('footer-mode'),
};

// ========================= STATE =========================

let currentMode = 'human';
let videoWs = null;
let dataWs = null;
let videoConnected = false;
let dataConnected = false;
let chartPeople = null;
let chartAlerts = null;
let chartConfidence = null;
let alertFilter = 'all';
let lastAlerts = [];
let alertSoundCooldown = 0;

// ========================= CHART.JS SETUP =========================

// Shared chart defaults
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.scale.grid = { color: 'rgba(255,255,255,0.04)' };
Chart.defaults.scale.border = { color: 'rgba(255,255,255,0.06)' };

function initCharts() {
    // ---- People Count Timeline ----
    const ctxPeople = DOM.chartPeopleCanvas.getContext('2d');

    const gradientPeople = ctxPeople.createLinearGradient(0, 0, 0, 160);
    gradientPeople.addColorStop(0, 'rgba(34, 211, 238, 0.25)');
    gradientPeople.addColorStop(1, 'rgba(34, 211, 238, 0)');

    chartPeople = new Chart(ctxPeople, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Detections',
                data: [],
                borderColor: '#22d3ee',
                backgroundColor: gradientPeople,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: '#22d3ee',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            animation: { duration: 300 },
            scales: {
                x: {
                    display: true,
                    ticks: { maxTicksLimit: 8, font: { family: "'JetBrains Mono', monospace", size: 9 } },
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    suggestedMax: 15,
                    ticks: { stepSize: 5, font: { family: "'JetBrains Mono', monospace", size: 9 } },
                }
            },
            plugins: {
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 8,
                    titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    bodyFont: { size: 11 },
                    displayColors: false,
                }
            }
        }
    });

    // ---- Alert Distribution Doughnut ----
    const ctxAlerts = DOM.chartAlertsCanvas.getContext('2d');
    chartAlerts = new Chart(ctxAlerts, {
        type: 'doughnut',
        data: {
            labels: ['Density', 'Weapon', 'Fire'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: ['#fbbf24', '#ef4444', '#f97316'],
                borderColor: 'rgba(10, 14, 23, 0.8)',
                borderWidth: 3,
                hoverOffset: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            animation: { duration: 400 },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        boxWidth: 8,
                        boxHeight: 8,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 10,
                        font: { size: 10 },
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                }
            }
        }
    });

    // ---- Confidence Level Bar Chart ----
    const ctxConf = DOM.chartConfidenceCanvas.getContext('2d');

    const gradientConf = ctxConf.createLinearGradient(0, 0, 0, 140);
    gradientConf.addColorStop(0, 'rgba(167, 139, 250, 0.6)');
    gradientConf.addColorStop(1, 'rgba(167, 139, 250, 0.05)');

    chartConfidence = new Chart(ctxConf, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Confidence',
                data: [],
                backgroundColor: gradientConf,
                borderColor: '#a78bfa',
                borderWidth: 1,
                borderRadius: 3,
                barPercentage: 0.7,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            scales: {
                x: {
                    display: false,
                },
                y: {
                    display: true,
                    min: 0,
                    max: 1,
                    ticks: {
                        callback: v => `${(v * 100).toFixed(0)}%`,
                        stepSize: 0.25,
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    },
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => `${(ctx.parsed.y * 100).toFixed(1)}%`,
                    },
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                }
            }
        }
    });
}

// ========================= WEBSOCKET: VIDEO =========================

function connectVideoWs() {
    if (videoWs && videoWs.readyState <= 1) return;

    videoWs = new WebSocket(WS_VIDEO_URL);

    videoWs.onopen = () => {
        videoConnected = true;
        DOM.videoOverlay.classList.add('hidden');
        updateConnectionStatus();
        console.log('[WS] Video connected');
    };

    videoWs.onmessage = (event) => {
        DOM.videoFeed.src = `data:image/jpeg;base64,${event.data}`;
    };

    videoWs.onclose = () => {
        videoConnected = false;
        DOM.videoOverlay.classList.remove('hidden');
        updateConnectionStatus();
        console.log('[WS] Video disconnected, reconnecting...');
        setTimeout(connectVideoWs, RECONNECT_DELAY);
    };

    videoWs.onerror = () => {
        videoWs.close();
    };
}

// ========================= WEBSOCKET: DATA =========================

function connectDataWs() {
    if (dataWs && dataWs.readyState <= 1) return;

    dataWs = new WebSocket(WS_DATA_URL);

    dataWs.onopen = () => {
        dataConnected = true;
        updateConnectionStatus();
        console.log('[WS] Data connected');
    };

    dataWs.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleTelemetry(data);
        } catch (e) {
            console.error('[WS] Data parse error:', e);
        }
    };

    dataWs.onclose = () => {
        dataConnected = false;
        updateConnectionStatus();
        console.log('[WS] Data disconnected, reconnecting...');
        setTimeout(connectDataWs, RECONNECT_DELAY);
    };

    dataWs.onerror = () => {
        dataWs.close();
    };
}

// ========================= TELEMETRY HANDLER =========================

function handleTelemetry(data) {
    // Update stats cards
    updateStat(DOM.statCurrentCount, data.current_count);
    updateStat(DOM.statCumulativeCount, data.cumulative_count);

    const batteryPct = data.battery;
    DOM.statBattery.textContent = `${batteryPct}%`;
    DOM.batteryFill.style.width = `${batteryPct}%`;
    DOM.batteryFill.className = 'battery-fill' +
        (batteryPct < 20 ? ' low' : batteryPct < 50 ? ' medium' : '');

    DOM.statAltitude.textContent = `${data.altitude} cm`;
    DOM.fpsBadge.textContent = `${data.fps} FPS`;

    // Uptime
    const mins = Math.floor(data.uptime / 60);
    const secs = data.uptime % 60;
    DOM.uptimeValue.textContent =
        `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    // Mode badge
    DOM.modeBadge.textContent = data.mode.toUpperCase();
    DOM.footerMode.textContent = `Mode: ${data.mode.toUpperCase()}`;

    // Update current mode if server changed it
    if (data.mode !== currentMode) {
        currentMode = data.mode;
        updateModeButtons();
    }

    // Alert flash on video
    if (data.density_alert || data.weapon_alert || data.fire_alert) {
        const severity = (data.weapon_alert || data.fire_alert) ? 'danger' : 'warning';
        DOM.alertFlash.className = `alert-flash ${severity}`;
        DOM.cardPeople.classList.add('alert-active');

        // Browser alert sound
        if (Date.now() > alertSoundCooldown) {
            playAlertSound();
            alertSoundCooldown = Date.now() + 5000;
        }
    } else {
        DOM.alertFlash.className = 'alert-flash';
        DOM.cardPeople.classList.remove('alert-active');
    }

    // Update people chart
    if (data.people_history && data.people_history.length > 0) {
        const labels = data.people_history.map(p => `${p.t.toFixed(0)}s`);
        const values = data.people_history.map(p => p.v);

        chartPeople.data.labels = labels;
        chartPeople.data.datasets[0].data = values;

        // Dynamic color based on mode
        const modeColors = {
            human: { border: '#22d3ee', bg: 'rgba(34, 211, 238, 0.25)' },
            weapon: { border: '#ef4444', bg: 'rgba(239, 68, 68, 0.25)' },
            fire: { border: '#f97316', bg: 'rgba(249, 115, 22, 0.25)' },
        };
        const mc = modeColors[data.mode] || modeColors.human;
        chartPeople.data.datasets[0].borderColor = mc.border;

        const ctx = DOM.chartPeopleCanvas.getContext('2d');
        const g = ctx.createLinearGradient(0, 0, 0, 160);
        g.addColorStop(0, mc.bg);
        g.addColorStop(1, mc.bg.replace('0.25', '0'));
        chartPeople.data.datasets[0].backgroundColor = g;

        chartPeople.update('none');
    }

    // Update alert distribution chart
    if (data.alert_counts) {
        chartAlerts.data.datasets[0].data = [
            data.alert_counts.density || 0,
            data.alert_counts.weapon || 0,
            data.alert_counts.fire || 0,
        ];
        // Show placeholder if all zero
        const total = Object.values(data.alert_counts).reduce((a, b) => a + b, 0);
        if (total === 0) {
            chartAlerts.data.datasets[0].data = [1, 1, 1];
            chartAlerts.data.datasets[0].backgroundColor = [
                'rgba(255,255,255,0.05)',
                'rgba(255,255,255,0.05)',
                'rgba(255,255,255,0.05)',
            ];
        } else {
            chartAlerts.data.datasets[0].backgroundColor = ['#fbbf24', '#ef4444', '#f97316'];
        }
        chartAlerts.update('none');
    }

    // Update confidence chart
    if (data.confidence_values && data.confidence_values.length > 0) {
        const confLabels = data.confidence_values.map((_, i) => i + 1);
        chartConfidence.data.labels = confLabels;
        chartConfidence.data.datasets[0].data = data.confidence_values;
        chartConfidence.update('none');
    }

    // Update alert log
    if (data.alerts) {
        DOM.totalAlertCount.textContent = data.total_alerts || 0;
        updateAlertLog(data.alerts);
    }
}

// ========================= UI HELPERS =========================

function updateStat(el, value) {
    const current = el.textContent;
    const newVal = String(value);
    if (current !== newVal) {
        el.textContent = newVal;
        el.classList.add('updating');
        setTimeout(() => el.classList.remove('updating'), 300);
    }
}

function updateConnectionStatus() {
    const online = videoConnected && dataConnected;
    const el = DOM.connectionStatus;

    el.classList.remove('online', 'offline');

    if (online) {
        el.classList.add('online');
        DOM.statusText = document.querySelector('.status-text');
        DOM.statusText.textContent = 'Connected';
    } else if (!videoConnected && !dataConnected) {
        el.classList.add('offline');
        document.querySelector('.status-text').textContent = 'Disconnected';
    } else {
        document.querySelector('.status-text').textContent = 'Partial';
    }
}

function updateModeButtons() {
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === currentMode);
    });
}

// ========================= ALERT LOG =========================

const alertIcons = {
    density: '👥',
    weapon: '🔫',
    fire: '🔥',
};

function updateAlertLog(alerts) {
    if (!alerts || alerts.length === 0) return;

    // Check if alerts changed
    const alertKey = JSON.stringify(alerts.map(a => a.timestamp + a.type));
    if (alertKey === lastAlerts) return;
    lastAlerts = alertKey;

    // Filter alerts
    const filtered = alertFilter === 'all'
        ? alerts
        : alerts.filter(a => a.type === alertFilter);

    if (filtered.length === 0) {
        DOM.alertList.innerHTML = `
            <div class="alert-empty">
                <span>✅</span>
                <p>No ${alertFilter} alerts — monitoring active</p>
            </div>`;
        return;
    }

    DOM.alertList.innerHTML = filtered.map(alert => `
        <div class="alert-item ${alert.type}">
            <span class="alert-type-icon">${alertIcons[alert.type] || '⚠'}</span>
            <div class="alert-content">
                <div class="alert-message">${escapeHtml(alert.message)}</div>
                <div class="alert-timestamp">${alert.timestamp}</div>
            </div>
            <span class="alert-severity ${alert.severity}">${alert.severity}</span>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========================= ALERT SOUND =========================

function playAlertSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, audioContext.currentTime);
        oscillator.frequency.setValueAtTime(660, audioContext.currentTime + 0.1);
        oscillator.frequency.setValueAtTime(880, audioContext.currentTime + 0.2);

        gainNode.gain.setValueAtTime(0.15, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.4);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.4);
    } catch (e) {
        // Audio not available
    }
}

// ========================= MODE SWITCHING =========================

async function switchMode(mode) {
    try {
        const res = await fetch(`${API_BASE}/api/mode/${mode}`, { method: 'POST' });
        if (res.ok) {
            currentMode = mode;
            updateModeButtons();
            console.log(`[MODE] Switched to ${mode}`);
        }
    } catch (e) {
        console.error('[MODE] Switch failed:', e);
    }
}

// ========================= FILTER PILLS =========================

function setupFilterPills() {
    document.querySelectorAll('.pill[data-filter]').forEach(pill => {
        pill.addEventListener('click', () => {
            alertFilter = pill.dataset.filter;
            document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            lastAlerts = ''; // Force re-render
        });
    });
}

// ========================= DRONE COMMAND =========================

async function droneCommand(cmd) {
    try {
        const res = await fetch(`${API_BASE}/api/drone/${cmd}`, { method: 'POST' });
        const data = await res.json();
        if (data.error) {
            console.warn(`[DRONE] ${cmd}: ${data.error}`);
        } else {
            console.log(`[DRONE] ${cmd}: ${data.status}`);
        }
    } catch (e) {
        console.error(`[DRONE] ${cmd} failed:`, e);
    }
}

// ========================= SOURCE BADGE =========================

async function updateSourceBadge() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        const data = await res.json();
        const badge = document.getElementById('source-badge');
        if (badge) {
            if (data.demo_mode) {
                badge.textContent = 'WEBCAM';
                badge.classList.remove('live');
            } else {
                badge.textContent = 'DRONE';
                badge.classList.add('live');
            }
        }
    } catch (e) { /* ignore */ }
}

// ========================= INIT =========================

function init() {
    console.log('[DroneWatch] Initializing dashboard...');

    // Initialize charts
    initCharts();

    // Connect WebSockets
    connectVideoWs();
    connectDataWs();

    // Mode buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchMode(btn.dataset.mode);
        });
    });

    // Alert filter pills
    setupFilterPills();

    // Check source (drone vs webcam)
    updateSourceBadge();

    console.log('[DroneWatch] Dashboard ready!');
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', init);
