"""Локальное распознавание речи: Vosk ловит ключевое слово, Whisper распознаёт команду.

Всё работает на ПК, без интернета. Модели скачиваются один раз в %APPDATA%\\VoxPC\\models:
  * Vosk small-ru (~45 МБ) — постоянно слушает микрофон, ищет ключевое слово;
  * faster-whisper (large-v3-turbo ~1,6 ГБ, или medium/small) — распознаёт фразу после ключевого слова.
Интерфейс совпадает с voice.VoiceListener: listen_once / start_continuous / stop_continuous.
"""
import collections
import json
import os
import re
import threading
import time
import urllib.request
import zipfile

import wake as wakeword
from config import data_dir

RATE = 16000
CHUNK = 4000                      # 0.25 с
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
VOSK_DIR = "vosk-model-small-ru-0.22"
WHISPER_MODELS = {"large-v3-turbo": "Large v3 Turbo — лучший русский",
                  "medium": "Medium — быстрее",
                  "small": "Small — самый быстрый"}
PROMPT = "Вокс, открой Steam. Глитч, сделай громче. Запусти Discord. Громкость 30. Выключи компьютер."
HALLUCINATIONS = ("субтитр", "продолжение следует", "спасибо за просмотр", "dimatorzok", "подписывайтесь",
                  "редактор субтитров", "корректор")


def models_dir():
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vosk_ready() -> bool:
    return (models_dir() / VOSK_DIR / "am").is_dir()


def download_vosk(progress=lambda msg: None):
    if vosk_ready():
        return
    target = models_dir() / "vosk-ru.zip"
    progress("Скачиваю модель Vosk (45 МБ)…")
    with urllib.request.urlopen(VOSK_URL, timeout=60) as r, open(target, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            f.write(block)
            done += len(block)
            if total:
                progress(f"Скачиваю модель Vosk… {done * 100 // total}%")
    with zipfile.ZipFile(target) as z:
        z.extractall(models_dir())
    target.unlink(missing_ok=True)


class LocalVoice:
    def __init__(self, on_text, on_state, wake_word_fn, config):
        self.on_text = on_text
        self.on_state = on_state
        self.wake_word_fn = wake_word_fn
        self.config = config
        self.vosk_model = None
        self.whisper = None
        self.device = ""
        self.error = ""
        self._stop = threading.Event()
        self._thread = None
        self._manual = threading.Event()
        self._ready = threading.Event()
        self._busy = False
        threading.Thread(target=self._prepare, daemon=True).start()

    # ---------- интерфейс как у VoiceListener ----------
    @property
    def available(self) -> bool:
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            n = pa.get_device_count()
            pa.terminate()
            return n > 0
        except Exception:
            return False

    @property
    def continuous(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._one_shot

    _one_shot = False

    def listen_once(self):
        if not self._ready.is_set():
            self.on_state("error", self.error or "Модели распознавания ещё загружаются…")
            return
        if self._thread and self._thread.is_alive():
            self._manual.set()
            self.on_state("listening", "Слушаю…")
            return
        self._one_shot = True
        self._manual.set()
        self._start()

    def start_continuous(self):
        self._one_shot = False
        if not (self._thread and self._thread.is_alive()):
            self._start()

    def stop_continuous(self):
        self._stop.set()

    # ---------- подготовка моделей ----------
    def _status(self, msg):
        self.on_state("processing", msg)

    def _prepare(self):
        try:
            download_vosk(self._status)
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self.vosk_model = Model(str(models_dir() / VOSK_DIR))
            self._load_whisper()
            self._ready.set()
            self.on_state("idle", f"Распознавание: Vosk + Whisper ({self.device})")
        except Exception as e:
            self.error = f"Локальное распознавание не запустилось: {e}"
            self.on_state("error", self.error)

    def _load_whisper(self):
        from faster_whisper import WhisperModel
        import numpy as np
        name = self.config.get("whisper_model") or "large-v3-turbo"
        root = str(models_dir() / "whisper")
        self._status(f"Загружаю Whisper {name} (первый раз скачивается ~1,6 ГБ, подождите)…")
        last = None
        for endpoint in (None, "https://hf-mirror.com"):
            if endpoint:
                os.environ["HF_ENDPOINT"] = endpoint
            for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
                try:
                    model = WhisperModel(name, device=device, compute_type=ctype, download_root=root)
                    # проверка: на «пустой» видеокарте ошибка вылезает только при первом распознавании
                    list(model.transcribe(np.zeros(RATE // 2, dtype=np.float32), language="ru")[0])
                    self.whisper = model
                    self.device = "видеокарта" if device == "cuda" else "процессор"
                    return
                except Exception as e:
                    last = e
                    if "download" in str(e).lower() or "connect" in str(e).lower():
                        break
        raise RuntimeError(f"не удалось загрузить Whisper: {last}")

    # ---------- распознавание ----------
    def transcribe(self, pcm: bytes) -> str:
        import numpy as np
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self.whisper.transcribe(
            audio, language="ru", beam_size=5, vad_filter=True, initial_prompt=PROMPT,
            condition_on_previous_text=False, no_speech_threshold=0.5)
        text = " ".join(s.text.strip() for s in segments).strip()
        low = text.lower()
        if not text or any(h in low for h in HALLUCINATIONS):
            return ""
        return text

    def _start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @staticmethod
    def _rms(block: bytes) -> float:
        import numpy as np
        a = np.frombuffer(block, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a * a))) if a.size else 0.0

    def _loop(self):
        if not self._ready.wait(timeout=1800):
            return
        try:
            import pyaudio
            from vosk import KaldiRecognizer
        except Exception as e:
            self.on_state("error", f"Нет модулей распознавания: {e}")
            return
        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
        except Exception:
            pa.terminate()
            self.on_state("error", "Микрофон не найден")
            return
        rec = KaldiRecognizer(self.vosk_model, RATE)
        preroll = collections.deque(maxlen=8)        # ~2 с звука до срабатывания
        capture, capturing, manual = [], False, False
        speech_started, silence, noise = False, 0, 300.0
        if not self._one_shot:
            self.on_state("idle", "Жду ключевое слово…")
        try:
            while not self._stop.is_set():
                data = stream.read(CHUNK, exception_on_overflow=False)
                level = self._rms(data)
                if self._manual.is_set() and not capturing:
                    self._manual.clear()
                    capture, capturing, manual = [], True, True
                    speech_started, silence = False, 0
                    self.on_state("listening", "Слушаю…")
                if capturing:
                    capture.append(data)
                    loud = level > max(400.0, noise * 2.2)
                    if loud:
                        speech_started, silence = True, 0
                    else:
                        silence += 1
                    seconds = len(capture) * CHUNK / RATE
                    done = (speech_started and silence >= 4) or seconds > 12 or \
                           (not speech_started and seconds > 6)
                    if done:
                        pcm = b"".join(capture)
                        capturing = False
                        rec.Reset()
                        self._finish(pcm, manual, speech_started)
                        if self._one_shot:
                            break
                    continue
                noise = noise * 0.97 + level * 0.03 if level < noise * 3 else noise
                preroll.append(data)
                if rec.AcceptWaveform(data):
                    heard = json.loads(rec.Result()).get("text", "")
                else:
                    heard = json.loads(rec.PartialResult()).get("partial", "")
                if heard and wakeword.split(heard, self.wake_word_fn() or "")[0]:
                    capture = list(preroll)
                    capturing, manual = True, False
                    speech_started, silence = True, 0
                    rec.Reset()
                    self.on_state("listening", "Слушаю…")
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            pa.terminate()

    def _finish(self, pcm, manual, had_speech):
        if not had_speech:
            self.on_state("idle", "Ничего не услышала")
            return
        self.on_state("processing", "Распознаю…")
        try:
            text = self.transcribe(pcm)
        except Exception as e:
            self.on_state("error", f"Whisper: {e}")
            return
        if not text:
            self.on_state("idle", "Не удалось разобрать речь")
            return
        if manual:
            self.on_state("idle", "")
            self.on_text(text, True)
            return
        found, rest = wakeword.split(text, self.wake_word_fn() or "")
        if not rest.strip():
            # Whisper мог не записать само ключевое слово — тогда вся фраза и есть команда
            rest = text if not found else ""
        rest = re.sub(r"^[\s,.!?]+", "", rest)
        if not rest:
            self._manual.set()                      # сказали только «вокс» — слушаем команду
            return
        self.on_state("idle", f"Жду ключевое слово… Услышала: «{text[:60]}»")
        self.on_text(rest, False)
