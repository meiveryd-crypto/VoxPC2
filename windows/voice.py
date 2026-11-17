"""Распознавание речи (Google Speech, русский) и озвучка ответов."""
import queue
import urllib.error
import threading
import time

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover
    sr = None


def _norm(s: str) -> str:
    return (s or "").lower().replace("ё", "е").strip()


class VoiceListener:
    """on_text(text, manual) и on_state(state, message); state: idle/listening/processing/error."""

    def __init__(self, on_text, on_state, wake_word_fn):
        self.on_text = on_text
        self.on_state = on_state
        self.wake_word_fn = wake_word_fn
        self.recognizer = sr.Recognizer() if sr else None
        if self.recognizer:
            self.recognizer.pause_threshold = 0.7
        self._busy = False
        self._manual_next = False
        self._stop = threading.Event()
        self._thread = None

    @property
    def available(self) -> bool:
        if not sr:
            return False
        try:
            return len(sr.Microphone.list_microphone_names()) > 0
        except Exception:
            return False

    @property
    def continuous(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---------- одна фраза по кнопке ----------
    def listen_once(self):
        if not sr:
            self.on_state("error", "Установите SpeechRecognition и PyAudio")
            return
        if self.continuous:
            self._manual_next = True
            self.on_state("listening", "Слушаю…")
            return
        if self._busy:
            return
        threading.Thread(target=self._once, daemon=True).start()

    def _once(self):
        self._busy = True
        try:
            with sr.Microphone() as source:
                self.on_state("listening", "Говорите…")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=10)
            self.on_state("processing", "Распознаю…")
            text = self.recognizer.recognize_google(audio, language="ru-RU")
            self.on_state("idle", "")
            self.on_text(text, True)
        except sr.WaitTimeoutError:
            self.on_state("idle", "Ничего не услышал")
        except sr.UnknownValueError:
            self.on_state("idle", "Не удалось разобрать речь")
        except sr.RequestError:
            self.on_state("error", "Нет интернета для распознавания речи")
        except OSError:
            self.on_state("error", "Микрофон не найден")
        except Exception as e:
            self.on_state("error", str(e))
        finally:
            self._busy = False

    # ---------- постоянное прослушивание с ключевым словом ----------
    def start_continuous(self):
        if not sr or self.continuous:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop_continuous(self):
        self._stop.set()

    def _loop(self):
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.on_state("idle", "Жду ключевое слово…")
                while not self._stop.is_set():
                    try:
                        audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=7)
                    except sr.WaitTimeoutError:
                        continue
                    manual = self._manual_next
                    try:
                        text = self.recognizer.recognize_google(audio, language="ru-RU")
                    except sr.UnknownValueError:
                        if manual:
                            self._manual_next = False
                            self.on_state("idle", "Не расслышал")
                        continue
                    except sr.RequestError:
                        self.on_state("error", "Нет интернета для распознавания речи")
                        time.sleep(3)
                        continue
                    self._manual_next = False
                    wake = _norm(self.wake_word_fn())
                    low = _norm(text)
                    if not manual and wake and low.strip(" ,.!") == wake:
                        # сказали только «компьютер» — ждём команду следующей фразой
                        self._manual_next = True
                        self.on_state("listening", "Слушаю…")
                        continue
                    if manual or (wake and low.startswith(wake)):
                        self.on_state("idle", "Жду ключевое слово…")
                        self.on_text(text, manual)
        except OSError:
            self.on_state("error", "Микрофон не найден")
        except Exception as e:
            self.on_state("error", str(e))


EDGE_VOICE = "ru-RU-SvetlanaNeural"


def _play_mp3(path: str):
    """Проигрывает mp3 средствами Windows (MCI) и ждёт окончания."""
    import ctypes
    winmm = ctypes.windll.winmm
    alias = "voxpc_tts"
    winmm.mciSendStringW(f'close {alias}', None, 0, None)
    if winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None) != 0:
        raise OSError("MCI open failed")
    winmm.mciSendStringW(f'play {alias} wait', None, 0, None)
    winmm.mciSendStringW(f'close {alias}', None, 0, None)


class Speaker:
    """Озвучка ответов в отдельном потоке.

    Голос «Глитч»: нейронный голос Microsoft (edge-tts) с повышенным тоном; без интернета
    или без пакета edge-tts — голоса Windows (SAPI).
    on_speaking(True/False) сообщает, когда идёт речь (для анимации рта).
    """

    def __init__(self, enabled_fn, engine_fn=lambda: "edge", on_speaking=None, settings_fn=lambda: {}):
        self.enabled_fn = enabled_fn
        self.engine_fn = engine_fn
        self.settings_fn = settings_fn
        self.last_error = ""
        self.on_speaking = on_speaking or (lambda v: None)
        self.q = queue.Queue()
        self.speaking = False
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str, force: bool = False):
        if text and (force or self.enabled_fn()):
            self.q.put(text)

    def _sapi_engine(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                desc = f"{v.id} {v.name}".lower()
                if any(k in desc for k in ("ru", "russian", "irina", "pavel", "русск")):
                    engine.setProperty("voice", v.id)
                    break
            engine.setProperty("rate", 185)
            return engine
        except Exception:
            return None

    def _edge(self, text: str) -> bool:
        try:
            import asyncio
            import os
            import tempfile
            import edge_tts
        except ImportError:
            return False
        path = os.path.join(tempfile.gettempdir(), "voxpc_tts.mp3")
        try:
            async def synth():
                await edge_tts.Communicate(text, EDGE_VOICE, rate="+6%", pitch="+28Hz").save(path)
            asyncio.run(synth())
            self._set(True)
            _play_mp3(path)
            return True
        except Exception:
            return False

    # ---------- ElevenLabs ----------
    def eleven_synth(self, text: str) -> bytes:
        """Синтез через ElevenLabs API. Короткие фразы кэшируются, чтобы не тратить кредиты."""
        import hashlib
        import json as _json
        import urllib.request
        from config import data_dir
        st = self.settings_fn() or {}
        key, vid = (st.get("elevenlabs_key") or "").strip(), (st.get("elevenlabs_voice") or "").strip()
        if not key or not vid:
            raise ValueError("Не указан API-ключ или Voice ID ElevenLabs")
        model = st.get("elevenlabs_model") or "eleven_multilingual_v2"
        cache_dir = data_dir() / "tts_cache"
        cache = cache_dir / (hashlib.sha1(f"{vid}|{model}|{text}".encode("utf-8")).hexdigest() + ".mp3")
        if cache.exists():
            return cache.read_bytes()
        body = {"text": text, "model_id": model,
                "voice_settings": {"stability": 0.38, "similarity_boost": 0.8, "style": 0.45,
                                   "use_speaker_boost": True}}
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
            data=_json.dumps(body).encode("utf-8"), method="POST",
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                audio = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            raise RuntimeError(f"ElevenLabs {e.code}: {detail}")
        if len(text) <= 80:
            cache_dir.mkdir(exist_ok=True)
            cache.write_bytes(audio)
        return audio

    def _eleven(self, text: str) -> bool:
        import os
        import tempfile
        try:
            audio = self.eleven_synth(text)
            path = os.path.join(tempfile.gettempdir(), "voxpc_tts_el.mp3")
            with open(path, "wb") as f:
                f.write(audio)
            self.last_error = ""
            self._set(True)
            _play_mp3(path)
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def _set(self, value):
        self.speaking = value
        try:
            self.on_speaking(value)
        except Exception:
            pass

    def _run(self):
        sapi = None
        while True:
            text = self.q.get()
            try:
                engine = self.engine_fn()
                done = engine == "elevenlabs" and self._eleven(text)
                if not done and engine in ("edge", "elevenlabs"):
                    done = self._edge(text)
                if not done:
                    if sapi is None:
                        sapi = self._sapi_engine() or False
                    if sapi:
                        self._set(True)
                        try:
                            sapi.say(text)
                            sapi.runAndWait()
                        except Exception:
                            pass
            finally:
                self._set(False)
