#!/usr/bin/env python3
"""
Export the rollup summary tables to a static JSON file for the public site.

This is the only data that needs to leave the Pi. The site is fully static
(HTML plus this JSON) and the Pi never accepts inbound connections. Run daily
after the rollup, then publish audit_site/audit_data.json. Read-only against
audit.db. Run from the bristol-live-buses folder:
    python audit_export.py
"""
import os
import json
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_DB = os.path.join(HERE, "audit.db")
OUT_DIR = os.path.join(HERE, "audit_site")
OUT_FILE = os.path.join(OUT_DIR, "audit_data.json")

OPERATOR = "FBRI"
OPERATOR_NAME = "First Bristol"
TARGET_PCT = 95
ON_TIME_BAND = "1 minute early to 5 min 59s late (DfT statistical definition)"

OVERALL_COLS = [
    "on_time_pct", "mean_delay_s", "median_delay_s",
    "readings_in_gate", "readings_total", "excluded_distance",
    "median_gate_dist_m", "expected_trips", "observed_trips", "coverage_pct",
]
ROUTE_COLS = [
    "route", "on_time_pct", "mean_delay_s", "median_delay_s",
    "readings_in_gate", "on_time", "early", "late",
    "expected_trips", "observed_trips", "coverage_pct",
]


def build_day(cur, service_date):
    cur.execute("SELECT * FROM daily_overall_summary WHERE service_date = ?", (service_date,))
    overall_row = cur.fetchone()
    overall = {column: overall_row[column] for column in OVERALL_COLS}

    cur.execute(
        """SELECT * FROM daily_route_summary
           WHERE service_date = ? AND route IS NOT NULL
           ORDER BY readings_in_gate DESC""",
        (service_date,),
    )
    routes = [{column: row[column] for column in ROUTE_COLS} for row in cur.fetchall()]

    return {"service_date": service_date, "overall": overall, "routes": routes}


def main():
    if not os.path.exists(AUDIT_DB):
        print(f"audit.db not found at {AUDIT_DB}")
        return

    conn = sqlite3.connect(AUDIT_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT service_date FROM daily_overall_summary ORDER BY service_date")
    except sqlite3.OperationalError:
        print("No rollup tables yet, run: python audit_rollup.py")
        return

    dates = [row[0] for row in cur.fetchall()]
    if not dates:
        print("No rollup rows yet.")
        return

    payload = {
        "operator": OPERATOR,
        "operator_name": OPERATOR_NAME,
        "target_pct": TARGET_PCT,
        "on_time_band": ON_TIME_BAND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": [build_day(cur, service_date) for service_date in dates],
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as out:
        json.dump(payload, out, indent=2)
    print(f"Wrote {OUT_FILE}  ({len(dates)} day(s): {', '.join(dates)})")


if __name__ == "__main__":
    main()
