"""Fraud pattern definition and injection logic for synthetic transaction generation."""

import datetime
import hashlib
import random
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class FraudPatternType(str, Enum):
    """The five distinct fraud pattern signatures defined in Section 4."""

    VELOCITY = "velocity_fraud"
    GEOGRAPHIC_IMPOSSIBILITY = "geographic_impossibility"
    AMOUNT_DEVIATION = "amount_deviation"
    NEW_DEVICE_HIGH_AMOUNT = "new_device_plus_high_amount"
    ROUND_NUMBER_STRUCTURING = "round_number_structuring"


@dataclass
class UserProfile:
    """Statistical profile of a baseline user to enable realistic variance and anomaly injection."""

    user_id: int
    home_country: str
    primary_currency: str
    avg_amount: float
    std_amount: float
    known_devices: list[str]
    frequent_categories: list[str]


def create_user_profiles(
    num_users: int,
    countries: list[str],
    country_weights: list[float],
    currencies: list[str],
    currency_weights: list[float],
    categories: list[str],
    rng: random.Random,
) -> dict[int, UserProfile]:
    """Generate baseline statistical profiles for a user population."""
    profiles: dict[int, UserProfile] = {}

    for uid in range(1, num_users + 1):
        home_country = rng.choices(countries, weights=country_weights, k=1)[0]
        currency = rng.choices(currencies, weights=currency_weights, k=1)[0]

        # Log-normal distribution parameters for typical daily user spend ($15 - $200 mean)
        avg_amount = float(rng.uniform(15.0, 150.0))
        std_amount = float(max(5.0, avg_amount * rng.uniform(0.2, 0.5)))

        # 1 to 3 primary devices per user
        num_devices = rng.randint(1, 3)
        devices = [
            hashlib.sha256(f"user_{uid}_device_{d}".encode()).hexdigest()[:16]
            for d in range(num_devices)
        ]

        # 1 to 4 frequent merchant categories
        max_cats = max(1, min(4, len(categories)))
        min_cats = min(2, max_cats)
        k_cats = rng.randint(min_cats, max_cats)
        fav_cats = rng.sample(categories, k=k_cats)

        profiles[uid] = UserProfile(
            user_id=uid,
            home_country=home_country,
            primary_currency=currency,
            avg_amount=avg_amount,
            std_amount=std_amount,
            known_devices=devices,
            frequent_categories=fav_cats,
        )

    return profiles


def generate_baseline_transaction(
    user_profile: UserProfile,
    tx_time: datetime.datetime,
    categories: list[str],
    category_weights: list[float],
    rng: random.Random,
) -> dict[str, Any]:
    """Generate a single legitimate baseline transaction consistent with the user profile."""
    # 70% chance of favorite category, 30% chance of random category
    if rng.random() < 0.70 and user_profile.frequent_categories:
        category = rng.choice(user_profile.frequent_categories)
    else:
        category = rng.choices(categories, weights=category_weights, k=1)[0]

    # Positive spend around user mean
    raw_amount = max(
        1.50,
        rng.gauss(user_profile.avg_amount, user_profile.std_amount),
    )
    amount = Decimal(f"{raw_amount:.2f}")

    # 92% of the time, merchant country and IP country match the user's home country
    m_country = user_profile.home_country
    ip_country = user_profile.home_country

    # Card present is higher for dining/grocery/retail, lower for electronics/travel
    card_present = category in {"dining", "grocery", "retail"} and (rng.random() < 0.80)
    device_id = rng.choice(user_profile.known_devices) if user_profile.known_devices else None

    return {
        "transaction_id": uuid.uuid4(),
        "user_id": user_profile.user_id,
        "transaction_date": tx_time,
        "amount": amount,
        "currency": user_profile.primary_currency,
        "merchant_category": category,
        "merchant_country": m_country,
        "card_present": card_present,
        "device_id": device_id,
        "ip_country": ip_country,
        "is_flagged": False,
        "flag_reason": None,
        "fraud_score": None,
        "created_at": tx_time,
    }


def inject_velocity_fraud(
    user_profile: UserProfile,
    anchor_time: datetime.datetime,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Pattern 1: Velocity Fraud.

    Generates a rapid burst of 4 to 8 transactions within a 30 to 180-second window.
    """
    burst_count = rng.randint(4, 8)
    records: list[dict[str, Any]] = []
    current_time = anchor_time

    for i in range(burst_count):
        if i > 0:
            current_time += datetime.timedelta(seconds=rng.randint(5, 30))
        tx_time = current_time
        amount = Decimal(f"{rng.uniform(80.0, 450.0):.2f}")
        records.append(
            {
                "transaction_id": uuid.uuid4(),
                "user_id": user_profile.user_id,
                "transaction_date": tx_time,
                "amount": amount,
                "currency": user_profile.primary_currency,
                "merchant_category": "electronics" if i % 2 == 0 else "luxury",
                "merchant_country": user_profile.home_country,
                "card_present": False,
                "device_id": rng.choice(user_profile.known_devices)
                if user_profile.known_devices
                else None,
                "ip_country": user_profile.home_country,
                "is_flagged": True,
                "flag_reason": FraudPatternType.VELOCITY.value,
                "fraud_score": None,
                "created_at": tx_time,
            }
        )

    return records


def inject_geographic_impossibility(
    user_profile: UserProfile,
    anchor_time: datetime.datetime,
    all_countries: list[str],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Pattern 2: Geographic Impossibility.

    Two card-present transactions occurring 15-45 minutes apart in geographically distant countries.
    """
    other_countries = [c for c in all_countries if c != user_profile.home_country]
    foreign_country = rng.choice(other_countries) if other_countries else "JP"

    # Transaction 1: Home country
    tx1_time = anchor_time
    tx1 = {
        "transaction_id": uuid.uuid4(),
        "user_id": user_profile.user_id,
        "transaction_date": tx1_time,
        "amount": Decimal(f"{rng.uniform(25.0, 95.0):.2f}"),
        "currency": user_profile.primary_currency,
        "merchant_category": "dining",
        "merchant_country": user_profile.home_country,
        "card_present": True,
        "device_id": rng.choice(user_profile.known_devices) if user_profile.known_devices else None,
        "ip_country": user_profile.home_country,
        "is_flagged": True,
        "flag_reason": FraudPatternType.GEOGRAPHIC_IMPOSSIBILITY.value,
        "fraud_score": None,
        "created_at": tx1_time,
    }

    # Transaction 2: Distant foreign country 20-40 minutes later with card present
    offset_minutes = rng.randint(15, 40)
    tx2_time = anchor_time + datetime.timedelta(minutes=offset_minutes)
    tx2 = {
        "transaction_id": uuid.uuid4(),
        "user_id": user_profile.user_id,
        "transaction_date": tx2_time,
        "amount": Decimal(f"{rng.uniform(350.0, 1800.0):.2f}"),
        "currency": user_profile.primary_currency,
        "merchant_category": "luxury",
        "merchant_country": foreign_country,
        "card_present": True,  # Physical card present on another continent
        "device_id": hashlib.sha256(f"foreign_pos_{uuid.uuid4()}".encode()).hexdigest()[:16],
        "ip_country": foreign_country,
        "is_flagged": True,
        "flag_reason": FraudPatternType.GEOGRAPHIC_IMPOSSIBILITY.value,
        "fraud_score": None,
        "created_at": tx2_time,
    }

    return [tx1, tx2]


def inject_amount_deviation(
    user_profile: UserProfile,
    tx_time: datetime.datetime,
    rng: random.Random,
) -> dict[str, Any]:
    """Pattern 3: Amount Deviation.

    A massive single transaction amount far exceeding the user's normal baseline (z-score > 6-12).
    """
    multiplier = rng.uniform(8.0, 25.0)
    extreme_amount = max(3500.0, user_profile.avg_amount * multiplier)
    amount = Decimal(f"{extreme_amount:.2f}")

    return {
        "transaction_id": uuid.uuid4(),
        "user_id": user_profile.user_id,
        "transaction_date": tx_time,
        "amount": amount,
        "currency": user_profile.primary_currency,
        "merchant_category": "luxury" if rng.random() < 0.6 else "electronics",
        "merchant_country": user_profile.home_country,
        "card_present": False,
        "device_id": rng.choice(user_profile.known_devices) if user_profile.known_devices else None,
        "ip_country": user_profile.home_country,
        "is_flagged": True,
        "flag_reason": FraudPatternType.AMOUNT_DEVIATION.value,
        "fraud_score": None,
        "created_at": tx_time,
    }


def inject_new_device_high_amount(
    user_profile: UserProfile,
    tx_time: datetime.datetime,
    rng: random.Random,
) -> dict[str, Any]:
    """Pattern 4: New Device + High Amount.

    An unseen device ID never in the user's historical profile paired with a high-value purchase.
    """
    new_device_id = hashlib.sha256(f"unseen_rogue_device_{uuid.uuid4()}".encode()).hexdigest()[:16]
    high_amount = max(1800.0, user_profile.avg_amount * rng.uniform(6.0, 15.0))

    return {
        "transaction_id": uuid.uuid4(),
        "user_id": user_profile.user_id,
        "transaction_date": tx_time,
        "amount": Decimal(f"{high_amount:.2f}"),
        "currency": user_profile.primary_currency,
        "merchant_category": "electronics",
        "merchant_country": user_profile.home_country,
        "card_present": False,
        "device_id": new_device_id,
        "ip_country": user_profile.home_country,
        "is_flagged": True,
        "flag_reason": FraudPatternType.NEW_DEVICE_HIGH_AMOUNT.value,
        "fraud_score": None,
        "created_at": tx_time,
    }


def inject_round_number_structuring(
    user_profile: UserProfile,
    tx_time: datetime.datetime,
    structuring_amounts: list[Decimal],
    rng: random.Random,
) -> dict[str, Any]:
    """Pattern 5: Round-Number / Structuring.

    Transactions deliberately structured just under common reporting thresholds (e.g. $9,900, $4,950).
    """
    struct_amount = rng.choice(structuring_amounts)

    return {
        "transaction_id": uuid.uuid4(),
        "user_id": user_profile.user_id,
        "transaction_date": tx_time,
        "amount": struct_amount,
        "currency": user_profile.primary_currency,
        "merchant_category": "retail" if rng.random() < 0.5 else "luxury",
        "merchant_country": user_profile.home_country,
        "card_present": False,
        "device_id": rng.choice(user_profile.known_devices) if user_profile.known_devices else None,
        "ip_country": user_profile.home_country,
        "is_flagged": True,
        "flag_reason": FraudPatternType.ROUND_NUMBER_STRUCTURING.value,
        "fraud_score": None,
        "created_at": tx_time,
    }
