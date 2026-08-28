#!/usr/bin/env python3
"""Convenience script to run the synthetic data generator and ingestion CLI."""

import sys

from src.generator.cli import main

if __name__ == "__main__":
    sys.exit(main())
