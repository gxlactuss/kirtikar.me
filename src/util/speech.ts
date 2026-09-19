/**
 * Text-to-speech for the screen-reader button.
 *
 * The app uses Sarvam's bulbul TTS for Indic languages. The demo is
 * English-only and the browser already has a voice, so this uses
 * speechSynthesis rather than spending an API call on it.
 */
export function speak(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95;
    u.lang = 'en-IN';
    window.speechSynthesis.speak(u);
  } catch {
    // Speech is an enhancement; a browser that refuses it changes nothing else.
  }
}

export function stopSpeaking(): void {
  try {
    window.speechSynthesis?.cancel();
  } catch {
    /* no-op */
  }
}
