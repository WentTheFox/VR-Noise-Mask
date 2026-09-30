"""Owns the PyAudio stream lifecycle: finds the configured output device,
opens/moves/reopens a stream as it comes and goes, and generates the noise.

On Linux, output goes through PipeWire's Pulse-compat layer (the ALSA "pulse"
device) and is then moved to the matching sink via `pactl move-sink-input` --
opening the raw ALSA hardware device would fight PipeWire for the card.

On Windows, output devices are distinct WASAPI endpoints, so normal PortAudio
device selection by name is used.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

import pyaudio

from .noise import PinkNoise, pct_to_gain

IS_LINUX = sys.platform.startswith("linux")
SINK_EVENT = re.compile(r"'(new|remove)' on sink #")  # not sink-input
SAMPLE_RATE = 48000
CHUNK = 1024


def pactl_list_sinks():
    try:
        out = subprocess.run(
            ["pactl", "-f", "json", "list", "sinks"],
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout
        data = json.loads(out)
        return [(s["name"], s.get("description", s["name"])) for s in data]
    except Exception as e:
        print(f"vr-noise-mask: pactl list sinks failed: {e}")
        return []


def pactl_find_sink(match: str):
    match = match.lower()
    for name, desc in pactl_list_sinks():
        if match in name.lower() or match in desc.lower():
            return name
    return None


def pactl_move_our_stream_to_sink(sink_name, retries=10, delay=0.15):
    pid = os.getpid()
    for _ in range(retries):
        try:
            out = subprocess.run(
                ["pactl", "-f", "json", "list", "sink-inputs"],
                capture_output=True, text=True, timeout=3, check=True,
            ).stdout
            for si in json.loads(out):
                props = si.get("properties", {})
                if str(props.get("application.process.id")) == str(pid):
                    subprocess.run(
                        ["pactl", "move-sink-input", str(si["index"]), sink_name],
                        capture_output=True, text=True, timeout=3,
                    )
                    return True
        except Exception as e:
            print(f"vr-noise-mask: move-sink-input failed: {e}")
        time.sleep(delay)
    return False


class NoiseEngine:
    def __init__(self, volume_pct=10, device_match="index"):
        self.volume_pct = volume_pct
        self.device_match = device_match
        self.enabled = True

        self.pa = pyaudio.PyAudio()
        self.noise = PinkNoise()
        self.stream = None
        self.current_target = None
        self._lock = threading.Lock()
        self._ticker = None
        self._ticker_stop = threading.Event()
        self._wake = threading.Event()
        self._subscriber = None  # `pactl subscribe` process
        self._open_failed = False

    # ---- device discovery ----

    def find_target(self):
        if not self.device_match:
            return None
        if IS_LINUX:
            return pactl_find_sink(self.device_match)
        match = self.device_match.lower()
        for i in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) > 0 and match in info["name"].lower():
                return i
        return None

    def list_candidate_devices(self):
        keywords = ("index", "vr", "hmd", "valve", "vive", "oculus", "wmr")
        out = []
        if IS_LINUX:
            for name, desc in pactl_list_sinks():
                if any(k in desc.lower() or k in name.lower() for k in keywords):
                    out.append((name, desc))
            return out
        for i in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) <= 0:
                continue
            if any(k in info["name"].lower() for k in keywords):
                out.append((i, info["name"]))
        return out

    def list_all_output_devices(self):
        if IS_LINUX:
            return pactl_list_sinks()
        out = []
        for i in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) > 0:
                out.append((i, info["name"]))
        return out

    def _get_pulse_device_index(self):
        for i in range(self.pa.get_device_count()):
            if self.pa.get_device_info_by_index(i)["name"] == "pulse":
                return i
        return None

    # ---- stream lifecycle ----

    def _audio_callback(self, in_data, frame_count, time_info, status):
        gain = pct_to_gain(self.volume_pct)
        chunk = self.noise.next_chunk(frame_count) * gain
        return (chunk.tobytes(), pyaudio.paContinue)

    def _start_stream(self, target):
        with self._lock:
            self._stop_stream_locked()
            try:
                device_index = self._get_pulse_device_index() if IS_LINUX else target
                self.stream = self.pa.open(
                    format=pyaudio.paFloat32,
                    channels=2,
                    rate=SAMPLE_RATE,
                    output=True,
                    output_device_index=device_index,
                    frames_per_buffer=CHUNK,
                    stream_callback=self._audio_callback,
                )
                self.stream.start_stream()
                self.current_target = target
                self._open_failed = False
            except Exception as e:
                print(f"vr-noise-mask: failed to open stream: {e}")
                self.current_target = None
                self._open_failed = True
                return
        if IS_LINUX:
            threading.Thread(
                target=pactl_move_our_stream_to_sink, args=(target,), daemon=True
            ).start()

    def _stop_stream_locked(self):
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.current_target = None

    def stop(self):
        with self._lock:
            self._stop_stream_locked()

    def shutdown(self):
        self._ticker_stop.set()
        self._wake.set()
        if self._subscriber is not None:
            self._subscriber.terminate()
        if self._ticker is not None:
            self._ticker.join(timeout=5)
        self.stop()
        self.pa.terminate()

    # ---- event-driven presence tracking ----

    def poke(self):
        """Ask the ticker thread to re-check device presence now (call after
        changing enabled/device_match)."""
        self._wake.set()

    def start_ticker(self, on_change=None):
        """Run tick() on a background thread whenever poke() is called or
        PipeWire reports a sink appearing/disappearing (`pactl subscribe`);
        on_change() is called when a tick changed the active state. It only
        wakes on its own to retry a failed stream open (or every 2s on
        platforms without sink events)."""
        def loop():
            while True:
                try:
                    if self.tick() and on_change:
                        on_change()
                except Exception as e:
                    print(f"vr-noise-mask: tick failed: {e}")
                retry = self._open_failed or not IS_LINUX
                self._wake.wait(timeout=2.0 if retry else None)
                self._wake.clear()
                if self._ticker_stop.is_set():
                    return
        self._ticker = threading.Thread(target=loop, name="noise-engine-tick", daemon=True)
        self._ticker.start()
        if IS_LINUX:
            threading.Thread(target=self._watch_sinks, name="noise-engine-sinks", daemon=True).start()

    def _watch_sinks(self):
        while not self._ticker_stop.is_set():
            try:
                self._subscriber = subprocess.Popen(
                    ["pactl", "subscribe"], stdout=subprocess.PIPE, text=True
                )
                for line in self._subscriber.stdout:
                    if SINK_EVENT.search(line):
                        self.poke()
            except OSError as e:
                print(f"vr-noise-mask: pactl subscribe failed: {e}")
            # pactl exited (PipeWire restarted?): retry, re-checking on success.
            if self._ticker_stop.wait(5):
                return
            self.poke()

    def tick(self) -> bool:
        """Check device presence and (re)start/stop as needed.
        Returns True if something changed (for the UI to refresh on)."""
        if self.enabled:
            target = self.find_target()
            if target is not None and target != self.current_target:
                self._start_stream(target)
                return True
            elif target is None and self.current_target is not None:
                self.stop()
                return True
        else:
            if self.current_target is not None:
                self.stop()
                return True
        return False

    @property
    def is_active(self) -> bool:
        return self.current_target is not None
