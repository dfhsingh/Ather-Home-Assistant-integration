"""Ride Manager for Ather Electric."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
import json
import requests

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    MetaData,
    Table,
    create_engine,
    inspect,
    text,
)


from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder

from .api import AtherAPI

_LOGGER = logging.getLogger(__name__)

Base = declarative_base()


class AtherRide(Base):
    """Ather Ride Table Definition."""

    __tablename__ = "ather_rides"

    ride_id = Column(
        String, primary_key=True
    )  # ride_id in JSON is a large number, safe to store as String or BigInt. Using String for compatibility.
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    distance_km = Column(Float)
    avg_speed = Column(Float)
    top_speed = Column(Float)
    energy_consumed_kwh = Column(Float, nullable=True)  # 'energy_consumed_kWh'
    efficiency_km_kwh = Column(Float)
    created_at = Column(DateTime(timezone=True), default=datetime.now)

    # Note on fields:
    # JSON has: ride_id, distance_m, duration_secs, efficiency_wh_km, efficiency_km_kwh,
    # ride_end_time, ride_start_time (epoch ms), ride_start_lat/lon, ride_end_lat/lon
    # max_display_speed_kmph, avg_display_speed_kmph

    # User Schema request:
    # ride_id (SERIAL? JSON has explicit ID, better to use that)
    # start_time, end_time
    # distance_km
    # avg_speed, top_speed
    # energy_consumed_kWh (Not in API directly, but have efficiency_wh_km * distance_km?)
    # efficiency_km_kwh


class RideManager:
    """Manages ride data fetching and storage."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: AtherAPI,
        scooter_id: str,
        api_token: str,
        retention_months: int = 13,
        tsdb_url: str | None = None,
        tsdb_type: str | None = None,
    ) -> None:
        """Initialize Ride Manager."""
        self.hass = hass
        self.api = api
        self.scooter_id = scooter_id
        self.api_token = api_token
        self.retention_months = retention_months
        self.tsdb_url = tsdb_url
        self.tsdb_type = (
            tsdb_type or "victoriametrics"
        )  # Default to VM if not specified but URL is present
        self._db_url = None
        self._engine = None
        self._session_maker = None

    async def async_init(self) -> None:
        """Initialize DB connection and table."""
        try:
            # Get Recorder DB URL
            recorder_instance = recorder.get_instance(self.hass)
            if not recorder_instance:
                _LOGGER.error("Recorder instance not found. Cannot initialize Ride DB.")
                return

            self._db_url = recorder_instance.db_url
            _LOGGER.debug("Using Recorder DB URL (redacted credentials)")

            # Create Engine (in executor to avoid blocking)
            await self.hass.async_add_executor_job(self._init_db_sync)

        except Exception as e:
            _LOGGER.error("Error initializing Ride Manager: %s", e)

    def _init_db_sync(self):
        """Synchronous DB initialization."""
        try:
            if not self._db_url:
                return

            self._engine = create_engine(self._db_url, future=True)
            self._session_maker = sessionmaker(bind=self._engine)

            # Check if table exists
            inspector = inspect(self._engine)
            if not inspector.has_table("ather_rides"):
                _LOGGER.info("Creating ather_rides table...")
                Base.metadata.create_all(self._engine)
            else:
                _LOGGER.debug("Table ather_rides already exists.")

        except SQLAlchemyError as e:
            _LOGGER.error("SQLAlchemy Error during init: %s", e)

    async def sync_daily(self):
        """Perform daily sync (limit=10)."""
        _LOGGER.info("Starting Daily Ride Sync...")
        await self._fetch_and_store(limit=10)
        await self.cleanup_old_rides()

    async def sync_initial(self):
        """Perform initial sync (limit=100) only if DB is empty."""
        count = await self.hass.async_add_executor_job(self._get_ride_count_sync)
        if count > 0:
            _LOGGER.info(
                "Rides already exist in DB (%d). Skipping initial 100-ride fetch.",
                count,
            )
            return

        _LOGGER.info("Starting Initial Ride Sync (Fresh Install)...")
        await self._fetch_and_store(limit=100)

    async def sync_startup(self):
        """Perform startup sync based on DB state."""
        count = await self.hass.async_add_executor_job(self._get_ride_count_sync)
        if count == 0:
            _LOGGER.info("Startup: DB Empty. Fetching history (limit=100).")
            await self._fetch_and_store(limit=100)
        else:
            _LOGGER.info("Startup: DB has %d rides. Fetching recent (limit=10).", count)
            await self._fetch_and_store(limit=10)

    def _get_ride_count_sync(self) -> int:
        """Count rides in DB synchronously."""
        if not self._session_maker:
            return 0
        session = self._session_maker()
        try:
            return session.query(AtherRide).count()
        except SQLAlchemyError:
            return 0
        finally:
            session.close()

    async def sync_post_ride(self):
        """Perform post-ride sync (limit=1)."""
        _LOGGER.info("Starting Post-Ride Sync...")
        await self._fetch_and_store(limit=5)

    async def _fetch_and_store(self, limit: int):
        """Fetch rides and store in DB."""
        try:
            rides = await self.api.fetch_rides(
                self.scooter_id, self.api_token, limit=limit
            )
            if rides is None:
                _LOGGER.warning("No rides fetched or error occurred.")
                return

            if not rides:
                _LOGGER.debug("Empty ride list returned.")
                return

            _LOGGER.debug("Processing %d fetched rides...", len(rides))
            await self.hass.async_add_executor_job(self._store_rides_sync, rides)

        except Exception as e:
            _LOGGER.error("Error in fetch_and_store: %s", e)

    def _store_rides_sync(self, rides_data: list[dict]):
        """Store rides in DB or TSDB synchronously."""
        # Dispatch to TSDB if configured
        if self.tsdb_url:
            _LOGGER.debug(
                "Attempting to store ride data via driver: %s (URL: %s)",
                self.tsdb_type,
                self.tsdb_url,
            )
            if self.tsdb_type == "victoriametrics":
                self._push_to_victoriametrics(rides_data)
            else:
                _LOGGER.error("Unsupported TSDB type: %s", self.tsdb_type)
            return

        # Fallback to Local SQL
        if not self._session_maker:
            _LOGGER.error("DB Session not initialized.")
            return

        session = self._session_maker()
        new_count = 0
        try:
            for ride in rides_data:
                ride_id = str(ride.get("ride_id"))

                # Check if exists
                existing = session.query(AtherRide).filter_by(ride_id=ride_id).first()
                if existing:
                    continue

                # Parse Data
                # Time is in ms
                start_ts = ride.get("ride_start_time")
                end_ts = ride.get("ride_end_time")

                start_dt = datetime.fromtimestamp(start_ts / 1000) if start_ts else None
                end_dt = datetime.fromtimestamp(end_ts / 1000) if end_ts else None

                # conversions
                dist_km = ride.get("distance_m", 0) / 1000.0

                # speed from "max_display_speed_kmph" / "avg_display_speed_kmph"
                # API gives these directly

                # Energy? efficiency_km_kwh is there.
                # energy_consumed can be derived: distance_km / efficiency_km_kwh
                eff_km_kwh = ride.get("efficiency_km_kwh", 0)
                energy_kwh = (
                    (dist_km / eff_km_kwh) if eff_km_kwh and eff_km_kwh > 0 else 0
                )

                new_ride = AtherRide(
                    ride_id=ride_id,
                    start_time=start_dt,
                    end_time=end_dt,
                    distance_km=round(dist_km, 2),
                    avg_speed=ride.get("avg_display_speed_kmph"),
                    top_speed=ride.get("max_display_speed_kmph"),
                    # I will check if they are in 'ride_details' but getting details for every ride is expensive (N+1).
                    # For now, map what we have.
                    energy_consumed_kwh=round(energy_kwh, 3),
                    efficiency_km_kwh=eff_km_kwh,
                )
                session.add(new_ride)
                new_count += 1

            session.commit()
            _LOGGER.info("Stored %d new rides in local SQL table.", new_count)

        except SQLAlchemyError as e:
            session.rollback()
            _LOGGER.error("Database error storing rides: %s", e)
        finally:
            session.close()

    def _push_to_victoriametrics(self, rides_data: list[dict]):
        """Push rides to VictoriaMetrics TSDB."""
        payload = ""
        count = 0
        for ride in rides_data:
            # Skip if ride is incomplete (no end time)
            if not ride.get("ride_end_time"):
                continue

            ride_id = str(ride.get("ride_id"))
            ts = int(ride.get("ride_end_time"))  # Already in ms

            # Values
            dist_km = ride.get("distance_m", 0) / 1000.0
            avg_spd = ride.get("avg_display_speed_kmph", 0)
            eff_km_kwh = ride.get("efficiency_km_kwh", 0)
            energy = (dist_km / eff_km_kwh) if eff_km_kwh and eff_km_kwh > 0 else 0

            # Helper to create VM JSON lines
            def make_line(name, value, timestamp, rid):
                return (
                    json.dumps(
                        {
                            "metric": {"__name__": name, "ride_id": str(rid)},
                            "values": [float(value)],
                            "timestamps": [int(timestamp)],
                        }
                    )
                    + "\n"
                )

            payload += make_line("ather_ride_distance_km", dist_km, ts, ride_id)
            payload += make_line("ather_ride_avg_speed_kmph", avg_spd, ts, ride_id)
            payload += make_line("ather_ride_energy_consumed_kwh", energy, ts, ride_id)
            payload += make_line(
                "ather_ride_efficiency_km_kwh", eff_km_kwh, ts, ride_id
            )
            count += 1

        if payload:
            try:
                response = requests.post(self.tsdb_url, data=payload, timeout=10)
                if response.status_code == 204:
                    _LOGGER.info(
                        "Successfully pushed %d rides to VictoriaMetrics TSDB.", count
                    )
                else:
                    _LOGGER.error(
                        "Failed to push to TSDB: %s - %s",
                        response.status_code,
                        response.text,
                    )
            except Exception as e:
                _LOGGER.error("Error pushing to TSDB: %s", e)
        else:
            _LOGGER.debug("No valid rides to push to TSDB.")

    async def cleanup_old_rides(self):
        """Delete rides older than retention period."""
        await self.hass.async_add_executor_job(self._cleanup_sync)

    def _cleanup_sync(self):
        """Synchronous cleanup."""
        if not self._session_maker:
            return

        session = self._session_maker()
        try:
            cutoff = datetime.now() - timedelta(days=30 * self.retention_months)
            deleted = (
                session.query(AtherRide).filter(AtherRide.start_time < cutoff).delete()
            )
            session.commit()
            if deleted > 0:
                _LOGGER.info("Cleaned up %d old rides.", deleted)
        except SQLAlchemyError as e:
            session.rollback()
            _LOGGER.error("Error cleaning up old rides: %s", e)
        finally:
            session.close()
