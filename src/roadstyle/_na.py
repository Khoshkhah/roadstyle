"""One test for a missing value, used wherever a cell may be empty."""
import pandas as pd


def missing(v):
    """None, NaN, or pandas' NA (a column from DuckDB with no values comes as a nullable dtype): ``v != v`` raised on NA (2026-10-09)."""
    return v is None or v is pd.NA or (isinstance(v, float) and v != v)
