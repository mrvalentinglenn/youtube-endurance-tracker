const STORAGE_KEY = 'ete-theme'

// Mirrors the inline script in index.html: same key, same dark-by-default fallback,
// so the toggle's initial state always matches what was already painted on <html>.
export function getStoredTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'dark'
  } catch {
    return 'dark'
  }
}

export function setStoredTheme(theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Storage unavailable: the toggle still applies for this page view, it just
    // won't survive a reload.
  }
}

export function applyTheme(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}
