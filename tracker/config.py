"""Load and expose tunable configuration from config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class LocationConfig:
    lat: float
    lon: float
    alt_m: float


@dataclass
class HomeAssistantConfig:
    url: str
    token: str


@dataclass
class OpenSkyConfig:
    username: str
    password: str
    poll_interval_s: float
    bbox_radius_km: float
    prediction_seconds: float


@dataclass
class DetectionConfig:
    accept_radius: int
    roi_r: int
    min_area: float
    max_area: float
    blob_color: int


@dataclass
class RecordingConfig:
    output_dir: str
    clip_duration_s: float
    ffmpeg_path: str


@dataclass
class VPSConfig:
    host: str
    user: str
    ssh_key_path: str
    remote_path: str
    domain: str


@dataclass
class CameraConfig:
    name: str
    az_min: float
    az_max: float
    el_min: float
    el_max: float
    rtsp: str
    pan_entity: str
    tilt_entity: str
    pan_scale: float
    pan_offset: float
    tilt_scale: float
    tilt_offset: float
    fov_h: float
    fov_v: float
    img_w: int
    img_h: int

    def covers(self, azimuth: float, elevation: float) -> bool:
        """Whether a given az/el falls within this camera's coverage zone."""
        if not (self.el_min <= elevation <= self.el_max):
            return False
        az = azimuth % 360
        lo = self.az_min % 360
        hi = self.az_max % 360
        if lo <= hi:
            return lo <= az <= hi
        return az >= lo or az <= hi  # zone wraps past 360/0


@dataclass
class Config:
    location: LocationConfig
    home_assistant: HomeAssistantConfig
    opensky: OpenSkyConfig
    detection: DetectionConfig
    recording: RecordingConfig
    vps: VPSConfig
    cameras: dict[str, CameraConfig] = field(default_factory=dict)


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    cameras = {
        name: CameraConfig(name=name, **cam_raw)
        for name, cam_raw in raw["cameras"].items()
    }

    return Config(
        location=LocationConfig(**raw["location"]),
        home_assistant=HomeAssistantConfig(**raw["home_assistant"]),
        opensky=OpenSkyConfig(**raw["opensky"]),
        detection=DetectionConfig(**raw["detection"]),
        recording=RecordingConfig(**raw["recording"]),
        vps=VPSConfig(**raw["vps"]),
        cameras=cameras,
    )


CONFIG_PATH = os.environ.get("TRACKER_CONFIG", "config.yaml")
