import datetime
from decimal import Decimal
from typing import Any

# Threshold for flagging a transaction
FLAGGING_THRESHOLD = 0.60

def evaluate_transaction(
    tx: dict[str, Any],
    user_history: list[dict[str, Any]],
    user_summary: dict[str, Any]
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
    # Check if the previous card_present tx was in a different country within 8 hours
    if check_geographic_impossibility(tx, user_history):
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


def check_geographic_impossibility(tx: dict[str, Any], user_history: list[dict[str, Any]]) -> bool:
    """True if card is present and previous card_present tx in last 8 hours was in another country."""
    if not tx.get("card_present"):
        return False
        
    tx_time = tx["transaction_date"]
    current_country = tx["merchant_country"]
    window_start = tx_time - datetime.timedelta(hours=8)
    
    for past_tx in reversed(user_history):
        if past_tx["transaction_id"] == tx["transaction_id"]:
            continue
        if past_tx["transaction_date"] < window_start:
            break
        if past_tx.get("card_present"):
            if past_tx["merchant_country"] != current_country:
                return True
            else:
                # Same country, so no impossibility for this jump
                return False
                
    return False


def check_amount_deviation(tx: dict[str, Any], user_summary: dict[str, Any]) -> bool:
    """True if amount z-score > 6."""
    amount = float(tx["amount"])
    avg_amount = float(user_summary.get("avg_amount", 0.0))
    std_amount = float(user_summary.get("std_amount", 0.0))
    
    if std_amount <= 0:
        std_amount = max(1.0, avg_amount * 0.1) # fallback
        
    z_score = (amount - avg_amount) / std_amount
    return z_score > 6.0


def check_new_device_high_amount(
    tx: dict[str, Any], 
    user_history: list[dict[str, Any]], 
    user_summary: dict[str, Any]
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
            return False # Device is known
            
    return True # Unseen device and high amount


def check_round_number_structuring(tx: dict[str, Any]) -> bool:
    """True if amount is a multiple of 50 and >= 1000, or explicitly $9900 etc."""
    amount = float(tx["amount"])
    if amount < 1000.0:
        return False
        
    # Structured amounts injected in synthetic data: e.g. 9900, 4950, 2950, etc.
    # Check if amount is a whole number and divisible by 50
    if amount % 50 == 0:
        return True
        
    return False
