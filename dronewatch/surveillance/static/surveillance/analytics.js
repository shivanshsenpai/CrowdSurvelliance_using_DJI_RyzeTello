/* =========================================================
   DroneWatch Analytics — Report Page Application
   Fetches analytics data and renders charts & tables
   ========================================================= */

// ========================= CONFIGURATION =========================

const API_BASE = `${window.location.protocol}//${window.location.host}`;

// ========================= DOM REFERENCES =========================

const ADOM = {
    loading: document.getElementById('analytics-loading'),
    error: document.getElementById('analytics-error'),
    errorMessage: document.getElementById('error-message'),
    content: document.getElementById('report-content'),

    // Session bar
    sessionId: document.getElementById('session-id'),
    sessionStart: document.getElementById('session-start'),
    sessionEnd: document.getElementById('session-end'),
    sessionDuration: document.getElementById('session-duration'),
    trendBadge: document.getElementById('trend-badge'),
    trendArrow: document.getElementById('trend-arrow'),
    trendText: document.getElementById('trend-text'),

    // Summary cards
    sumPeak: document.getElementById('sum-peak'),
    sumPeakTime: document.getElementById('sum-peak-time'),
    sumAvg: document.getElementById('sum-avg'),
    sumSnapshots: document.getElementById('sum-snapshots'),
    sumUnique: document.getElementById('sum-unique'),
    sumAlerts: document.getElementById('sum-alerts'),
    sumAlertBreakdown: document.getElementById('sum-alert-breakdown'),

    // Charts
    chartTimelineCanvas: document.getElementById('chart-timeline'),
    chartHourlyCanvas: document.getElementById('chart-hourly'),
    chartAlertDistCanvas: document.getElementById('chart-alert-dist'),

    // Events
    eventsTbody: document.getElementById('events-tbody'),
    eventsCount: document.getElementById('events-count'),

    // Sessions
    sessionsList: document.getElementById('sessions-list'),

    // Footer
    reportGenerated: document.getElementById('report-generated'),
};

// ========================= STATE =========================

let chartTimeline = null;
let chartHourly = null;
let chartAlertDist = null;
let currentReportData = null;

// ========================= THEME PALETTES =========================

const THEME_KEY = 'dronewatch-theme';
const THEME_PALETTES = {
    light: {
        axis: '#64748b',
        grid: 'rgba(15, 23, 42, 0.06)',
        border: 'rgba(15, 23, 42, 0.10)',
        timeline: { border: '#246b73', bg: 'rgba(36, 107, 115, 0.16)' },
        avg: { border: '#246b73', bg: 'rgba(36, 107, 115, 0.5)' },
        peak: { border: '#5b5f97', bg: 'rgba(91, 95, 151, 0.35)' },
        alerts: ['#b7791f', '#c2413a', '#c05621'],
        placeholder: ['rgba(15,23,42,0.06)', 'rgba(15,23,42,0.06)', 'rgba(15,23,42,0.06)'],
    },
    dark: {
        axis: '#94a3b8',
        grid: 'rgba(255,255,255,0.04)',
        border: 'rgba(255,255,255,0.06)',
        timeline: { border: '#22d3ee', bg: 'rgba(34, 211, 238, 0.3)' },
        avg: { border: '#22d3ee', bg: 'rgba(34, 211, 238, 0.5)' },
        peak: { border: '#a78bfa', bg: 'rgba(167, 139, 250, 0.35)' },
        alerts: ['#fbbf24', '#ef4444', '#f97316'],
        placeholder: ['rgba(255,255,255,0.05)', 'rgba(255,255,255,0.05)', 'rgba(255,255,255,0.05)'],
    }
};

function getSavedTheme() {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light';
}

function getThemePalette() {
    return THEME_PALETTES[getSavedTheme()];
}

// ========================= CHART DEFAULTS =========================

const initialPalette = getThemePalette();
Chart.defaults.color = initialPalette.axis;
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.scale.grid = { color: initialPalette.grid };
Chart.defaults.scale.border = { color: initialPalette.border };

// ========================= LOAD REPORT =========================

async function loadReport(hours) {
    ADOM.loading.style.display = 'flex';
    ADOM.error.style.display = 'none';
    ADOM.content.style.display = 'none';

    try {
        let url = `${API_BASE}/api/analytics/report`;
        if (hours) url += `?hours=${hours}`;

        const res = await fetch(url);
        const data = await res.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        currentReportData = data;
        renderReport(data);
        ADOM.loading.style.display = 'none';
        ADOM.content.style.display = 'block';
        ADOM.reportGenerated.textContent = `Report generated: ${new Date().toLocaleTimeString()}`;

    } catch (e) {
        console.error('[Analytics] Load error:', e);
        showError('Failed to load analytics data. Is the server running?');
    }
}

function showError(message) {
    ADOM.loading.style.display = 'none';
    ADOM.error.style.display = 'flex';
    ADOM.content.style.display = 'none';
    ADOM.errorMessage.textContent = message;
}

// ========================= RENDER REPORT =========================

function renderReport(data) {
    // Session info
    if (data.session) {
        ADOM.sessionId.textContent = data.session.session_id.substring(0, 8);
        ADOM.sessionStart.textContent = data.session.start_time;
        ADOM.sessionEnd.textContent = data.session.end_time;
        ADOM.sessionDuration.textContent = formatDuration(data.session.duration_sec);
    }

    // Trend badge
    const trend = data.trend || 'stable';
    ADOM.trendBadge.className = `trend-badge ${trend}`;
    const trendIcons = { increasing: '↑', decreasing: '↓', stable: '→' };
    ADOM.trendArrow.textContent = trendIcons[trend] || '→';
    ADOM.trendText.textContent = trend.toUpperCase();

    // Summary cards
    const s = data.summary || {};
    ADOM.sumPeak.textContent = s.peak_count || 0;
    ADOM.sumPeakTime.textContent = `at ${s.peak_time || '—'}`;
    ADOM.sumAvg.textContent = s.avg_count || 0;
    ADOM.sumSnapshots.textContent = `${s.total_snapshots || 0} snapshots`;
    ADOM.sumUnique.textContent = s.total_unique_people || 0;
    ADOM.sumAlerts.textContent = s.total_alerts || 0;
    ADOM.sumAlertBreakdown.textContent =
        `D:${s.density_alerts || 0} W:${s.weapon_alerts || 0} F:${s.fire_alerts || 0}`;

    // Charts
    renderTimelineChart(data.timeline || []);
    renderHourlyChart(data.hourly_breakdown || []);
    renderAlertDistChart(s);

    // Events table
    renderEventsTable(data.high_density_events || []);
}

// ========================= CHARTS =========================

function renderTimelineChart(timeline) {
    const ctx = ADOM.chartTimelineCanvas.getContext('2d');

    if (chartTimeline) chartTimeline.destroy();

    const labels = timeline.map(d => d.timestamp);
    const values = timeline.map(d => d.count);

    const palette = getThemePalette();
    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, palette.timeline.bg);
    gradient.addColorStop(1, palette.timeline.bg.replace(/0\.\d+\)/, '0)'));

    chartTimeline = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'People Count',
                data: values,
                borderColor: palette.timeline.border,
                backgroundColor: gradient,
                fill: true,
                tension: 0.35,
                pointRadius: values.length > 100 ? 0 : 2,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: palette.timeline.border,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            animation: { duration: 600, easing: 'easeOutQuart' },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        maxTicksLimit: 15,
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    },
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    ticks: {
                        stepSize: 2,
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    },
                }
            },
            plugins: {
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 10,
                    titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    bodyFont: { size: 12 },
                    displayColors: false,
                    callbacks: {
                        label: ctx => `${ctx.parsed.y} people detected`,
                    }
                }
            }
        }
    });
}

function renderHourlyChart(hourlyData) {
    const ctx = ADOM.chartHourlyCanvas.getContext('2d');

    if (chartHourly) chartHourly.destroy();

    const labels = hourlyData.map(d => d.hour);
    const avgValues = hourlyData.map(d => d.avg);
    const peakValues = hourlyData.map(d => d.peak);
    const palette = getThemePalette();

    chartHourly = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Average',
                    data: avgValues,
                    backgroundColor: palette.avg.bg,
                    borderColor: palette.avg.border,
                    borderWidth: 1,
                    borderRadius: 4,
                    barPercentage: 0.6,
                },
                {
                    label: 'Peak',
                    data: peakValues,
                    backgroundColor: palette.peak.bg,
                    borderColor: palette.peak.border,
                    borderWidth: 1,
                    borderRadius: 4,
                    barPercentage: 0.6,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 500 },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    },
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    ticks: {
                        stepSize: 2,
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    },
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        boxWidth: 8,
                        boxHeight: 8,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 12,
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
}

function renderAlertDistChart(summary) {
    const ctx = ADOM.chartAlertDistCanvas.getContext('2d');

    if (chartAlertDist) chartAlertDist.destroy();

    const density = summary.density_alerts || 0;
    const weapon = summary.weapon_alerts || 0;
    const fire = summary.fire_alerts || 0;
    const total = density + weapon + fire;

    const palette = getThemePalette();
    chartAlertDist = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Density', 'Weapon', 'Fire'],
            datasets: [{
                data: total > 0 ? [density, weapon, fire] : [1, 1, 1],
                backgroundColor: total > 0
                    ? palette.alerts
                    : palette.placeholder,
                borderColor: getSavedTheme() === 'dark' ? 'rgba(10, 14, 23, 0.8)' : '#ffffff',
                borderWidth: 3,
                hoverOffset: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            animation: { duration: 500 },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        boxWidth: 8,
                        boxHeight: 8,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 12,
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
}

// ========================= EVENTS TABLE =========================

function renderEventsTable(events) {
    ADOM.eventsCount.textContent = `${events.length} event${events.length !== 1 ? 's' : ''}`;

    if (events.length === 0) {
        ADOM.eventsTbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="6">✅ No high-density events recorded — crowd levels normal</td>
            </tr>`;
        return;
    }

    ADOM.eventsTbody.innerHTML = events.map((ev, i) => {
        const severity = ev.peak >= 20 ? 'critical' : 'high';
        return `
            <tr>
                <td>${i + 1}</td>
                <td>${ev.start}</td>
                <td>${ev.end}</td>
                <td>${formatDuration(ev.duration_sec)}</td>
                <td style="color: var(--accent-red); font-weight: 700;">${ev.peak}</td>
                <td><span class="severity-badge ${severity}">${severity}</span></td>
            </tr>`;
    }).join('');
}

// ========================= SESSIONS =========================

async function loadSessions() {
    try {
        const res = await fetch(`${API_BASE}/api/analytics/sessions`);
        const data = await res.json();

        if (!data.sessions || data.sessions.length === 0) {
            ADOM.sessionsList.innerHTML = '<p class="sessions-empty">No past sessions found</p>';
            return;
        }

        ADOM.sessionsList.innerHTML = data.sessions.map(s => `
            <div class="session-item ${s.is_active ? 'active' : ''}"
                 onclick="loadSessionReport('${s.session_id}')">
                <span class="session-item-id">${s.session_id.substring(0, 8)}</span>
                <span class="session-item-time">${s.start_time}</span>
                <div class="session-item-stats">
                    <span>👥 Peak: ${s.peak_count}</span>
                    <span>📊 Avg: ${s.avg_count}</span>
                    <span>🚨 ${s.total_alerts}</span>
                    <span>📸 ${s.total_snapshots}</span>
                </div>
                <span class="session-item-status ${s.is_active ? 'active' : 'ended'}">
                    ${s.is_active ? 'LIVE' : 'ENDED'}
                </span>
            </div>
        `).join('');
    } catch (e) {
        console.error('[Sessions] Load error:', e);
        ADOM.sessionsList.innerHTML = '<p class="sessions-empty">Failed to load sessions</p>';
    }
}

async function loadSessionReport(sessionId) {
    ADOM.loading.style.display = 'flex';
    ADOM.content.style.display = 'none';

    try {
        const res = await fetch(`${API_BASE}/api/analytics/report?session_id=${sessionId}`);
        const data = await res.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        currentReportData = data;
        renderReport(data);
        ADOM.loading.style.display = 'none';
        ADOM.content.style.display = 'block';
    } catch (e) {
        showError('Failed to load session report');
    }
}

// ========================= UTILITY =========================

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function refreshReport(hours) {
    // Update button states
    document.querySelectorAll('.time-btn').forEach(btn => {
        const btnHours = btn.dataset.hours;
        btn.classList.toggle('active', btnHours === String(hours || ''));
    });
    loadReport(hours);
}

function exportReport() {
    if (!currentReportData) {
        alert('No report data to export. Load a report first.');
        return;
    }
    const blob = new Blob([JSON.stringify(currentReportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dronewatch_report_${new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ========================= AUTO-REFRESH =========================

let autoRefreshInterval = null;

function startAutoRefresh() {
    // Refresh report every 30 seconds if session is active
    autoRefreshInterval = setInterval(() => {
        if (currentReportData && currentReportData.session && currentReportData.session.is_active) {
            loadReport(null);
        }
    }, 30000);
}

// ========================= THEME SWITCH EVENT =========================

function updateChartThemes(theme) {
    const palette = THEME_PALETTES[theme];
    if (!palette) return;

    Chart.defaults.color = palette.axis;
    Chart.defaults.scale.grid.color = palette.grid;
    Chart.defaults.scale.border.color = palette.border;

    [chartTimeline, chartHourly, chartAlertDist].forEach(chart => {
        if (!chart) return;
        if (chart.options.scales) {
            Object.values(chart.options.scales).forEach(scale => {
                if (scale.ticks) scale.ticks.color = palette.axis;
                if (scale.grid) scale.grid.color = palette.grid;
                if (scale.border) scale.border.color = palette.border;
            });
        }
    });

    if (chartTimeline) {
        chartTimeline.data.datasets[0].borderColor = palette.timeline.border;
        chartTimeline.data.datasets[0].pointHoverBackgroundColor = palette.timeline.border;
        const ctx = ADOM.chartTimelineCanvas.getContext('2d');
        const g = ctx.createLinearGradient(0, 0, 0, 240);
        g.addColorStop(0, palette.timeline.bg);
        g.addColorStop(1, palette.timeline.bg.replace(/0\.\d+\)/, '0)'));
        chartTimeline.data.datasets[0].backgroundColor = g;
        chartTimeline.update('none');
    }

    if (chartHourly) {
        chartHourly.data.datasets[0].backgroundColor = palette.avg.bg;
        chartHourly.data.datasets[0].borderColor = palette.avg.border;
        chartHourly.data.datasets[1].backgroundColor = palette.peak.bg;
        chartHourly.data.datasets[1].borderColor = palette.peak.border;
        if (chartHourly.options.plugins && chartHourly.options.plugins.legend && chartHourly.options.plugins.legend.labels) {
            chartHourly.options.plugins.legend.labels.color = palette.axis;
        }
        chartHourly.update('none');
    }

    if (chartAlertDist) {
        chartAlertDist.data.datasets[0].borderColor = theme === 'dark' ? 'rgba(10, 14, 23, 0.8)' : '#ffffff';
        const currentBg = chartAlertDist.data.datasets[0].backgroundColor;
        if (Array.isArray(currentBg)) {
            const isPlaceholder = currentBg.includes(THEME_PALETTES.light.placeholder[0]) || 
                                currentBg.includes(THEME_PALETTES.dark.placeholder[0]);
            if (isPlaceholder) {
                chartAlertDist.data.datasets[0].backgroundColor = palette.placeholder;
            } else {
                chartAlertDist.data.datasets[0].backgroundColor = palette.alerts;
            }
        }
        if (chartAlertDist.options.plugins && chartAlertDist.options.plugins.legend && chartAlertDist.options.plugins.legend.labels) {
            chartAlertDist.options.plugins.legend.labels.color = palette.axis;
        }
        chartAlertDist.update('none');
    }
}

// ========================= INIT =========================

function init() {
    console.log('[Analytics] Initializing...');
    loadReport(null);
    loadSessions();
    startAutoRefresh();
    
    // Register theme switch event listener
    window.addEventListener('themeChanged', (e) => {
        updateChartThemes(e.detail.theme);
    });
    
    console.log('[Analytics] Ready!');
}

document.addEventListener('DOMContentLoaded', init);
