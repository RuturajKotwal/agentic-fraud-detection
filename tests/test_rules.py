import datetime
from decimal import Decimal

from src.rules.engine import (
    evaluate_transaction,
    check_velocity,
    check_geographic_impossibility,
    check_amount_deviation,
    check_new_device_high_amount,
    check_round_number_structuring,
)

def test_check_velocity():
    now = datetime.datetime.now(datetime.UTC)
    tx = {"transaction_id": "tx5", "transaction_date": now, "amount": 100}
    
    # 3 past tx within 3 minutes = 4 total, should trigger
    history_trigger = [
        {"transaction_id": "tx1", "transaction_date": now - datetime.timedelta(minutes=2)},
        {"transaction_id": "tx2", "transaction_date": now - datetime.timedelta(minutes=1)},
        {"transaction_id": "tx3", "transaction_date": now - datetime.timedelta(seconds=30)},
    ]
    assert check_velocity(tx, history_trigger) == True

    # 2 past tx within 3 minutes = 3 total, should NOT trigger
    history_pass = [
        {"transaction_id": "tx1", "transaction_date": now - datetime.timedelta(minutes=4)},
        {"transaction_id": "tx2", "transaction_date": now - datetime.timedelta(minutes=1)},
        {"transaction_id": "tx3", "transaction_date": now - datetime.timedelta(seconds=30)},
    ]
    assert check_velocity(tx, history_pass) == False


def test_check_geographic_impossibility():
    now = datetime.datetime.now(datetime.UTC)
    tx = {
        "transaction_id": "tx2", 
        "transaction_date": now, 
        "merchant_country": "US",
        "card_present": True
    }
    
    # Previous card-present tx in different country within 8 hours
    history_trigger = [
        {
            "transaction_id": "tx1", 
            "transaction_date": now - datetime.timedelta(hours=2),
            "merchant_country": "JP",
            "card_present": True
        }
    ]
    assert check_geographic_impossibility(tx, history_trigger) == True

    # Not card present, should not trigger
    tx_not_present = {**tx, "card_present": False}
    assert check_geographic_impossibility(tx_not_present, history_trigger) == False

    # Previous was in same country, should not trigger
    history_pass = [
        {
            "transaction_id": "tx1", 
            "transaction_date": now - datetime.timedelta(hours=2),
            "merchant_country": "US",
            "card_present": True
        }
    ]
    assert check_geographic_impossibility(tx, history_pass) == False


def test_check_amount_deviation():
    tx = {"amount": 800.0}
    user_summary = {"avg_amount": 50.0, "std_amount": 10.0}
    
    # z_score = (800 - 50) / 10 = 75 (> 6) -> True
    assert check_amount_deviation(tx, user_summary) == True
    
    tx_normal = {"amount": 70.0}
    # z_score = (70 - 50) / 10 = 2 (< 6) -> False
    assert check_amount_deviation(tx_normal, user_summary) == False


def test_check_new_device_high_amount():
    tx = {
        "transaction_id": "tx2",
        "amount": 1000.0,
        "device_id": "device_new"
    }
    user_summary = {"avg_amount": 100.0}
    
    history_unseen = [
        {"transaction_id": "tx1", "device_id": "device_old"}
    ]
    # Unseen device + amount (1000) > 3 * avg (300) -> True
    assert check_new_device_high_amount(tx, history_unseen, user_summary) == True

    history_seen = [
        {"transaction_id": "tx1", "device_id": "device_new"}
    ]
    # Seen device -> False
    assert check_new_device_high_amount(tx, history_seen, user_summary) == False


def test_check_round_number_structuring():
    assert check_round_number_structuring({"amount": 9900.0}) == True
    assert check_round_number_structuring({"amount": 4950.0}) == True
    assert check_round_number_structuring({"amount": 2000.0}) == True
    assert check_round_number_structuring({"amount": 999.0}) == False
    assert check_round_number_structuring({"amount": 9901.0}) == False


def test_evaluate_transaction_combined():
    now = datetime.datetime.now(datetime.UTC)
    tx = {
        "transaction_id": "tx2",
        "transaction_date": now,
        "amount": 4950.0, # Triggers round number (0.6)
        "merchant_country": "US",
        "card_present": True,
        "device_id": "device_new" # Triggers new device high amount (0.8)
    }
    history = [
        {
            "transaction_id": "tx1",
            "transaction_date": now - datetime.timedelta(minutes=30),
            "merchant_country": "JP", # Triggers geo impossibility (0.9)
            "card_present": True,
            "device_id": "device_old"
        }
    ]
    summary = {"avg_amount": 50.0, "std_amount": 10.0}
    # amount deviation z-score = (4950-50)/10 = 490 > 6 (0.7)
    
    # Combined should trigger multiple rules
    is_flagged, flag_reason, fraud_score = evaluate_transaction(tx, history, summary)
    
    assert is_flagged == True
    assert fraud_score == 1.0 # capped at 1.0
    
    reasons = flag_reason.split(",")
    assert "geographic_impossibility" in reasons
    assert "amount_deviation" in reasons
    assert "new_device_plus_high_amount" in reasons
    assert "round_number_structuring" in reasons
    assert "velocity_fraud" not in reasons
