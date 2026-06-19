"""Poll OpenSky Network for live flight states and predict future positions."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import requests

from tracker.config import OpenSkyConfig

OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
EARTH_RADIUS_M = 6371000.0
METERS_PER_DEGREE_LAT = 111320.0


@dataclass
class Aircraft:
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    altitude_m: float
    velocity_ms: float
    heading_deg: float
    vertical_rate_ms: float
    timestamp: float

    def predict(self, dt_s: float) -> tuple[float, float, float]:
        """Predict (lat, lon, altitude_m) dt_s seconds into the future."""
        heading_rad = math.radians(self.heading_deg)
        north_m = self.velocity_ms * math.cos(heading_rad) * dt_s
        east_m = self.velocity_ms * math.sin(heading_rad) * dt_s

        dlat = north_m / METERS_PER_DEGREE_LAT
        meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(self.latitude))
        dlon = east_m / meters_per_degree_lon if meters_per_degree_lon else 0.0

        future_lat = self.latitude + dlat
        future_lon = self.longitude + dlon
        future_alt = self.altitude_m + self.vertical_rate_ms * dt_s
        return future_lat, future_lon, future_alt


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (lamin, lomin, lamax, lomax) around a center point."""
    dlat = radius_km * 1000 / METERS_PER_DEGREE_LAT
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))
    dlon = radius_km * 1000 / meters_per_degree_lon if meters_per_degree_lon else 0.0
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


class OpenSkyClient:
    def __init__(self, config: OpenSkyConfig, home_lat: float, home_lon: float, bbox_radius_km: float):
        self._config = config
        self._home_lat = home_lat
        self._home_lon = home_lon
        self._bbox_radius_km = bbox_radius_km
        self._session = requests.Session()
        if config.username and config.password:
            self._session.auth = (config.username, config.password)

    def poll(self) -> list[Aircraft]:
        lamin, lomin, lamax, lomax = bounding_box(
            self._home_lat, self._home_lon, self._bbox_radius_km
        )
        response = self._session.get(
            OPENSKY_STATES_URL,
            params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        states = payload.get("states") or []

        aircraft = []
        for state in states:
            icao24, callsign = state[0], (state[1] or "").strip()
            longitude, latitude, baro_altitude = state[5], state[6], state[7]
            velocity, true_track, vertical_rate = state[9], state[10], state[11]
            on_ground = state[8]

            if on_ground or latitude is None or longitude is None or baro_altitude is None:
                continue

            aircraft.append(
                Aircraft(
                    icao24=icao24,
                    callsign=callsign or icao24,
                    latitude=latitude,
                    longitude=longitude,
                    altitude_m=baro_altitude,
                    velocity_ms=velocity or 0.0,
                    heading_deg=true_track or 0.0,
                    vertical_rate_ms=vertical_rate or 0.0,
                    timestamp=time.time(),
                )
            )
        return aircraft
