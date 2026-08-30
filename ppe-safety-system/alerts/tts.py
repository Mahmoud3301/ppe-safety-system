"""
Text-to-Speech Module — Bilingual (Arabic + English)
=====================================================
Plays Arabic alert first, then English alert.
Uses gTTS for generation and pygame for playback.
Works in headless (no-display) environments.
"""

import os
import tempfile
import threading
import time
from gtts import gTTS
import pygame


class TTSEngine:
    """Bilingual Text-to-Speech engine using gTTS + pygame."""

    def __init__(self, language="both", speed=1.0, enabled=True):
        """
        Args:
            language: 'en', 'ar', or 'both' (plays Arabic then English)
            speed: Not used directly (gTTS slow param)
            enabled: Enable/disable TTS
        """
        self.language = language
        self.speed = speed
        self.enabled = enabled
        self._lock = threading.Lock()
        self._initialized = False

        # Initialize pygame mixer
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self._initialized = True
            print("🔊 TTS Engine initialized (gTTS + pygame) — Bilingual AR+EN")
        except Exception as e:
            print(f"⚠️  Could not initialize audio: {e}")
            self._initialized = False

    def speak(self, text_en: str, text_ar: str = None, blocking: bool = False):
        """
        Play alert in Arabic then English (or per language setting).

        Args:
            text_en: English alert text
            text_ar: Arabic alert text (auto-generated if None)
            blocking: Wait for playback to finish
        """
        if not self.enabled or not self._initialized:
            print(f"🔇 TTS (disabled): {text_en}")
            return

        if blocking:
            self._speak_bilingual(text_en, text_ar)
        else:
            t = threading.Thread(
                target=self._speak_bilingual,
                args=(text_en, text_ar),
                daemon=True
            )
            t.start()

    def _speak_bilingual(self, text_en: str, text_ar: str = None):
        """Internal: play Arabic then English alerts."""
        with self._lock:
            if self.language in ("ar", "both") and text_ar:
                self._play_tts(text_ar, lang="ar")
                time.sleep(0.3)

            if self.language in ("en", "both"):
                self._play_tts(text_en, lang="en")

    def _play_tts(self, text: str, lang: str = "en"):
        """Generate and play a single TTS audio clip."""
        tmp_path = None
        try:
            tts = gTTS(text=text, lang=lang, slow=False)

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
                tts.save(tmp_path)

            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)

        except Exception as e:
            print(f"⚠️  TTS Error [{lang}]: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    def stop(self):
        """Stop any currently playing audio."""
        if self._initialized:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    def cleanup(self):
        """Cleanup resources."""
        if self._initialized:
            try:
                pygame.mixer.quit()
            except Exception:
                pass


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing Bilingual TTS Engine")
    print("=" * 60)

    engine = TTSEngine(language="both", enabled=True)

    text_en = "Warning. Worker number 1 is not wearing a safety helmet. Please put on your safety equipment immediately."
    text_ar = "تحذير. العامل رقم 1 لا يرتدي خوذة السلامة. يرجى ارتداء معدات الحماية فوراً."

    engine.speak(text_en=text_en, text_ar=text_ar, blocking=True)

    print("✅ Bilingual TTS test complete!")
    engine.cleanup()
