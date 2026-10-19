#!/usr/bin/env python3
"""Build a reproducible talk-travel emissions estimate without external APIs.

The source ledger is trip-based so multiple talks at one meeting can share one trip.
Flight distance is airport-to-airport great-circle distance. The calculation then uses
an 8% distance uplift and 2026 UK Government air-passenger conversion factors, with
the methodology's optional 1.7 radiative-forcing multiplier applied to CO2 only.

This is a screening estimate for a personal website, not an audited inventory or an
offset calculation. No network access, API key, package installation, or paid service
is required.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "travel-emissions.json"
FACTORS = ROOT / "data" / "flight-emission-factors-2026.json"
CACHE = ROOT / "data" / "travel-emissions-cache.json"
EPA_TREE_KG_CO2 = 60.0

# Airport coordinates used only for great-circle distance. The travel-update workflow
# also permits one-off destination coordinates for airports not listed here.
AIRPORTS = {
    "IAD": (38.9531, -77.4565),
    "DCA": (38.8512, -77.0402),
    "BWI": (39.1754, -76.6683),
    "BTV": (44.4719, -73.1533),
    "ORD": (41.9742, -87.9073),
    "SAN": (32.7338, -117.1933),
    "SLC": (40.7899, -111.9791),
    "PVD": (41.7240, -71.4282),
    "SXB": (48.5383, 7.6282),
    "HER": (35.3397, 25.1803),
    "SYD": (-33.9399, 151.1753),
    "JFK": (40.6413, -73.7781),
    "LGA": (40.7769, -73.8740),
    "EWR": (40.6895, -74.1745),
    "BOS": (42.3656, -71.0096),
    "ATL": (33.6407, -84.4277),
    "MIA": (25.7959, -80.2870),
    "AUS": (30.1975, -97.6664),
    "LAX": (33.9416, -118.4085),
    "SFO": (37.6213, -122.3790),
    "SJC": (37.3639, -121.9289),
    "PIT": (40.4915, -80.2329),
    "BNA": (36.1263, -86.6774),
    "DTW": (42.2162, -83.3554),
    "YYZ": (43.6777, -79.6248),
    "YUL": (45.4706, -73.7408),
    "VIE": (48.1103, 16.5697),
    "LHR": (51.4700, -0.4543),
    "ICN": (37.4602, 126.4407),
    "ACC": (5.6052, -0.1668),
}


def load_json(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def coordinates(code: str, trip: dict, prefix: str):
    lat_key = f"{prefix}Lat"
    lng_key = f"{prefix}Lng"
    if trip.get(lat_key) is not None and trip.get(lng_key) is not None:
        return float(trip[lat_key]), float(trip[lng_key])
    return AIRPORTS.get(code)


def haversine_km(a, b) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def normalize_trip(raw: dict, defaults: dict, overrides: dict) -> dict:
    trip = copy.deepcopy(raw)
    trip.setdefault("mode", "flight")
    trip.setdefault("origin", defaults.get("origin", "IAD"))
    trip.setdefault("cabin", defaults.get("cabin", "ECONOMY"))
    trip.setdefault("roundTrip", defaults.get("roundTrip", True))
    trip.setdefault("included", True)
    trip["origin"] = str(trip.get("origin") or "").upper()
    trip["destination"] = str(trip.get("destination") or "").upper()
    if trip["destination"] in overrides and "cabin" not in raw:
        trip["cabin"] = overrides[trip["destination"]]
    trip["cabin"] = str(trip.get("cabin") or "ECONOMY").upper()
    return trip


def effective_status(trip: dict, today: dt.date) -> str:
    if trip.get("date"):
        try:
            return "past" if dt.date.fromisoformat(trip["date"]) <= today else "upcoming"
        except ValueError:
            pass
    return str(trip.get("status") or "past").lower()


def segments_for(trip: dict):
    explicit = trip.get("segments") or []
    if explicit:
        return [
            {
                "origin": str(s.get("origin") or "").upper(),
                "destination": str(s.get("destination") or "").upper(),
                "cabin": str(s.get("cabin") or trip["cabin"]).upper(),
                "originLat": s.get("originLat"),
                "originLng": s.get("originLng"),
                "destinationLat": s.get("destinationLat"),
                "destinationLng": s.get("destinationLng"),
            }
            for s in explicit
        ]
    if not trip.get("origin") or not trip.get("destination"):
        return []
    result = [{
        "origin": trip["origin"],
        "destination": trip["destination"],
        "cabin": trip["cabin"],
        "originLat": trip.get("originLat"),
        "originLng": trip.get("originLng"),
        "destinationLat": trip.get("destinationLat"),
        "destinationLng": trip.get("destinationLng"),
    }]
    if trip.get("roundTrip", True):
        result.append({
            "origin": trip["destination"],
            "destination": trip["origin"],
            "cabin": trip["cabin"],
            "originLat": trip.get("destinationLat"),
            "originLng": trip.get("destinationLng"),
            "destinationLat": trip.get("originLat"),
            "destinationLng": trip.get("originLng"),
        })
    return result


def estimate_segment(segment: dict, factors_doc: dict):
    origin = coordinates(segment["origin"], segment, "origin")
    destination = coordinates(segment["destination"], segment, "destination")
    if not origin or not destination:
        return None, f"missing coordinates for {segment['origin']}-{segment['destination']}"

    gcd_km = haversine_km(origin, destination)
    band = "short" if gcd_km < float(factors_doc["shortHaulDistanceProxyKm"]) else "long"
    cabin = segment["cabin"]
    factor = (factors_doc.get("factors") or {}).get(band, {}).get(cabin)
    if not factor:
        return None, f"no {band}-haul factor for cabin {cabin}"

    adjusted_km = gcd_km * float(factors_doc["distanceUplift"])
    rf = float(factors_doc["radiativeForcingMultiplierOnCo2"])
    grams_per_pkm = float(factor["co2"]) * rf + float(factor["ch4"]) + float(factor["n2o"])
    kg_co2e = adjusted_km * grams_per_pkm / 1000.0
    return {
        "origin": segment["origin"],
        "destination": segment["destination"],
        "cabin": cabin,
        "haul": band,
        "greatCircleKm": round(gcd_km, 1),
        "adjustedKm": round(adjusted_km, 1),
        "kgCo2e": round(kg_co2e, 1),
    }, None


def compute(today: dt.date):
    ledger = load_json(LEDGER, {}) or {}
    factors_doc = load_json(FACTORS, {}) or {}
    defaults = ledger.get("defaults") or {}
    overrides = ledger.get("knownCabinOverrides") or {}

    past = 0.0
    upcoming = 0.0
    estimated = 0
    unestimated = 0
    trip_results = []

    for raw in ledger.get("trips") or []:
        trip = normalize_trip(raw, defaults, overrides)
        result = {
            "id": trip.get("id"),
            "label": trip.get("label"),
            "date": trip.get("date"),
            "status": effective_status(trip, today),
            "included": bool(trip.get("included", True)),
            "mode": trip.get("mode", "flight"),
        }
        if not result["included"] or result["mode"] != "flight":
            result["kgCo2e"] = None
            result["note"] = trip.get("note") or "Excluded from flight footprint."
            trip_results.append(result)
            continue

        segment_results = []
        errors = []
        for segment in segments_for(trip):
            estimate, error = estimate_segment(segment, factors_doc)
            if estimate:
                segment_results.append(estimate)
            if error:
                errors.append(error)

        if errors or not segment_results:
            unestimated += 1
            result["kgCo2e"] = None
            result["error"] = "; ".join(errors) if errors else "no flight segments"
        else:
            kg = sum(float(s["kgCo2e"]) for s in segment_results)
            result["kgCo2e"] = round(kg, 1)
            result["segments"] = segment_results
            estimated += 1
            if result["status"] == "upcoming":
                upcoming += kg
            else:
                past += kg
        if trip.get("assumption"):
            result["assumption"] = trip["assumption"]
        if trip.get("note"):
            result["note"] = trip["note"]
        trip_results.append(result)

    summary = {
        "pastKgCo2e": round(past, 1),
        "upcomingKgCo2e": round(upcoming, 1),
        "pastTreeSeedlings10yr": round(past / EPA_TREE_KG_CO2, 1),
        "upcomingTreeSeedlings10yr": round(upcoming / EPA_TREE_KG_CO2, 1),
        "estimatedTrips": estimated,
        "unestimatedTrips": unestimated,
    }
    return {
        "status": "ready",
        "generatedAt": None,
        "factorYear": factors_doc.get("year"),
        "summary": summary,
        "trips": trip_results,
        "coverageNote": ledger.get("coverageNote"),
        "methodology": {
            "flightFactors": factors_doc.get("source"),
            "flightFactorsUrl": factors_doc.get("sourceUrl"),
            "distanceUplift": factors_doc.get("distanceUplift"),
            "radiativeForcingMultiplierOnCo2": factors_doc.get("radiativeForcingMultiplierOnCo2"),
            "shortHaulDistanceProxyKm": factors_doc.get("shortHaulDistanceProxyKm"),
            "treeEquivalency": "U.S. EPA Greenhouse Gas Equivalencies Calculator",
            "treeEquivalencyUrl": "https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator",
            "epaKgCo2PerUrbanTreeSeedling10yr": EPA_TREE_KG_CO2,
        },
        "notes": factors_doc.get("notes") or [],
    }


def main() -> int:
    today = dt.date.today()
    output = compute(today)
    previous = load_json(CACHE, {}) or {}

    comparable_previous = copy.deepcopy(previous)
    comparable_previous["generatedAt"] = None
    comparable_output = copy.deepcopy(output)
    comparable_output["generatedAt"] = None
    if comparable_previous == comparable_output and previous.get("generatedAt"):
        output["generatedAt"] = previous["generatedAt"]
    else:
        output["generatedAt"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    CACHE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Travel footprint: {output['summary']['pastKgCo2e']} kg past travel, "
        f"{output['summary']['upcomingKgCo2e']} kg upcoming travel; "
        f"{output['summary']['estimatedTrips']} estimated, {output['summary']['unestimatedTrips']} unresolved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
