export type FontPreference = 'sans' | 'serif';

export const FONT_PREFERENCE_KEY = 'cn:font:preference';
const FONT_CLASS_SANS = 'font-sans-mode';
const FONT_CLASS_SERIF = 'font-serif-mode';

export function isFontPreference(value: unknown): value is FontPreference {
  return value === 'sans' || value === 'serif';
}

export function getStoredFontPreference(): FontPreference | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(FONT_PREFERENCE_KEY);
  return isFontPreference(raw) ? raw : null;
}

export function applyFontPreference(mode: FontPreference) {
  if (typeof document === 'undefined') return;
  document.body.classList.remove(FONT_CLASS_SANS, FONT_CLASS_SERIF);
  document.body.classList.add(mode === 'serif' ? FONT_CLASS_SERIF : FONT_CLASS_SANS);
}

export function setFontPreference(mode: FontPreference) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(FONT_PREFERENCE_KEY, mode);
  }
  applyFontPreference(mode);
}

