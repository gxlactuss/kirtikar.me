const NAME_KEY = 'kirtikar.visitorName';

/**
 * The optional name a visitor typed on the first step, kept across reloads
 * so a second product does not ask again. Storage can be off or refuse
 * writes, in which case the name only lasts until the page closes.
 */
let fallback = '';

export function visitorName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? fallback;
  } catch {
    return fallback;
  }
}

export function setVisitorName(name: string) {
  fallback = name;
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    // The in-memory copy still covers this visit.
  }
}
