"""Public FastAPI site: countdown to next predicted flyover + clip archive."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from tracker.config import CONFIG_PATH, load_config
from tracker.geometry import observer_to_target_az_el, select_cameras
from tracker.opensky import Aircraft, OpenSkyClient

FLYOVER_HORIZON_S = 600
FLYOVER_STEP_S = 5

config = load_config(CONFIG_PATH)
opensky = OpenSkyClient(
    config.opensky, config.location.lat, config.location.lon, config.opensky.bbox_radius_km
)

os.makedirs(config.recording.output_dir, exist_ok=True)

app = FastAPI(title="Aircraft Tracker")
app.mount("/clips", StaticFiles(directory=config.recording.output_dir), name="clips")


@dataclass
class FlyoverPrediction:
    callsign: str
    icao24: str
    eta_seconds: float
    camera: str


def _seconds_until_coverage(aircraft: Aircraft) -> FlyoverPrediction | None:
    for t in range(0, FLYOVER_HORIZON_S, FLYOVER_STEP_S):
        lat, lon, alt = aircraft.predict(t)
        az, el = observer_to_target_az_el(
            config.location.lat, config.location.lon, config.location.alt_m, lat, lon, alt
        )
        cameras = select_cameras(az, el, config.cameras)
        if cameras:
            return FlyoverPrediction(
                callsign=aircraft.callsign, icao24=aircraft.icao24, eta_seconds=t, camera=cameras[0].name
            )
    return None


@app.get("/api/countdown")
def countdown():
    try:
        aircraft_list = opensky.poll()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenSky poll failed: {exc}") from exc

    predictions = [p for p in (_seconds_until_coverage(a) for a in aircraft_list) if p is not None]
    predictions.sort(key=lambda p: p.eta_seconds)

    if not predictions:
        return {"next_flyover": None}

    next_flyover = predictions[0]
    return {
        "next_flyover": {
            "callsign": next_flyover.callsign,
            "icao24": next_flyover.icao24,
            "eta_seconds": next_flyover.eta_seconds,
            "camera": next_flyover.camera,
        }
    }


@app.get("/api/archive")
def archive():
    output_dir = config.recording.output_dir
    if not os.path.isdir(output_dir):
        return {"clips": []}

    clips = []
    for filename in sorted(os.listdir(output_dir), reverse=True):
        if not filename.endswith(".json"):
            continue
        metadata_path = os.path.join(output_dir, filename)
        clip_filename = filename[: -len(".json")] + ".mp4"
        if not os.path.exists(os.path.join(output_dir, clip_filename)):
            continue
        with open(metadata_path) as f:
            metadata = json.load(f)
        clips.append({**metadata, "clip_url": f"/clips/{clip_filename}"})

    return {"clips": clips}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
