"""Portable file checks and complete-output comparisons."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check_hashes(root, bindings):
    root = Path(root).resolve()
    for relative, digest in bindings.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Evidence path escapes root: {relative}")
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"Changed evidence: {relative}")

def compare_metrics(actual, expected):
    """Check all metric fields, rather than just the headline ratios."""
    if len(actual) != len(expected):
        raise ValueError('Different number of policy results')
    for a, b in zip(actual, expected):
        if set(a) != set(b):
            raise ValueError('Metric schema changed')
        for key in a:
            if isinstance(a[key], (float, int)) and not isinstance(a[key], bool):
                same = np.isclose(a[key], b[key], rtol=1e-9, atol=1e-9)
            else:
                same = a[key] == b[key]
            if not same:
                raise ValueError(f"Reproduction mismatch: {a.get('id')} / {key}")


def compare_ledger_prefix(original, recreated):
    """All-zero short columns can infer int where the full history infers float.

    Permit only integer/float storage changes, never string/bool conversions.
    Preserve the same numerical tolerances, index and complete column checks.
    """
    normalized = recreated.copy()
    differences = []
    if list(original.columns) != list(recreated.columns):
        raise ValueError('Ledger column schema changed')
    numeric = lambda dtype: pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_float_dtype(dtype)
    for column in original:
        left, right = original[column].dtype, recreated[column].dtype
        if left != right:
            if not (numeric(left) and numeric(right)):
                raise ValueError(f'Non-numeric ledger storage type changed: {column}')
            # Compare in a common floating representation, without truncating decimals.
            original = original.copy()
            original[column] = original[column].astype(float)
            normalized[column] = recreated[column].astype(float)
            differences.append({'column':column,'reference_dtype':str(left),'replay_dtype':str(right)})
    pd.testing.assert_frame_equal(original, normalized, check_exact=False, rtol=1e-10, atol=1e-8)
    return differences
