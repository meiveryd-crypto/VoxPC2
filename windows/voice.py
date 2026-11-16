"""Распознавание речи (Google Speech, русский) и озвучка ответов."""
import queue
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


class Speaker:
    """Озвучка ответов через голоса Windows (SAPI) в отдельном потоке."""

    def __init__(self, enabled_fn):
        self.enabled_fn = enabled_fn
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str):
        if text and self.enabled_fn():
            self.q.put(text)

    def _run(self):
        engine = None
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                desc = f"{v.id} {v.name}".lower()
                if any(k in desc for k in ("ru", "russian", "irina", "pavel", "русск")):
                    engine.setProperty("voice", v.id)
                    break
            engine.setProperty("rate", 185)
        except Exception:
            engine = None
        while True:
            text = self.q.get()
            if engine is None:
                continue
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass
