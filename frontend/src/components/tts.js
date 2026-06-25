import { fetchBlobUrl } from "../api";

/* Speak a line in the presenter's voice. Tries the backend TTS (ElevenLabs, presenter voice); if
   that isn't configured (501) or fails, falls back to the browser's built-in speech synthesis so it
   still talks. `onEnd` fires when speech finishes (used for hands-free voice mode). */

let current = null;

export function stopSpeaking() {
  try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch { /* ignore */ }
  if (current) { try { current.pause(); } catch { /* ignore */ } current = null; }
}

function browserSpeak(text, onEnd) {
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-GB";
    if (onEnd) u.onend = onEnd;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch { if (onEnd) onEnd(); }
}

export async function speak(text, presenter, onEnd) {
  stopSpeaking();
  if (!text) { if (onEnd) onEnd(); return; }
  try {
    const url = await fetchBlobUrl(
      `/api/reflection/tts?text=${encodeURIComponent(text.slice(0, 1500))}&presenter=${encodeURIComponent(presenter || "Oliver")}`
    );
    const audio = new Audio(url);
    current = audio;
    audio.onended = () => { current = null; if (onEnd) onEnd(); };
    audio.onerror = () => { current = null; browserSpeak(text, onEnd); };
    await audio.play();
  } catch {
    browserSpeak(text, onEnd);   // not configured / network → browser voice
  }
}
