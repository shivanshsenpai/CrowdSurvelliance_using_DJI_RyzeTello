/* =========================================================
   DroneWatch History — Past Records Visualization
   Fetches analytics report data for the selected session
   and renders timeline line chart, alerts doughnut, and heatmap.
   ========================================================= */

const API_BASE = `${window.location.protocol}//${window.location.host}`;

const HDOM = {
    metadata: document.getElementById('session-metadata'),
    timelineCanvas: document.getElementById('history-timeline-chart'),
    alertsCanvas: document.getElementById('history-alerts-chart'),
    heatmapContainer: document.getElementById('density-heatmap'),
};

let historyTimelineChart = null;
let historyAlertsChart = null;
let sessionReportData = null;

const THEME_KEY = 'dronewatch-theme';
const THEME_PALETTES = {
    light: {
        axis: '#64748b',
        grid: 'rgba(15, 23, 42, 0.06)',
        border: 'rgba(15, 23, 42, 0.10)',
        timeline: { border: '#246b73', bg: 'rgba(36, 107, 115, 0.16)' },
        alerts: ['#b7791f', '#c2413a', '#c05621'],
        placeholder: ['rgba(15,23,42,0.06)', 'rgba(15,23,42,0.06)', 'rgba(15,23,42,0.06)'],
    },
    dark: {
        axis: '#94a3b8',
        grid: 'rgba(255,255,255,0.04)',
        border: 'rgba(255,255,255,0.06)',
        timeline: { border: '#22d3ee', bg: 'rgba(34, 211, 238, 0.3)' },
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

// Set up chart defaults matching the theme
function configureChartDefaults() {
    const palette = getThemePalette();
    Chart.defaults.color = palette.axis;
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.scale.grid = { color: palette.grid };
    Chart.defaults.scale.border = { color: palette.border };
}

// Load visual data for the selected session
async function loadSessionVisuals() {
    if (!HDOM.metadata) return;
    const sessionId = HDOM.metadata.dataset.sessionId;
    if (!sessionId) return;

    try {
        const res = await fetch(`${API_BASE}/api/analytics/report?session_id=${sessionId}`);
        const data = await res.json();
        
        if (data.error) {
            console.error("[History] Data error:", data.error);
            return;
        }

        sessionReportData = data;
        renderTimelineChart(data.timeline || []);
        renderAlertsChart(data.summary || {});
        renderHeatmap(data.timeline || []);

    } catch (e) {
        console.error("[History] Failed to load session report data:", e);
    }
}

// Render the timeline trend chart
function renderTimelineChart(timeline) {
    if (!HDOM.timelineCanvas) return;
    const ctx = HDOM.timelineCanvas.getContext('2d');
    if (historyTimelineChart) historyTimelineChart.destroy();

    const labels = timeline.map(d => d.timestamp);
    const values = timeline.map(d => d.count);
    const palette = getThemePalette();

    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, palette.timeline.bg);
    gradient.addColorStop(1, palette.timeline.bg.replace(/0\.\d+\)/, '0)'));

    historyTimelineChart = new Chart(ctx, {
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
                pointRadius: values.length > 80 ? 0 : 2,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: palette.timeline.border,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        maxTicksLimit: 12,
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    ticks: {
                        stepSize: 2,
                        font: { family: "'JetBrains Mono', monospace", size: 9 },
                    }
                }
            },
            plugins: {
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 8,
                    titleFont: { family: "'JetBrains Mono', monospace", size: 10 },
                    displayColors: false,
                    callbacks: {
                        label: ctx => `${ctx.parsed.y} people detected`,
                    }
                }
            }
        }
    });
}

// Render alerts doughnut chart
function renderAlertsChart(summary) {
    if (!HDOM.alertsCanvas) return;
    const ctx = HDOM.alertsCanvas.getContext('2d');
    if (historyAlertsChart) historyAlertsChart.destroy();

    const density = summary.density_alerts || 0;
    const weapon = summary.weapon_alerts || 0;
    const fire = summary.fire_alerts || 0;
    const total = density + weapon + fire;

    const palette = getThemePalette();

    historyAlertsChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Density', 'Weapon', 'Fire'],
            datasets: [{
                data: total > 0 ? [density, weapon, fire] : [1, 1, 1],
                backgroundColor: total > 0 ? palette.alerts : palette.placeholder,
                borderColor: getSavedTheme() === 'dark' ? 'rgba(10, 14, 23, 0.8)' : '#ffffff',
                borderWidth: 3,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        boxWidth: 8,
                        boxHeight: 8,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 8,
                        font: { size: 10 }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1
                }
            }
        }
    });
}

// Render horizontal density heatmap timeline
function renderHeatmap(timeline) {
    if (!HDOM.heatmapContainer) return;
    HDOM.heatmapContainer.innerHTML = '';

    if (timeline.length === 0) {
        HDOM.heatmapContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 0.78rem; width: 100%; text-align: center; line-height: 48px;">No snapshots recorded to map</div>';
        return;
    }

    const maxCount = Math.max(...timeline.map(d => d.count), 1);

    timeline.forEach(d => {
        const cell = document.createElement('div');
        cell.className = 'heatmap-cell';

        // Categorize count level for class color mapping
        if (d.count >= 10) {
            cell.classList.add('high');
        } else if (d.count >= 5) {
            cell.classList.add('medium');
        } else {
            cell.classList.add('low');
        }

        // Scale height proportionally with a minimum of 20% height so 0 people still show a tiny indicator
        const heightPct = Math.max(20, (d.count / maxCount) * 100);
        cell.style.height = `${heightPct}%`;

        // Native tooltip details
        cell.setAttribute('title', `Time: ${d.timestamp}\nPeople Count: ${d.count}`);

        HDOM.heatmapContainer.appendChild(cell);
    });
}

// Update charts themes dynamically
function updateChartThemes(theme) {
    const palette = THEME_PALETTES[theme];
    if (!palette) return;

    Chart.defaults.color = palette.axis;
    Chart.defaults.scale.grid.color = palette.grid;
    Chart.defaults.scale.border.color = palette.border;

    [historyTimelineChart, historyAlertsChart].forEach(chart => {
        if (!chart) return;
        if (chart.options.scales) {
            Object.values(chart.options.scales).forEach(scale => {
                if (scale.ticks) scale.ticks.color = palette.axis;
                if (scale.grid) scale.grid.color = palette.grid;
                if (scale.border) scale.border.color = palette.border;
            });
        }
    });

    if (historyTimelineChart) {
        historyTimelineChart.data.datasets[0].borderColor = palette.timeline.border;
        historyTimelineChart.data.datasets[0].pointHoverBackgroundColor = palette.timeline.border;
        const ctx = HDOM.timelineCanvas.getContext('2d');
        const g = ctx.createLinearGradient(0, 0, 0, 240);
        g.addColorStop(0, palette.timeline.bg);
        g.addColorStop(1, palette.timeline.bg.replace(/0\.\d+\)/, '0)'));
        historyTimelineChart.data.datasets[0].backgroundColor = g;
        historyTimelineChart.update('none');
    }

    if (historyAlertsChart) {
        historyAlertsChart.data.datasets[0].borderColor = theme === 'dark' ? 'rgba(10, 14, 23, 0.8)' : '#ffffff';
        const currentBg = historyAlertsChart.data.datasets[0].backgroundColor;
        if (Array.isArray(currentBg)) {
            const isPlaceholder = currentBg.includes(THEME_PALETTES.light.placeholder[0]) || 
                                 currentBg.includes(THEME_PALETTES.dark.placeholder[0]);
            if (isPlaceholder) {
                historyAlertsChart.data.datasets[0].backgroundColor = palette.placeholder;
            } else {
                historyAlertsChart.data.datasets[0].backgroundColor = palette.alerts;
            }
        }
        if (historyAlertsChart.options.plugins && historyAlertsChart.options.plugins.legend && historyAlertsChart.options.plugins.legend.labels) {
            historyAlertsChart.options.plugins.legend.labels.color = palette.axis;
        }
        historyAlertsChart.update('none');
    }
}

// Initialize on DOM load
function init() {
    configureChartDefaults();
    loadSessionVisuals();

    // Listen to live theme switcher changes
    window.addEventListener('themeChanged', (e) => {
        updateChartThemes(e.detail.theme);
    });
}

document.addEventListener('DOMContentLoaded', init);
