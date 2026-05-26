// theme.js
export function getTheme() {
    // 1. Saved preference
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('theme');
      if (saved) return saved;
  
      // 2. System preference
      if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
      }
    }
  
    // 3. Default
    return 'light';
  }
  
  export function setTheme(theme) {
    localStorage.setItem('theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
  }
  
  export function initTheme() {
    const theme = getTheme();
    document.documentElement.setAttribute('data-theme', theme);
  }