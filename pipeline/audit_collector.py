#!/usr/bin/env python3
"""
audit_collector.py  --  CONTINUOUS TIMING-POINT PUNCTUALITY LOGGER

Data-collection arm of the open-source First Bus audit. Runs forever, polling
the BODS SIRI-VM feed every POLL_INTERVAL_SECONDS, matching each live First Bus
vehicle to its GTFS timetable, and recording how late/early it was each time it
passed a TIMING POINT (the stops the Traffic Commissioner / DfT measure
punctuality at).

READ-ONLY against timetable.db; writes ONLY to its own audit.db. Does not touch
app.py, the live website, or busbot.

MATCHING (important -- learned the hard way):
  First Bus's SIRI DatedVehicleJourneyRef is the scheduled departure time as
  HHMM (e.g. '1825' = 18:25), NOT a GTFS vehicle_journey_code, so exact
  journey-code matching is meaningless for FBRI. We match the same way the live
  site does and the Traffic Commissioner standard implies: by route +
  direction + first-stop departure-time window + calendar day (the "fuzzy"
  matcher ported from app.py's get_schedule_fuzzy).

SCHEDULED TIMES:
  Each stop's scheduled time is anchored to the matched trip's OWN first-stop
  GTFS offset (handles >24:00:00 and avoids the day-rollover bug that the
  origin-vs-clock heuristic in app.py's parse_schedule_time_py suffers from).

METHODOLOGY (kept conservative for credibility):
  * "On time" = official band: 1 min early to 5 min 59s late, i.e.
    observed_delay_s in [-60, +359].
  * Delay is measured when the bus is PHYSICALLY CLOSEST to a timing point
    (GPS / Haversine), within MAX_GPS_DISTANCE_M. We keep the single closest
    reading per (service_date, trip, stop).
  * A sanity band drops physically-impossible delays (data errors), logged
    separately so the audit can report how much was discarded.
  * Every poll's success/failure + counts are logged so collector uptime is
    auditable.

Run from the bristol-live-buses folder:
    python audit_collector.py
Needs BODS_API_KEY in .env (the same one app.py uses).
"""

import os
import sqlite3
import time
import math
import signal
from datetime import datetime, timedelta, timezone, time as time_obj
from urllib.parse import quote

import requests
import xmltodict
from dateutil import tz
from dateutil.parser import isoparse
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config -- mirrors app.py
# ---------------------------------------------------------------------------
load_dotenv()
API_KEY = os.getenv("BODS_API_KEY")
HERE = os.path.dirname(os.path.abspath(__file__))
TIMETABLE_DB = os.path.join(HERE, "timetable.db")      # read-only
AUDIT_DB = os.path.join(HERE, "audit.db")              # our own output

BOUNDING_BOX = "-3.1150604039022,51.2730967430816,-2.25213125341167,51.6773024336158"
OPERATOR = "FBRI"                 # First Bristol; the audit's subject
TARGET_TZ_STR = "Europe/London"

POLL_INTERVAL_SECONDS = 30
MAX_GPS_DISTANCE_M = 1000         # 1km, identical to app.py
MAX_JOURNEY_AGE_HOURS = 2
FETCH_TIMEOUT_SECONDS = 30
MAX_FETCH_RETRIES = 2

# Sanity band for a single timing-point delay. Anything outside this is almost
# certainly a data/matching error, not a real bus -45 min early. Dropped and
# counted, never silently kept.
SANITY_MIN_S = -15 * 60          # 15 min early
SANITY_MAX_S = 90 * 60           # 90 min late

# Official on-time band (seconds): 1 min early .. 5 min 59s late
ON_TIME_LOW_S = -60
ON_TIME_HIGH_S = 359

TARGET_TZ = tz.gettz(TARGET_TZ_STR) or tz.tzlocal()
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ---------------------------------------------------------------------------
# Pure helpers (copied in behaviour from app.py)
# ---------------------------------------------------------------------------
def get_nested_value(data, path):
    if data is None:
        return None
    val = data
    for key in path.split("/"):
        if not isinstance(val, dict):
            return None
        found = None
        for p_key in (key, f"siri:{key}"):
            found = val.get(p_key)
            if found is not None:
                break
        val = found
        if val is None:
            return None
    if isinstance(val, dict) and "#text" in val:
        val = val["#text"]
    return val


def parse_iso_datetime_utc(timestamp_str):
    if not timestamp_str:
        return None
    try:
        dt = isoparse(timestamp_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def gtfs_seconds(gtfs_time_str):
    """GTFS 'HH:MM:SS' -> seconds since service-day midnight (HH may be >=24)."""
    if not gtfs_time_str:
        return None
    try:
        p = gtfs_time_str.split(":")
        h, m = int(p[0]), int(p[1])
        s = int(p[2]) if len(p) > 2 else 0
        if not (0 <= m <= 59 and 0 <= s <= 59):
            return None
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return None


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def fetch_live_data(api_key, bounding_box):
    if not api_key:
        return None
    url = (f"https://data.bus-data.dft.gov.uk/api/v1/datafeed/"
           f"?boundingBox={quote(bounding_box)}&api_key={api_key}")
    for attempt in range(MAX_FETCH_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS)
            resp.raise_for_status()
            d = xmltodict.parse(resp.text)
            vm = d.get("Siri", {}).get("ServiceDelivery", {}).get("VehicleMonitoringDelivery", {})
            if isinstance(vm, list):
                vm = vm[0] if vm else {}
            acts = vm.get("VehicleActivity", [])
            if acts and not isinstance(acts, list):
                acts = [acts]
            return acts
        except requests.exceptions.Timeout:
            if attempt < MAX_FETCH_RETRIES:
                time.sleep((attempt + 1) * 10)
            else:
                print("SIRI API timeout after retries")
        except requests.exceptions.ConnectionError as e:
            if attempt < 1:
                print(f"SIRI network error, retrying in 5s: {e}")
                time.sleep(5)
            else:
                print(f"SIRI network error - giving up: {e}")
                break
        except Exception as e:
            print(f"ERROR fetching live data: {e}")
            return None
    return None


def fuzzy_match_trip(cur, line_name, direction_ref, origin_local):
    """Port of app.py's get_schedule_fuzzy. Match by route_short_name +
    (direction) + first-stop departure time within +/-10 min + calendar day.
    Returns (trip_id, route_short_name, rows) or (None, None, None) where each
    row is (stop_sequence, departure_time, timepoint, stop_code, lat, lon)."""
    if not line_name or line_name in ("Unknown", ""):
        return None, None, None

    direction_id = None
    dr = (direction_ref or "").lower().strip()
    if dr == "outbound":
        direction_id = 0
    elif dr == "inbound":
        direction_id = 1

    today_str = origin_local.strftime("%Y%m%d")
    lo = origin_local - timedelta(minutes=10)
    hi = origin_local + timedelta(minutes=10)
    lo_t = f"{lo.hour:02d}:{lo.minute:02d}:{lo.second:02d}"
    hi_t = f"{hi.hour:02d}:{hi.minute:02d}:{hi.second:02d}"
    search_sets = [(lo_t, hi_t, DAYS[origin_local.weekday()], today_str)]

    # Early morning: also try previous service day with GTFS 24+ hour times
    if origin_local.hour < 6:
        prev = origin_local - timedelta(days=1)
        search_sets.append((
            f"{lo.hour + 24:02d}:{lo.minute:02d}:{lo.second:02d}",
            f"{hi.hour + 24:02d}:{hi.minute:02d}:{hi.second:02d}",
            DAYS[prev.weekday()], prev.strftime("%Y%m%d"),
        ))

    for use_direction in (True, False):
        for lower, upper, day_col, date_str in search_sets:
            eff_dir = direction_id if use_direction else None
            dir_clause = "AND t.direction_id = ?" if eff_dir is not None else ""
            sql = f"""
                SELECT t.trip_id, r.route_short_name
                FROM trips t
                JOIN routes r ON t.route_id = r.route_id
                JOIN agency a ON r.agency_id = a.agency_id
                JOIN calendar c ON t.service_id = c.service_id
                JOIN stop_times st ON t.trip_id = st.trip_id
                WHERE r.route_short_name = ? AND a.agency_noc = ?
                {dir_clause}
                AND c.{day_col} = 1
                AND c.start_date <= ? AND c.end_date >= ?
                AND st.stop_sequence = 1
                AND st.departure_time BETWEEN ? AND ?
                LIMIT 1
            """
            params = [line_name, OPERATOR]
            if eff_dir is not None:
                params.append(eff_dir)
            params.extend([date_str, date_str, lower, upper])
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                continue
            trip_id, route_short = row[0], row[1]
            cur.execute(
                """SELECT st.stop_sequence, st.departure_time, st.timepoint,
                          s.stop_code, s.stop_lat, s.stop_lon
                   FROM stop_times st
                   JOIN stops s ON st.stop_id = s.stop_id
                   WHERE st.trip_id = ?
                   ORDER BY st.stop_sequence ASC""",
                (trip_id,),
            )
            rows = cur.fetchall()
            if rows:
                return trip_id, route_short, rows
    return None, None, None


# ---------------------------------------------------------------------------
# Audit DB
# ---------------------------------------------------------------------------
def init_audit_db():
    conn = sqlite3.connect(AUDIT_DB)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS timepoint_observations (
               service_date     TEXT NOT NULL,
               operator         TEXT NOT NULL,
               route            TEXT,
               trip_id          TEXT NOT NULL,
               siri_journey_ref TEXT,
               stop_sequence    INTEGER NOT NULL,
               stop_code        TEXT,
               scheduled_local  TEXT,
               observed_delay_s INTEGER,
               on_time          INTEGER,
               gps_distance_m   INTEGER,
               recorded_at      TEXT,
               vehicle_ref      TEXT,
               PRIMARY KEY (service_date, trip_id, stop_sequence)
           )"""
    )
    cur.execute(
        """CREATE INDEX IF NOT EXISTS idx_obs_date_route
               ON timepoint_observations (service_date, operator, route)"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS poll_log (
               poll_at         TEXT PRIMARY KEY,
               ok              INTEGER,
               vehicles_total  INTEGER,
               fbri_total      INTEGER,
               fbri_matched    INTEGER,
               obs_written     INTEGER,
               dropped_insane  INTEGER
           )"""
    )
    conn.commit()
    return conn


def upsert_observation(cur, obs):
    """Insert, but if one already exists for (service_date, trip, stop), keep
    the reading taken CLOSEST to the stop (most representative passing delay)."""
    cur.execute(
        """INSERT INTO timepoint_observations
               (service_date, operator, route, trip_id, siri_journey_ref,
                stop_sequence, stop_code, scheduled_local, observed_delay_s,
                on_time, gps_distance_m, recorded_at, vehicle_ref)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(service_date, trip_id, stop_sequence) DO UPDATE SET
               observed_delay_s = excluded.observed_delay_s,
               on_time          = excluded.on_time,
               gps_distance_m   = excluded.gps_distance_m,
               recorded_at      = excluded.recorded_at,
               vehicle_ref      = excluded.vehicle_ref,
               route            = excluded.route,
               siri_journey_ref = excluded.siri_journey_ref,
               scheduled_local  = excluded.scheduled_local
           WHERE excluded.gps_distance_m < timepoint_observations.gps_distance_m""",
        obs,
    )


# ---------------------------------------------------------------------------
# One poll cycle
# ---------------------------------------------------------------------------
def poll_once(tt_cur, audit_conn):
    poll_at = datetime.now(timezone.utc)
    acts = fetch_live_data(API_KEY, BOUNDING_BOX)
    audit_cur = audit_conn.cursor()

    if acts is None:
        audit_cur.execute(
            "INSERT OR REPLACE INTO poll_log VALUES (?,?,?,?,?,?,?)",
            (poll_at.isoformat(), 0, 0, 0, 0, 0, 0),
        )
        audit_conn.commit()
        return {"ok": False}

    now_utc = datetime.now(timezone.utc)
    vehicles_total = len(acts)
    fbri_total = 0
    fbri_matched = 0
    obs_written = 0
    dropped_insane = 0

    for a in acts:
        mvj = get_nested_value(a, "MonitoredVehicleJourney")
        if not mvj:
            continue
        if str(get_nested_value(mvj, "OperatorRef") or "") != OPERATOR:
            continue
        fbri_total += 1

        line_name = str(get_nested_value(mvj, "PublishedLineName")
                        or get_nested_value(mvj, "LineRef") or "").strip().rstrip("_")
        if not line_name:
            continue
        try:
            lat = float(get_nested_value(mvj, "VehicleLocation/Latitude"))
            lon = float(get_nested_value(mvj, "VehicleLocation/Longitude"))
        except (TypeError, ValueError):
            continue

        recorded_utc = parse_iso_datetime_utc(get_nested_value(a, "RecordedAtTime"))
        origin_utc = parse_iso_datetime_utc(get_nested_value(mvj, "OriginAimedDepartureTime"))
        if not recorded_utc or not origin_utc:
            continue
        if (now_utc - origin_utc).total_seconds() / 3600.0 > MAX_JOURNEY_AGE_HOURS:
            continue
        origin_local = origin_utc.astimezone(TARGET_TZ)
        direction_ref = str(get_nested_value(mvj, "DirectionRef") or "").lower()

        trip_id, route_short, schedule = fuzzy_match_trip(
            tt_cur, line_name, direction_ref, origin_local
        )
        if not schedule:
            continue
        fbri_matched += 1

        # Anchor the service day to the trip's OWN first-stop GTFS offset, so
        # scheduled times are exact and >24h rolls over correctly.
        first_secs = gtfs_seconds(schedule[0][1])
        if first_secs is None:
            continue
        # GTFS midnight of the service day = scheduled first departure - its offset
        service_midnight = (origin_local - timedelta(seconds=first_secs))
        service_date = service_midnight.strftime("%Y%m%d")
        service_midnight = service_midnight.replace(hour=0, minute=0, second=0, microsecond=0)

        # Closest stop by GPS (same as app.py)
        closest = None
        closest_dist = float("inf")
        for row in schedule:
            seq, dep_time, timepoint, stop_code, slat, slon = row
            if slat is None or slon is None:
                continue
            try:
                dist = haversine_distance(lat, lon, float(slat), float(slon))
            except (TypeError, ValueError):
                continue
            if dist < closest_dist:
                closest_dist = dist
                closest = row
        if closest is None or closest_dist > MAX_GPS_DISTANCE_M:
            continue

        seq, dep_time, timepoint, stop_code, slat, slon = closest
        if int(timepoint or 0) != 1:           # only timing points count
            continue

        stop_secs = gtfs_seconds(dep_time)
        if stop_secs is None:
            continue
        doff, rem = divmod(stop_secs, 86400)
        sched_local = (service_midnight + timedelta(days=doff, seconds=rem))
        observed_delay_s = int(round(
            (recorded_utc - sched_local.astimezone(timezone.utc)).total_seconds()
        ))

        # Drop physically-impossible values (data/matching errors), count them.
        if not (SANITY_MIN_S <= observed_delay_s <= SANITY_MAX_S):
            dropped_insane += 1
            continue

        on_time = 1 if ON_TIME_LOW_S <= observed_delay_s <= ON_TIME_HIGH_S else 0
        siri_ref = str(get_nested_value(mvj, "FramedVehicleJourneyRef/DatedVehicleJourneyRef") or "")
        vehicle_ref = str(get_nested_value(mvj, "VehicleRef") or "")

        upsert_observation(audit_cur, (
            service_date, OPERATOR, route_short, trip_id, siri_ref,
            int(seq), stop_code, sched_local.isoformat(), observed_delay_s,
            on_time, int(closest_dist), recorded_utc.isoformat(), vehicle_ref,
        ))
        if audit_cur.rowcount:
            obs_written += 1

    audit_cur.execute(
        "INSERT OR REPLACE INTO poll_log VALUES (?,?,?,?,?,?,?)",
        (poll_at.isoformat(), 1, vehicles_total, fbri_total, fbri_matched,
         obs_written, dropped_insane),
    )
    audit_conn.commit()
    return {
        "ok": True, "vehicles_total": vehicles_total, "fbri_total": fbri_total,
        "fbri_matched": fbri_matched, "obs_written": obs_written,
        "dropped_insane": dropped_insane,
    }


_running = True


def _stop(signum, frame):
    global _running
    _running = False
    print("\nShutting down after current cycle...")


def main():
    if not API_KEY:
        print("ERROR: BODS_API_KEY not found in .env")
        return
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    audit_conn = init_audit_db()
    tt_conn = sqlite3.connect(f"file:{TIMETABLE_DB}?mode=ro", uri=True)
    tt_cur = tt_conn.cursor()

    print(f"Audit collector started. Polling every {POLL_INTERVAL_SECONDS}s.")
    print(f"  timetable (ro): {TIMETABLE_DB}")
    print(f"  audit out:      {AUDIT_DB}")

    while _running:
        cycle_start = time.time()
        try:
            r = poll_once(tt_cur, audit_conn)
            ts = datetime.now(TARGET_TZ).strftime("%H:%M:%S")
            if r.get("ok"):
                print(f"[{ts}] {r['fbri_total']:>3} FBRI live | "
                      f"{r['fbri_matched']:>3} matched | "
                      f"{r['obs_written']:>3} obs | "
                      f"{r['dropped_insane']:>2} dropped")
            else:
                print(f"[{ts}] feed fetch FAILED (logged)")
        except Exception as e:
            print(f"Poll error (continuing): {e}")
        elapsed = time.time() - cycle_start
        sleep_for = max(1, POLL_INTERVAL_SECONDS - elapsed)
        for _ in range(int(sleep_for)):
            if not _running:
                break
            time.sleep(1)

    tt_conn.close()
    audit_conn.close()
    print("Collector stopped cleanly.")


if __name__ == "__main__":
    main()
