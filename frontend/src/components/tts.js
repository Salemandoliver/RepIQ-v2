import { fetchBlobUrl } from "../api";

/* Speak a line in the presenter's voice.
   1. Best: the backend TTS (ElevenLabs) in the configured Oliver/Gary voice — for truly matching the
      videos, point ELEVENLABS_OLIVER_VOICE_ID / ELEVENLABS_GARY_VOICE_ID at the same voices.
   2. Fallback: the browser's own speech — but we pick a natural British male voice and give Oliver and
      Gary distinct voices/pitch so it sounds like two real people, not the flat default.
   `onEnd` fires when speech finishes (used for hands-free voice mode). */

let current = null;

// Warm the voice list (some browsers populate it asynchronously).
try { window.speechSynthesis && window.speechSynthesis.getVoices(); } catch { /* ignore */ }

export function stopSpeaking() {
  try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch { /* ignore */ }
  if (current) { try { current.pause(); } catch { /* ignore */ } current = null; }
}

function pickVoice(presenter) {
  const voices = (window.speechSynthesis && window.speechSynthesis.getVoices()) || [];
  if (!voices.length) return null;
  const gb = voices.filter((v) => /en[-_]GB/i.test(v.lang));
  const pool = gb.length ? gb : voices.filter((v) => /^en/i.test(v.lang));
  // Different preference order per presenter so Oliver and Gary don't sound identical.
  const prefer = (presenter || "").toLowerCase() === "gary"
    ? ["george", "arthur", "microsoft george", "daniel", "google uk english male"]
    : ["daniel", "ryan", "microsoft ryan", "google uk english male", "arthur"];
  for (const name of prefer) {
    const v = pool.find((x) => x.name.toLowerCase().includes(name));
    if (v) return v;
  }
  return pool.find((x) => /male/i.test(x.name)) || pool[0] || null;
}

function browserSpeak(text, presenter, onEnd) {
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-GB";
    const v = pickVoice(presenter);
    if (v) u.voice = v;
    u.pitch = (presenter || "").toLowerCase() === "gary" ? 0.9 : 1.05;  // distinguish the two
    u.rate = 1.0;
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
    audio.onerror = () => { current = null; browserSpeak(text, presenter, onEnd); };
    await audio.play();
  } catch {
    browserSpeak(text, presenter, onEnd);   // not configured / network → browser voice
  }
}
