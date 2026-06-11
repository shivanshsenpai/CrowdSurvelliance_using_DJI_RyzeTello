(function () {
    const theme = localStorage.getItem('dronewatch-theme') === 'dark'
        ? 'dark'
        : 'light';

    function applyTheme() {
        if (!document.body) return;
        document.body.classList.toggle('theme-dark', theme === 'dark');
    }

    if (document.body) {
        applyTheme();
    } else {
        document.addEventListener('DOMContentLoaded', applyTheme, { once: true });
    }
}());
