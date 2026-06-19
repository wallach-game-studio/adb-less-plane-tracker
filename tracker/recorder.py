"""FFmpeg-triggered clip recording, metadata sidecar, and VPS sync."""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field

from tracker.config import RecordingConfig, VPSConfig
from tracker.opensky import Aircraft


@dataclass
class ClipMetadata:
    flight_number: str
    icao24: str
    aircraft_type: str | None
    timestamp: float
    predicted_path: list[tuple[float, float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "flight_number": self.flight_number,
            "icao24": self.icao24,
            "aircraft_type": self.aircraft_type,
            "timestamp": self.timestamp,
            "predicted_path": self.predicted_path,
        }


def _clip_basename(aircraft: Aircraft) -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe_callsign = aircraft.callsign.strip().replace(" ", "_") or aircraft.icao24
    return f"{ts}_{safe_callsign}"


def start_recording(
    camera_rtsp: str,
    aircraft: Aircraft,
    config: RecordingConfig,
    predicted_path: list[tuple[float, float, float]] | None = None,
    aircraft_type: str | None = None,
) -> subprocess.Popen:
    """Launch an ffmpeg process recording a fixed-duration clip; returns the process handle."""
    os.makedirs(config.output_dir, exist_ok=True)
    basename = _clip_basename(aircraft)
    clip_path = os.path.join(config.output_dir, f"{basename}.mp4")
    metadata_path = os.path.join(config.output_dir, f"{basename}.json")

    metadata = ClipMetadata(
        flight_number=aircraft.callsign,
        icao24=aircraft.icao24,
        aircraft_type=aircraft_type,
        timestamp=aircraft.timestamp,
        predicted_path=predicted_path or [],
    )
    with open(metadata_path, "w") as f:
        json.dump(metadata.to_dict(), f, indent=2)

    cmd = [
        config.ffmpeg_path,
        "-y",
        "-rtsp_transport", "tcp",
        "-i", camera_rtsp,
        "-t", str(config.clip_duration_s),
        "-c", "copy",
        clip_path,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def sync_clip_to_vps(clip_path: str, metadata_path: str, vps: VPSConfig) -> None:
    """Copy a clip and its metadata sidecar to the VPS over scp."""
    destination = f"{vps.user}@{vps.host}:{vps.remote_path}/"
    subprocess.run(
        ["scp", "-i", os.path.expanduser(vps.ssh_key_path), clip_path, metadata_path, destination],
        check=True,
    )
