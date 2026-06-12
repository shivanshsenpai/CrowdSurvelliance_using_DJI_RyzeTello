(function () {
    const THEME_KEY = 'dronewatch-theme';
    let currentTheme = localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light';

    function applyTheme(theme) {
        if (!document.body) return;
        document.body.classList.toggle('theme-dark', theme === 'dark');
        
        // Update any theme choices on the screen
        document.querySelectorAll('.theme-choice').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.themeChoice === theme);
        });
    }

    function toggleTheme(nextTheme) {
        if (nextTheme === currentTheme) return;
        currentTheme = nextTheme;
        localStorage.setItem(THEME_KEY, currentTheme);
        applyTheme(currentTheme);
        
        // Dispatch custom event for Chart.js and other scripts to listen to
        window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: currentTheme } }));
    }

    // Set initial theme as early as possible
    if (document.body) {
        applyTheme(currentTheme);
    } else {
        document.addEventListener('DOMContentLoaded', () => applyTheme(currentTheme), { once: true });
    }

    // Setup event listeners for theme switcher buttons when DOM is loaded
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme(currentTheme);
        
        document.body.addEventListener('click', (event) => {
            const btn = event.target.closest('.theme-choice');
            if (btn) {
                const selectedTheme = btn.dataset.themeChoice === 'dark' ? 'dark' : 'light';
                toggleTheme(selectedTheme);
            }
        });
    });
}());
