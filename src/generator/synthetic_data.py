"""High-performance synthetic transaction generation pipeline using NumPy, Faker, and pattern injection."""

import datetime
import random
from collections.abc import Generator
from typing import Any

import numpy as np

from src.generator.config import GeneratorConfig
from src.generator.patterns import (
    FraudPatternType,
    create_user_profiles,
    generate_baseline_transaction,
    inject_amount_deviation,
    inject_geographic_impossibility,
    inject_new_device_high_amount,
    inject_round_number_structuring,
    inject_velocity_fraud,
)


def generate_transactions(
    config: GeneratorConfig,
) -> Generator[list[dict[str, Any]], None, None]:
    """Generate batches of synthetic transactions across the 24-month partition span with injected fraud patterns.

    Yields lists of transaction dictionaries sized up to config.batch_size.
    """
    config.validate()
    rng = random.Random(config.seed)
    np_rng = np.random.default_rng(config.seed)

    # 1. Create baseline user profiles
    user_profiles = create_user_profiles(
        num_users=config.num_users,
        countries=config.primary_countries,
        country_weights=config.country_weights,
        currencies=config.primary_currencies,
        currency_weights=config.currency_weights,
        categories=config.merchant_categories,
        rng=rng,
    )
    user_ids = list(user_profiles.keys())

    # 2. Time boundaries (24 months)
    start_ts = config.start_date.timestamp()
    end_ts = config.end_date.timestamp()
    total_duration = end_ts - start_ts

    records_generated = 0
    current_batch: list[dict[str, Any]] = []

    fraud_pattern_choices = [
        FraudPatternType.VELOCITY,
        FraudPatternType.GEOGRAPHIC_IMPOSSIBILITY,
        FraudPatternType.AMOUNT_DEVIATION,
        FraudPatternType.NEW_DEVICE_HIGH_AMOUNT,
        FraudPatternType.ROUND_NUMBER_STRUCTURING,
    ]

    while records_generated < config.total_records:
        remaining = config.total_records - records_generated
        batch_target = min(config.batch_size, remaining)

        while (
            len(current_batch) < batch_target
            and records_generated + len(current_batch) < config.total_records
        ):
            # Pick a user
            uid = rng.choice(user_ids)
            profile = user_profiles[uid]

            # Generate realistic timestamp uniformly across 24-month range
            rand_fraction = float(np_rng.uniform(0.0, 1.0))
            tx_timestamp = datetime.datetime.fromtimestamp(
                start_ts + (rand_fraction * total_duration),
                tz=datetime.UTC,
            )

            # Decide whether to inject a fraud pattern
            if rng.random() < config.fraud_rate:
                pattern = rng.choice(fraud_pattern_choices)

                if pattern == FraudPatternType.VELOCITY:
                    injected = inject_velocity_fraud(profile, tx_timestamp, rng)
                    current_batch.extend(injected)

                elif pattern == FraudPatternType.GEOGRAPHIC_IMPOSSIBILITY:
                    injected = inject_geographic_impossibility(
                        profile, tx_timestamp, config.primary_countries, rng
                    )
                    current_batch.extend(injected)

                elif pattern == FraudPatternType.AMOUNT_DEVIATION:
                    injected = [inject_amount_deviation(profile, tx_timestamp, rng)]
                    current_batch.extend(injected)

                elif pattern == FraudPatternType.NEW_DEVICE_HIGH_AMOUNT:
                    injected = [inject_new_device_high_amount(profile, tx_timestamp, rng)]
                    current_batch.extend(injected)

                elif pattern == FraudPatternType.ROUND_NUMBER_STRUCTURING:
                    injected = [
                        inject_round_number_structuring(
                            profile, tx_timestamp, config.structuring_amounts, rng
                        )
                    ]
                    current_batch.extend(injected)
            else:
                base_tx = generate_baseline_transaction(
                    profile,
                    tx_timestamp,
                    config.merchant_categories,
                    config.category_weights,
                    rng,
                )
                current_batch.append(base_tx)

        # Trim batch if it slightly exceeded the total count limit due to pattern expansion
        if records_generated + len(current_batch) > config.total_records:
            excess = (records_generated + len(current_batch)) - config.total_records
            current_batch = current_batch[:-excess]

        records_generated += len(current_batch)
        yield current_batch
        current_batch = []
