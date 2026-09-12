"""Fraud detection rules engine."""

import datetime
import math
import os
from typing import Any

# Threshold for flagging a transaction
FLAGGING_THRESHOLD = 0.60

# Geographic Impossibility Configuration Modes
GEO_MODE_SPEED = "speed"
GEO_MODE_FIXED_WINDOW = "fixed_window"

# Feature flag / default config: "speed" for physical-plausibility, "fixed_window" for legacy 8-hour rule
DEFAULT_GEO_IMPOSSIBILITY_MODE = os.getenv("GEO_IMPOSSIBILITY_MODE", GEO_MODE_SPEED)
DEFAULT_MAX_SPEED_KMH = float(os.getenv("GEO_MAX_SPEED_KMH", "900.0"))
DEFAULT_FIXED_WINDOW_HOURS = float(os.getenv("GEO_FIXED_WINDOW_HOURS", "8.0"))

# Approximate country centroid coordinates (latitude, longitude)
COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "AU": (-25.2744, 133.7751),  # Australia
    "CA": (56.1304, -106.3468),  # Canada
    "DE": (51.1657, 10.4515),    # Germany
    "FR": (46.2276, 2.2137),     # France
    "GB": (55.3781, -3.4360),    # United Kingdom
    "JP": (36.2048, 138.2529),   # Japan
    "US": (37.0902, -95.7129),   # United States
}

# Static lookup table for approximate distance in kilometers between country centroids
COUNTRY_DISTANCES: dict[tuple[str, str], float] = {
    ("AU", "AU"): 0.0,
    ("AU", "CA"): 14152.0,
    ("AU", "DE"): 14466.0,
    ("AU", "FR"): 15159.0,
    ("AU", "GB"): 15206.0,
    ("AU", "JP"): 6852.0,
    ("AU", "US"): 15185.0,
    ("CA", "CA"): 0.0,
    ("CA", "DE"): 6751.0,
    ("CA", "FR"): 6841.0,
    ("CA", "GB"): 5807.0,
    ("CA", "JP"): 8083.0,
    ("CA", "US"): 2262.0,
    ("DE", "DE"): 0.0,
    ("DE", "FR"): 816.0,
    ("DE", "GB"): 1033.0,
    ("DE", "JP"): 9048.0,
    ("DE", "US"): 7862.0,
    ("FR", "FR"): 0.0,
    ("FR", "GB"): 1091.0,
    ("FR", "JP"): 9850.0,
    ("FR", "US"): 7666.0,
    ("GB", "GB"): 0.0,
    ("GB", "JP"): 9200.0,
    ("GB", "US"): 6830.0,
    ("JP", "JP"): 0.0,
    ("JP", "US"): 10150.0,
    ("US", "US"): 0.0,
}


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the great-circle distance between two points in km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return 6371.0 * c


def get_country_distance(country1: str | None, country2: str | None) -> float:
    """Looks up or calculates approximate distance in km between two countries."""
    if not country1 or not country2:
        return 0.0
    c1, c2 = str(country1).upper().strip(), str(country2).upper().strip()
    if c1 == c2:
        return 0.0

    if (c1, c2) in COUNTRY_DISTANCES:
        return COUNTRY_DISTANCES[(c1, c2)]
    if (c2, c1) in COUNTRY_DISTANCES:
        return COUNTRY_DISTANCES[(c2, c1)]

    # Centroid fallback if coordinates are defined
    if c1 in COUNTRY_CENTROIDS and c2 in COUNTRY_CENTROIDS:
        lat1, lon1 = COUNTRY_CENTROIDS[c1]
        lat2, lon2 = COUNTRY_CENTROIDS[c2]
        return _haversine_distance(lat1, lon1, lat2, lon2)

    # Generic international distance fallback
    return 5000.0


def evaluate_transaction(
    tx: dict[str, Any],
    user_history: list[dict[str, Any]],
    user_summary: dict[str, Any],
    geo_mode: str | None = None,
) -> tuple[bool, str | None, float]:
    """
    Evaluates a transaction against 5 fraud rules.
    Returns: (is_flagged, flag_reason, fraud_score)
    """
    triggered_rules = []
    total_score = 0.0

    # Rule 1: Velocity Fraud
    # Check if there are >= 4 transactions within the last 3 minutes
    if check_velocity(tx, user_history):
        triggered_rules.append("velocity_fraud")
        total_score += 0.85

    # Rule 2: Geographic Impossibility
    # Physical plausibility speed check (default) or legacy fixed-window check
    if check_geographic_impossibility(tx, user_history, mode=geo_mode):
        triggered_rules.append("geographic_impossibility")
        total_score += 0.90

    # Rule 3: Amount Deviation (Z-Score)
    # Check if amount is > 6 std devs from the mean
    if check_amount_deviation(tx, user_summary):
        triggered_rules.append("amount_deviation")
        total_score += 0.70

    # Rule 4: New Device + High Amount
    # Check if device is new AND amount > 3x average
    if check_new_device_high_amount(tx, user_history, user_summary):
        triggered_rules.append("new_device_plus_high_amount")
        total_score += 0.80

    # Rule 5: Round-Number Structuring
    # Check if amount is a structured round number just below a threshold
    if check_round_number_structuring(tx):
        triggered_rules.append("round_number_structuring")
        total_score += 0.60

    # Cap score at 1.0
    fraud_score = min(1.0, total_score)
    is_flagged = fraud_score >= FLAGGING_THRESHOLD

    flag_reason = ",".join(triggered_rules) if triggered_rules else None

    return is_flagged, flag_reason, fraud_score


def check_velocity(tx: dict[str, Any], user_history: list[dict[str, Any]]) -> bool:
    """True if there are >= 3 other transactions in the past 3 minutes (4 total)."""
    tx_time = tx["transaction_date"]
    window_start = tx_time - datetime.timedelta(minutes=3)

    recent_count = 0
    # user_history is assumed to be ordered by transaction_date ASC
    # We iterate backwards from the end
    for past_tx in reversed(user_history):
        if past_tx["transaction_id"] == tx["transaction_id"]:
            continue
        if past_tx["transaction_date"] >= window_start and past_tx["transaction_date"] <= tx_time:
            recent_count += 1
        elif past_tx["transaction_date"] < window_start:
            break

    return recent_count >= 3


def check_geographic_impossibility(
    tx: dict[str, Any],
    user_history: list[dict[str, Any]],
    mode: str | None = None,
    max_speed_kmh: float | None = None,
    fixed_window_hours: float | None = None,
) -> bool:
    """
    Checks whether a card-present transaction represents an impossible geographic transition.

    Modes:
        - 'speed' (default): Computes distance (km) / elapsed time (hours) between this
          transaction and the prior card-present transaction. Flags only if implied speed >
          max_speed_kmh (default 900 km/h, commercial flight speed with connection margin).
        - 'fixed_window': Flags any card-present transaction occurring in a different country
          from the prior card-present transaction within fixed_window_hours (default 8 hours).
    """
    if not tx.get("card_present"):
        return False

    current_country = tx.get("merchant_country") or tx.get("ip_country")
    if not current_country:
        return False

    effective_mode = mode or DEFAULT_GEO_IMPOSSIBILITY_MODE
    speed_threshold = max_speed_kmh if max_speed_kmh is not None else DEFAULT_MAX_SPEED_KMH
    window_hours = fixed_window_hours if fixed_window_hours is not None else DEFAULT_FIXED_WINDOW_HOURS

    tx_time = tx["transaction_date"]

    # Find the most recent prior card-present transaction
    for past_tx in reversed(user_history):
        if past_tx.get("transaction_id") == tx.get("transaction_id"):
            continue

        past_time = past_tx["transaction_date"]
        if past_time > tx_time:
            continue

        if not past_tx.get("card_present"):
            continue

        past_country = past_tx.get("merchant_country") or past_tx.get("ip_country")
        if not past_country:
            continue

        # 1. Legacy fixed-window mode
        if effective_mode == GEO_MODE_FIXED_WINDOW:
            window_start = tx_time - datetime.timedelta(hours=window_hours)
            if past_time < window_start:
                return False
            return past_country != current_country

        # 2. Physical-plausibility speed check mode (default)
        if past_country == current_country:
            return False

        elapsed_seconds = (tx_time - past_time).total_seconds()
        if elapsed_seconds < 0:
            return False

        elapsed_hours = elapsed_seconds / 3600.0
        distance_km = get_country_distance(current_country, past_country)

        # Virtually simultaneous across different countries -> infinite speed
        if elapsed_hours <= 1e-6:
            return distance_km > 0

        implied_speed_kmh = distance_km / elapsed_hours
        return implied_speed_kmh > speed_threshold

    return False


def check_amount_deviation(tx: dict[str, Any], user_summary: dict[str, Any]) -> bool:
    """True if amount z-score > 6."""
    amount = float(tx["amount"])
    avg_amount = float(user_summary.get("avg_amount", 0.0))
    std_amount = float(user_summary.get("std_amount", 0.0))

    if std_amount <= 0:
        std_amount = max(1.0, avg_amount * 0.1)  # fallback

    z_score = (amount - avg_amount) / std_amount
    return z_score > 6.0


def check_new_device_high_amount(
    tx: dict[str, Any],
    user_history: list[dict[str, Any]],
    user_summary: dict[str, Any],
) -> bool:
    """True if device_id is unseen for this user AND amount is > 3x their average."""
    device_id = tx.get("device_id")
    if not device_id:
        return False

    amount = float(tx["amount"])
    avg_amount = float(user_summary.get("avg_amount", 0.0))

    if amount <= (avg_amount * 3):
        return False

    # Check if device was seen in history
    for past_tx in user_history:
        if past_tx["transaction_id"] == tx["transaction_id"]:
            continue
        if past_tx.get("device_id") == device_id:
            return False  # Device is known

    return True  # Unseen device and high amount


def check_round_number_structuring(tx: dict[str, Any]) -> bool:
    """True if amount is a multiple of 50 and >= 1000, or explicitly $9900 etc."""
    amount = float(tx["amount"])
    if amount < 1000.0:
        return False

    # Structured amounts injected in synthetic data: e.g. 9900, 4950, 2950, etc.
    # Check if amount is a whole number and divisible by 50
    return amount % 50 == 0
