"""Orchestrator loop: poll OpenSky, predict positions, detect blobs, trigger recordings."""
from __future__ import annotations

import logging
import time

from tracker.camera import CameraStream, HomeAssistantClient, detect_blob_near, make_blob_detector
from tracker.config import CONFIG_PATH, load_config
from tracker.geometry import camera_to_world, is_in_frame, observer_to_target_az_el, select_cameras, world_to_pixel
from tracker.opensky import OpenSkyClient
from tracker.recorder import start_recording

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tracker")

RECORDING_COOLDOWN_S = 60


def run() -> None:
    config = load_config(CONFIG_PATH)

    opensky = OpenSkyClient(
        config.opensky, config.location.lat, config.location.lon, config.opensky.bbox_radius_km
    )
    ha_client = HomeAssistantClient(config.home_assistant)
    detector = make_blob_detector(config.detection)
    streams = {name: CameraStream(cam) for name, cam in config.cameras.items()}

    last_recorded_at: dict[str, float] = {}

    log.info("Starting tracker loop (poll every %.1fs)", config.opensky.poll_interval_s)
    while True:
        try:
            aircraft_list = opensky.poll()
        except Exception:
            log.exception("OpenSky poll failed")
            time.sleep(config.opensky.poll_interval_s)
            continue

        for aircraft in aircraft_list:
            now = time.time()
            if now - last_recorded_at.get(aircraft.icao24, 0) < RECORDING_COOLDOWN_S:
                continue

            future_lat, future_lon, future_alt = aircraft.predict(config.opensky.prediction_seconds)
            target_az, target_el = observer_to_target_az_el(
                config.location.lat, config.location.lon, config.location.alt_m,
                future_lat, future_lon, future_alt,
            )

            for camera in select_cameras(target_az, target_el, config.cameras):
                try:
                    pan, tilt = ha_client.get_pan_tilt(camera)
                except Exception:
                    log.exception("Failed reading pan/tilt for %s", camera.name)
                    continue

                cam_az, cam_el = camera_to_world(pan, tilt, camera)
                px, py = world_to_pixel(target_az, target_el, cam_az, cam_el, camera)
                if not is_in_frame(px, py, camera.img_w, camera.img_h):
                    continue

                frame = streams[camera.name].read_frame()
                if frame is None:
                    continue

                hit = detect_blob_near(frame, px, py, detector, config.detection)
                if hit is None:
                    continue

                log.info(
                    "Confirmed %s on %s at pixel %s (predicted %s)",
                    aircraft.callsign, camera.name, hit, (px, py),
                )
                start_recording(
                    camera.rtsp,
                    aircraft,
                    config.recording,
                    predicted_path=[(future_lat, future_lon, future_alt)],
                )
                last_recorded_at[aircraft.icao24] = now

        time.sleep(config.opensky.poll_interval_s)


if __name__ == "__main__":
    run()
