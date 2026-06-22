import os

import fastf1
import pandas as pd
from fastf1.ergast import Ergast
from flask import Flask, jsonify
from flask_cors import CORS

CACHE_DIR = os.path.join(os.path.dirname(__file__), "f1_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

app = Flask(__name__)
CORS(app)

ergast = Ergast()


def safe_value(value):
    if pd.isna(value):
        return None
    return value


def format_timedelta(td):
    if pd.isna(td):
        return None
    total_seconds = td.total_seconds()
    minutes, seconds = divmod(total_seconds, 60)
    if minutes >= 1:
        return f"+{int(minutes)}:{seconds:06.3f}"
    return f"+{seconds:.3f}"


@app.route("/api/race/<int:year>/<int:round_number>/results")
def race_results(year, round_number):
    try:
        session = fastf1.get_session(year, round_number, "R")
        session.load(laps=False, telemetry=False, weather=False, messages=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

    results_df = session.results
    winner_time = results_df.iloc[0]["Time"] if len(results_df) > 0 else None

    results = []
    for _, row in results_df.iterrows():
        position = safe_value(row["Position"])
        grid_position = safe_value(row["GridPosition"])
        status = row["Status"] if pd.notna(row["Status"]) else "UNKNOWN"
        is_finished = status == "Finished" or "Lap" in str(status)

        time_str = None
        if is_finished and pd.notna(row["Time"]):
            if position == 1:
                total_seconds = row["Time"].total_seconds()
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"
            else:
                time_str = format_timedelta(row["Time"] - winner_time) if winner_time is not None else None

        results.append({
            "position": int(position) if position is not None else None,
            "gridPosition": int(grid_position) if grid_position is not None else None,
            "driverCode": row["Abbreviation"],
            "driverName": row["FullName"],
            "team": row["TeamName"],
            "teamColor": f"#{row['TeamColor']}" if pd.notna(row["TeamColor"]) else "#888888",
            "time": time_str,
            "fastestLap": False,
            "status": "FINISHED" if is_finished else status.upper(),
            "points": safe_value(row["Points"]),
        })

    try:
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        fastest = session.laps.pick_fastest()
        if fastest is not None and not fastest.empty:
            fastest_driver_code = fastest["Driver"]
            for r in results:
                if r["driverCode"] == fastest_driver_code:
                    r["fastestLap"] = True
    except Exception:
        pass

    event = session.event
    return jsonify({
        "raceInfo": {
            "name": event["EventName"],
            "circuit": event["Location"],
            "round": int(round_number),
            "date": str(event["EventDate"].date()),
        },
        "results": results,
    })


@app.route("/api/standings/drivers")
@app.route("/api/standings/drivers/<int:season>")
def driver_standings(season=None):
    season_param = season if season else "current"
    try:
        standings = ergast.get_driver_standings(season=season_param)
        standings_df = standings.content[0]
    except Exception as e:
        return jsonify({"error": str(e)}), 404

    drivers = []
    for _, row in standings_df.iterrows():
        drivers.append({
            "position": int(row["position"]),
            "driverCode": row.get("driverCode"),
            "driverName": f"{row['givenName']} {row['familyName']}",
            "team": row["constructorNames"][0] if len(row["constructorNames"]) > 0 else None,
            "points": float(row["points"]),
            "wins": int(row["wins"]),
        })

    return jsonify({"season": season_param, "standings": drivers})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)