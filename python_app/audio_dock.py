from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None

DEFAULT_MODEL = "nova-3"
DEFAULT_LANGUAGE = "en-IN"
TRAINING_LABELS = ("double_clap", "single_clap", "noise", "false_trigger", "tap_noise", "speech")
LEGACY_AUDIO_PREFIXES = ("AUDIODOCK_AUDIO:", "UDIODOCK_AUDIO:", "DIODOCK_AUDIO:", "IODOCK_AUDIO:", "AUDIO:")
INDEXED_AUDIO_PATTERN = re.compile(
    r"(?:AUDIODOCK_AUDIO_CHUNK|AUDIODOCK_AUDIO)\s*:\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9A-Fa-f]+)$"
)
MODE_CONTROL_ALIASES = {
    "voice": "mode_voice",
    "voice_mode": "mode_voice",
    "modevoice": "mode_voice",
    "always_listen": "mode_voice",
    "alwayslisten": "mode_voice",
    "vice_city": "mode_voice",
    "vicecity": "mode_voice",
    "clap": "mode_clap",
    "clap_mode": "mode_clap",
    "modeclap": "mode_clap",
    "double_clap": "mode_clap",
    "doubleclap": "mode_clap",
}


@dataclass
class AudioDockCapture:
    capture_id: int
    trigger_label: str
    expected_audio_size: int
    phase: str = "receiving"
    chunks: dict[int, bytes] = field(default_factory=dict)
    legacy_bytes: bytearray = field(default_factory=bytearray)

    def ingest_indexed_chunk(self, chunk_index: int, chunk_len: int, payload_hex: str) -> int:
        if len(payload_hex) % 2 != 0:
            payload_hex = payload_hex[:-1]
        payload = bytes.fromhex(payload_hex)
        payload = payload[: max(0, chunk_len)]
        if not payload:
            return 0
        self.chunks[chunk_index] = payload
        return len(payload)

    def ingest_legacy_chunk(self, payload_hex: str) -> int:
        if len(payload_hex) % 2 != 0:
            payload_hex = payload_hex[:-1]
        payload = bytes.fromhex(payload_hex)
        if not payload:
            return 0
        self.legacy_bytes.extend(payload)
        return len(payload)

    @property
    def received_size(self) -> int:
        if self.chunks:
            return sum(len(chunk) for chunk in self.chunks.values())
        return len(self.legacy_bytes)

    def build_audio_data(self) -> bytes:
        if self.chunks:
            ordered = bytearray()
            for chunk_index in sorted(self.chunks):
                ordered.extend(self.chunks[chunk_index])
            return bytes(ordered[: self.expected_audio_size])
        return bytes(self.legacy_bytes[: self.expected_audio_size])


class AudioDockBridge:
    def __init__(
        self,
        on_log: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_transcript: Callable[[str, str], None] | None = None,
        on_training: Callable[[str], None] | None = None,
        on_training_sample: Callable[[str, Path], None] | None = None,
        serial_bridge: Any | None = None,
        deepgram_api_key: str = "",
        audio_recording_path: Path | None = None,
        training_data_dir: Path | None = None,
    ) -> None:
        self.on_log = on_log
        self.on_status = on_status
        self.on_transcript = on_transcript  # Callback takes (clap_type, text)
        self.on_training = on_training
        self.on_training_sample = on_training_sample
        self.serial_bridge = serial_bridge
        self.is_connected = False
        self.latest_transcript = ""
        self.last_trigger = "-"
        self.status = "Disconnected"
        self.expected_audio_size = None
        self.audio_buffer = bytearray()
        self.deepgram_api_key = deepgram_api_key.strip()
        self.audio_recording_path = audio_recording_path
        self.training_data_dir = training_data_dir
        self.training_label = TRAINING_LABELS[0]
        self.training_capture_remaining = 0
        self.training_saved_count = 0
        self.last_audio_data: bytes | None = None
        self.last_audio_path: Path | None = None
        self.last_training_sample_path: Path | None = None
        self._missing_key_warning_logged = False
        self._capture_lock = threading.Lock()
        self._active_capture: AudioDockCapture | None = None
        self._capture_counter = 0
        self._latest_completed_capture_id = 0

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(f"[Audio Dock] {message}")

    def _set_status(self, status: str) -> None:
        self.status = status
        if self.on_status:
            self.on_status(status)

    def _set_training_status(self, status: str) -> None:
        if self.on_training:
            self.on_training(status)

    @staticmethod
    def _normalize_training_label(label: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", label.strip().lower()).strip("_")
        return normalized or TRAINING_LABELS[0]

    @staticmethod
    def _trigger_label_for_type(clap_type: int) -> str:
        if clap_type == 2:
            return "Double clap"
        if clap_type == 1:
            return "Single clap"
        if clap_type == 3:
            return "Voice command"
        if clap_type == 0:
            return "Training sample"
        return f"Trigger {clap_type}"

    def _clear_displayed_transcript(self, trigger_label: str) -> None:
        self.latest_transcript = ""
        self.last_trigger = trigger_label
        if self.on_transcript:
            self.on_transcript(trigger_label, "")

    def _start_capture(self, trigger_label: str, audio_size: int) -> AudioDockCapture:
        with self._capture_lock:
            self._capture_counter += 1
            capture = AudioDockCapture(
                capture_id=self._capture_counter,
                trigger_label=trigger_label,
                expected_audio_size=max(0, audio_size),
            )
            self._active_capture = capture
            self.expected_audio_size = capture.expected_audio_size
            self.audio_buffer = bytearray()
        self.last_trigger = trigger_label
        self._clear_displayed_transcript(trigger_label)
        return capture

    def _get_active_capture(self) -> AudioDockCapture | None:
        with self._capture_lock:
            return self._active_capture

    def _set_capture_phase(self, capture_id: int, phase: str) -> bool:
        with self._capture_lock:
            if self._active_capture is None or self._active_capture.capture_id != capture_id:
                return False
            self._active_capture.phase = phase
            return True

    def _finish_capture(self, capture_id: int) -> None:
        with self._capture_lock:
            if self._active_capture is not None and self._active_capture.capture_id == capture_id:
                self._active_capture = None
                self.expected_audio_size = None
                self.audio_buffer = bytearray()

    def _capture_is_current(self, capture_id: int) -> bool:
        with self._capture_lock:
            return self._active_capture is not None and self._active_capture.capture_id == capture_id

    def _capture_exists_or_completed(self, capture_id: int) -> bool:
        with self._capture_lock:
            if self._active_capture is not None and self._active_capture.capture_id == capture_id:
                return True
            return capture_id <= self._latest_completed_capture_id

    def load_deepgram_key(self) -> str:
        if self.deepgram_api_key:
            return self.deepgram_api_key
        env_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        if env_key:
            return env_key
        raise RuntimeError("Deepgram API key is not set. Add it in Settings or set DEEPGRAM_API_KEY.")

    def set_deepgram_key(self, api_key: str) -> None:
        self.deepgram_api_key = api_key.strip()
        if self.deepgram_api_key:
            self._missing_key_warning_logged = False

    def arm_training_capture(self, label: str, count: int = 1) -> None:
        self.training_label = self._normalize_training_label(label)
        self.training_capture_remaining = max(1, int(count))
        self._set_training_status(f"Armed: {self.training_label} x{self.training_capture_remaining}")
        self._log(f"Training capture armed for {self.training_label} ({self.training_capture_remaining} clip(s)).")

    def cancel_training_capture(self) -> None:
        self.training_capture_remaining = 0
        self._set_training_status("Capture stopped")
        self._log("Training capture stopped.")

    def save_last_training_sample(self, label: str | None = None) -> Path | None:
        if self.last_audio_data is None:
            self._set_training_status("No clip available")
            self._log("No Audio Dock clip is available to save yet.")
            return None
        path = self._save_training_sample(self.last_audio_data, label or self.training_label, self.last_trigger)
        if path and self.on_training_sample:
            self.on_training_sample(path.parent.name, path)
        return path

    def _save_training_sample(self, audio_data: bytes, label: str, trigger: str) -> Path | None:
        if not self.training_data_dir:
            self._set_training_status("Training folder unavailable")
            return None

        normalized_label = self._normalize_training_label(label)
        label_dir = self.training_data_dir / normalized_label
        label_dir.mkdir(parents=True, exist_ok=True)
        trigger_slug = self._normalize_training_label(trigger if trigger and trigger != "-" else "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = label_dir / f"{timestamp}_{trigger_slug}.wav"
        try:
            path.write_bytes(audio_data)
        except OSError as exc:
            self._set_training_status("Save failed")
            self._log(f"Failed to save training sample: {exc}")
            return None

        self.training_saved_count += 1
        self.last_training_sample_path = path
        status = f"Saved {normalized_label}: {path.name}"
        self._set_training_status(status)
        self._log(f"Saved training sample: {path}")
        return path

    def connect(self, port: str | None = None) -> bool:
        if not self.serial_bridge:
            self._log("Error: Serial bridge reference not set.")
            return False

        if not self.serial_bridge.is_connected:
            self._log("Error: Antenna is not connected. Please connect the Antenna first on the Live Data / Fused Input page.")
            self._set_status("Error")
            return False

        if self.is_connected:
            return True

        self.is_connected = True
        self._set_status("Waiting for Clap")
        self._log("Connected wirelessly via Antenna ESP-NOW bridge.")
        try:
            self.load_deepgram_key()
        except Exception as exc:
            if not self._missing_key_warning_logged:
                self._missing_key_warning_logged = True
                self._log(f"Warning: {exc} Audio will be received, but transcription needs a key.")
        self._log("Waiting for clap detection and audio stream...")
        return True

    def disconnect(self) -> None:
        self.is_connected = False
        self._finish_capture(self._active_capture.capture_id) if self._active_capture is not None else None
        self._set_status("Disconnected")
        self._log("Disconnected.")

    def send_control(self, control: str, **params: Any) -> bool:
        if not self.serial_bridge or not self.serial_bridge.is_connected:
            self._log("Error: Antenna is not connected.")
            return False

        normalized = control.strip().lower()
        aliases = {
            "ledtest": "led_test",
            "led": "led_test",
            "speakertest": "speaker_test",
            "speaker": "speaker_test",
            "spktest": "speaker_test",
            "trainingrecord": "training_record",
            "record_sample": "training_record",
            "sample": "training_record",
        }
        normalized = aliases.get(normalized, normalized)
        normalized = MODE_CONTROL_ALIASES.get(normalized, normalized)
        if normalized not in {"led_test", "speaker_test", "training_record", "mode_voice", "mode_clap"}:
            self._log(f"Unsupported control: {control}")
            return False

        if normalized == "training_record" and not self.is_connected:
            self._log("Error: Audio Dock is not connected in the dashboard. Click Connect before Start Capture.")
            return False

        command = {
            "cmd": "audiodock",
            "control": normalized,
        }
        if normalized == "training_record" and params.get("count") is not None:
            try:
                command["count"] = max(1, min(100, int(params["count"])))
            except (TypeError, ValueError):
                command["count"] = 1
        if self.serial_bridge.send_command(command):
            labels = {
                "led_test": "LED ring test",
                "speaker_test": "speaker test",
                "training_record": "training record",
                "mode_voice": "voice mode",
                "mode_clap": "clap mode",
            }
            label = labels[normalized]
            self._log(f"Sent wireless {label} command.")
            return True

        self._log("Failed to send Audio Dock control command to Antenna.")
        return False

    def _parse_indexed_audio_chunk(self, line: str) -> tuple[int, int, str] | None:
        match = INDEXED_AUDIO_PATTERN.search(line.strip())
        if not match:
            return None
        chunk_index = int(match.group(1))
        chunk_len = int(match.group(2))
        payload_hex = match.group(3)
        if len(payload_hex) < 2:
            return None
        return chunk_index, chunk_len, payload_hex

    def _parse_legacy_audio_hex(self, line: str) -> list[str]:
        normalized = line
        for prefix in LEGACY_AUDIO_PREFIXES:
            normalized = normalized.replace(prefix, "|")
        parts = [part.strip() for part in normalized.split("|")] if "|" in normalized else [normalized.strip()]
        payloads: list[str] = []
        for chunk in parts:
            if not chunk:
                continue
            match = re.search(r"[0-9a-fA-F]+$", chunk)
            if not match:
                continue
            payload_hex = match.group(0)
            if len(payload_hex) < 40:
                continue
            payloads.append(payload_hex)
        return payloads

    def handle_antenna_line(self, line: str) -> None:
        if not self.is_connected:
            return

        if "TRIGGER:" in line:
            current = self._get_active_capture()
            if current is not None and current.phase in {"receiving", "transcribing", "sending"}:
                return
            try:
                trigger_str = line.split("TRIGGER:", 1)[1]
                parts = trigger_str.split(",")
                clap_type = int(parts[0].strip())
                audio_size = int(parts[1].strip())
                trigger_label = self._trigger_label_for_type(clap_type)
                capture = self._start_capture(trigger_label, audio_size)
                self._set_status("Receiving Audio")
                self._log(
                    f"Audio trigger: {capture.trigger_label}. Expecting {capture.expected_audio_size} bytes of WAV audio."
                )
            except Exception as exc:
                self._log(f"Failed to parse trigger: {exc}")
            return

        capture = self._get_active_capture()
        if capture is None or capture.phase != "receiving":
            return

        if not ("AUDIO:" in line or "AUDIO_CHUNK" in line or "AUDIODOCK_AUDIO" in line):
            return

        try:
            indexed_chunk = self._parse_indexed_audio_chunk(line)
            bytes_added = 0
            if indexed_chunk is not None:
                chunk_index, chunk_len, payload_hex = indexed_chunk
                bytes_added = capture.ingest_indexed_chunk(chunk_index, chunk_len, payload_hex)
            else:
                for payload_hex in self._parse_legacy_audio_hex(line):
                    bytes_added += capture.ingest_legacy_chunk(payload_hex)

            if bytes_added <= 0:
                return

            total_len = capture.received_size
            if total_len > 0 and ((total_len // 200) % 40 == 0 or total_len >= capture.expected_audio_size):
                self._log(f"Receiving audio... {total_len}/{capture.expected_audio_size} bytes.")

            if total_len < capture.expected_audio_size:
                return

            if not self._set_capture_phase(capture.capture_id, "transcribing"):
                return

            audio_data = capture.build_audio_data()
            self._latest_completed_capture_id = max(self._latest_completed_capture_id, capture.capture_id)
            self._log("WAV audio successfully received wireless.")

            wav_path = self.audio_recording_path or (Path.cwd() / "last_esp32_recording.wav")
            try:
                wav_path.parent.mkdir(parents=True, exist_ok=True)
                wav_path.write_bytes(audio_data)
                self.last_audio_path = wav_path
            except Exception:
                pass

            self.last_audio_data = audio_data
            self.last_trigger = capture.trigger_label
            training_capture_active = self.training_capture_remaining > 0
            if training_capture_active:
                saved_path = self._save_training_sample(audio_data, self.training_label, capture.trigger_label)
                if saved_path:
                    self.training_capture_remaining -= 1
                    if self.training_capture_remaining > 0:
                        self._set_training_status(f"Armed: {self.training_label} x{self.training_capture_remaining}")
                    else:
                        self._set_training_status(f"Capture complete: {self.training_label}")
                    if self.on_training_sample:
                        self.on_training_sample(saved_path.parent.name, saved_path)

            self._set_status("Saving Sample" if training_capture_active else "Transcribing")
            threading.Thread(
                target=self._transcribe_and_send,
                args=(capture.capture_id, capture.trigger_label, audio_data),
                kwargs={"skip_transcription": training_capture_active},
                daemon=True,
            ).start()
        except Exception as exc:
            self._log(f"Failed to parse audio chunk: {exc}")

    def _transcribe_and_send(
        self,
        capture_id: int,
        trigger_label: str,
        audio_data: bytes,
        *,
        skip_transcription: bool = False,
    ) -> None:
        if skip_transcription:
            self._log("Training sample saved; skipping transcription.")
            transcript = "[Training Sample Saved]"
        else:
            try:
                self._log("Uploading audio to Deepgram API...")
                api_key = self.load_deepgram_key()
                transcript = self._transcribe(audio_data, api_key)
                self._log(f'Transcript: "{transcript}"')
            except Exception as exc:
                self._log(f"Transcribe error: {exc}")
                transcript = "[Transcription Error]"

        if not self._capture_is_current(capture_id):
            self._log(f"Discarded stale transcript result for capture {capture_id}.")
            return

        if not skip_transcription:
            self._set_status("Sending Transcript")
        self.latest_transcript = transcript
        self.last_trigger = trigger_label

        if self.on_transcript:
            self.on_transcript(trigger_label, transcript)

        if not skip_transcription:
            cmd = {
                "cmd": "audiodock",
                "transcript": transcript,
            }
            if self.serial_bridge.send_command(cmd):
                self._log("Transcript command successfully sent to Antenna.")
            else:
                self._log("Failed to send transcript command to Antenna.")

        time.sleep(2.0)
        if self._capture_is_current(capture_id):
            self._finish_capture(capture_id)
            if self.is_connected:
                self._set_status("Waiting for Clap")
                self._log("Waiting for next clap detection...")

    def _transcribe(self, audio: bytes, api_key: str) -> str:
        query = {
            "model": DEFAULT_MODEL,
            "smart_format": "true",
            "language": DEFAULT_LANGUAGE,
        }
        url = "https://api.deepgram.com/v1/listen?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            url,
            data=audio,
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Deepgram HTTP {exc.code}: {details}") from exc

        data = json.loads(body)
        try:
            transcript = data["results"]["channels"][0]["alternatives"][0].get("transcript", "")
            return transcript.strip()
        except Exception:
            raise RuntimeError(f"Deepgram returned invalid JSON: {body}")
