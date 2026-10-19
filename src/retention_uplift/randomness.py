"""Partition-independent pseudo-random draws using domain-separated SHA-256 keys."""

from pyspark.sql import Column
from pyspark.sql import functions as F


def uniform(seed: int, domain: str, *keys: str) -> Column:
    """Open-interval uniform from 52 hash bits; stable for a given seed/domain/row key.

    Inputs are internal IDs (no delimiters or nulls). This is a reproducible simulation
    PRNG, not a cryptographic assignment service or an empirical independence proof.
    """
    digest = F.sha2(
        F.concat_ws("|", F.lit(str(seed)), F.lit(domain), *[F.col(k) for k in keys]), 256
    )
    return (F.conv(F.substring(digest, 1, 13), 16, 10).cast("double") + 0.5) / 2**52


def normal(seed: int, domain: str, *keys: str) -> Column:
    """Box-Muller normal; distinct hash domains for the two uniforms."""
    return F.sqrt(-2 * F.log(uniform(seed, domain + ":u", *keys))) * F.cos(
        2 * 3.141592653589793 * uniform(seed, domain + ":v", *keys)
    )


def clip(value: Column, low: float, high: float) -> Column:
    return F.greatest(F.lit(low), F.least(F.lit(high), value))


def sigmoid(value: Column) -> Column:
    return 1 / (1 + F.exp(-value))
