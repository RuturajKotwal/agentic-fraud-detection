"""Unit and integration tests for synthetic data generation and fraud patterns."""

import datetime
import random
from decimal import Decimal

import pytest

from src.generator.config import GeneratorConfig
from src.generator.patterns import (
    create_user_profiles,
    generate_baseline_transaction,
    inject_amount_deviation,
    inject_geographic_impossibility,
    inject_new_device_high_amount,
    inject_round_number_structuring,
    inject_velocity_fraud,
)
from src.generator.synthetic_data import generate_transactions


def test_generator_config_validation():
    """Verify GeneratorConfig handles validation boundaries correctly."""
    valid_cfg = GeneratorConfig(total_records=1000, fraud_rate=0.02)
    valid_cfg.validate()

    with pytest.raises(ValueError, match="total_records"):
        GeneratorConfig(total_records=0).validate()

    with pytest.raises(ValueError, match="Fraud rate"):
        GeneratorConfig(fraud_rate=1.5).validate()

    with pytest.raises(ValueError, match="start_date"):
        GeneratorConfig(
            start_date=datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC),
            end_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        ).validate()


def test_user_profiles_creation():
    """Verify user profile statistical attributes."""
    rng = random.Random(42)
    countries = ["US", "GB", "DE"]
    country_weights = [0.7, 0.2, 0.1]
    currencies = ["USD", "EUR"]
    currency_weights = [0.8, 0.2]
    categories = ["dining", "grocery", "electronics"]

    profiles = create_user_profiles(
        num_users=10,
        countries=countries,
        country_weights=country_weights,
        currencies=currencies,
        currency_weights=currency_weights,
        categories=categories,
        rng=rng,
    )

    assert len(profiles) == 10
    for uid, prof in profiles.items():
        assert prof.user_id == uid
        assert prof.home_country in countries
        assert prof.primary_currency in currencies
        assert prof.avg_amount > 0
        assert len(prof.known_devices) >= 1
        assert len(prof.frequent_categories) >= 2


def test_baseline_transaction():
    """Verify baseline transaction format and fields."""
    rng = random.Random(42)
    profiles = create_user_profiles(
        num_users=1,
        countries=["US"],
        country_weights=[1.0],
        currencies=["USD"],
        currency_weights=[1.0],
        categories=["grocery", "dining"],
        rng=rng,
    )
    prof = profiles[1]
    now = datetime.datetime(2024, 5, 10, 12, 0, 0, tzinfo=datetime.UTC)

    tx = generate_baseline_transaction(
        user_profile=prof,
        tx_time=now,
        categories=["grocery", "dining"],
        category_weights=[0.5, 0.5],
        rng=rng,
    )

    assert tx["user_id"] == 1
    assert tx["amount"] > Decimal("0.00")
    assert tx["transaction_date"] == now
    assert tx["is_flagged"] is False
    assert tx["flag_reason"] is None
    assert tx["fraud_score"] is None


def test_pattern_velocity_fraud():
    """Test velocity fraud burst characteristics."""
    rng = random.Random(42)
    profiles = create_user_profiles(
        num_users=1,
        countries=["US"],
        country_weights=[1.0],
        currencies=["USD"],
        currency_weights=[1.0],
        categories=["electronics"],
        rng=rng,
    )
    prof = profiles[1]
    anchor = datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.UTC)

    burst = inject_velocity_fraud(prof, anchor, rng)
    assert len(burst) >= 4
    for i in range(len(burst) - 1):
        diff = (burst[i + 1]["transaction_date"] - burst[i]["transaction_date"]).total_seconds()
        assert 0 <= diff <= 60
        assert burst[i]["user_id"] == 1


def test_pattern_geographic_impossibility():
    """Test geographic impossibility pattern generation."""
    rng = random.Random(42)
    profiles = create_user_profiles(
        num_users=1,
        countries=["US"],
        country_weights=[1.0],
        currencies=["USD"],
        currency_weights=[1.0],
        categories=["dining"],
        rng=rng,
    )
    prof = profiles[1]
    anchor = datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.UTC)

    pair = inject_geographic_impossibility(prof, anchor, ["US", "JP", "GB"], rng)
    assert len(pair) == 2
    tx1, tx2 = pair
    assert tx1["merchant_country"] == "US"
    assert tx2["merchant_country"] != "US"
    time_diff = (tx2["transaction_date"] - tx1["transaction_date"]).total_seconds() / 60
    assert 10 <= time_diff <= 50
    assert tx2["card_present"] is True


def test_pattern_amount_deviation():
    """Test extreme amount deviation injection."""
    rng = random.Random(42)
    profiles = create_user_profiles(
        num_users=1,
        countries=["US"],
        country_weights=[1.0],
        currencies=["USD"],
        currency_weights=[1.0],
        categories=["luxury"],
        rng=rng,
    )
    prof = profiles[1]
    now = datetime.datetime(2024, 7, 1, 12, 0, 0, tzinfo=datetime.UTC)

    tx = inject_amount_deviation(prof, now, rng)
    assert tx["amount"] >= Decimal("3500.00")
    assert tx["amount"] > Decimal(str(prof.avg_amount * 5))


def test_pattern_new_device_high_amount():
    """Test new device plus high amount pattern."""
    rng = random.Random(42)
    profiles = create_user_profiles(
        num_users=1,
        countries=["US"],
        country_weights=[1.0],
        currencies=["USD"],
        currency_weights=[1.0],
        categories=["electronics"],
        rng=rng,
    )
    prof = profiles[1]
    now = datetime.datetime(2024, 7, 1, 12, 0, 0, tzinfo=datetime.UTC)

    tx = inject_new_device_high_amount(prof, now, rng)
    assert tx["device_id"] not in prof.known_devices
    assert tx["amount"] >= Decimal("1800.00")


def test_pattern_round_number_structuring():
    """Test round-number structuring amounts."""
    rng = random.Random(42)
    struct_amounts = [Decimal("9900.00"), Decimal("4950.00")]
    profiles = create_user_profiles(
        num_users=1,
        countries=["US"],
        country_weights=[1.0],
        currencies=["USD"],
        currency_weights=[1.0],
        categories=["retail"],
        rng=rng,
    )
    prof = profiles[1]
    now = datetime.datetime(2024, 7, 1, 12, 0, 0, tzinfo=datetime.UTC)

    tx = inject_round_number_structuring(prof, now, struct_amounts, rng)
    assert tx["amount"] in struct_amounts


def test_generate_transactions_batching():
    """Test full batch stream generator with exact count and date span."""
    config = GeneratorConfig(
        total_records=250,
        fraud_rate=0.05,
        num_users=20,
        batch_size=100,
        seed=999,
    )

    batches = list(generate_transactions(config))
    total_yielded = sum(len(b) for b in batches)
    assert total_yielded == 250
    assert len(batches) == 3

    for batch in batches:
        for tx in batch:
            assert config.start_date <= tx["transaction_date"] <= config.end_date
            assert tx["amount"] > 0
            assert tx["currency"] in config.primary_currencies
