"""Az/el calculation from lat/lon, camera pixel projection, and camera selection."""
from __future__ import annotations

import math

from tracker.config import CameraConfig

EARTH_RADIUS_M = 6371000.0


def observer_to_target_az_el(
    observer_lat: float,
    observer_lon: float,
    observer_alt_m: float,
    target_lat: float,
    target_lon: float,
    target_alt_m: float,
) -> tuple[float, float]:
    """Azimuth (0-360, from North) and elevation (degrees) of a target as seen from observer."""
    lat1, lon1 = math.radians(observer_lat), math.radians(observer_lon)
    lat2, lon2 = math.radians(target_lat), math.radians(target_lon)
    dlon = lon2 - lon1

    ground_distance = EARTH_RADIUS_M * math.acos(
        max(-1.0, min(1.0, math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(dlon)))
    )

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    azimuth = (math.degrees(math.atan2(y, x))) % 360

    # Earth-curvature drop of the target relative to a flat tangent plane at the observer.
    curvature_drop = (ground_distance ** 2) / (2 * EARTH_RADIUS_M)
    height_diff = (target_alt_m - observer_alt_m) - curvature_drop
    elevation = math.degrees(math.atan2(height_diff, ground_distance)) if ground_distance else 90.0

    return azimuth, elevation


def camera_to_world(pan: float, tilt: float, camera: CameraConfig) -> tuple[float, float]:
    """Convert raw pan/tilt sensor units into the camera's current pointing az/el."""
    azimuth = (pan - camera.pan_offset) * camera.pan_scale
    elevation = (tilt - camera.tilt_offset) * camera.tilt_scale
    return azimuth, elevation


def world_to_pixel(
    target_az: float, target_el: float, cam_az: float, cam_el: float, camera: CameraConfig
) -> tuple[int, int]:
    delta_az = ((target_az - cam_az + 180) % 360) - 180  # shortest angular delta
    delta_el = target_el - cam_el
    px = camera.img_w / 2 + (delta_az / camera.fov_h) * camera.img_w
    py = camera.img_h / 2 - (delta_el / camera.fov_v) * camera.img_h
    return int(px), int(py)


def is_in_frame(px: int, py: int, img_w: int, img_h: int) -> bool:
    return 0 <= px <= img_w and 0 <= py <= img_h


def select_cameras(azimuth: float, elevation: float, cameras: dict[str, CameraConfig]) -> list[CameraConfig]:
    """Return all cameras whose coverage zone contains the given az/el (may overlap)."""
    return [cam for cam in cameras.values() if cam.covers(azimuth, elevation)]
