"""EIP-2780 repricing analysis core.

This module is self-contained (depends only on numpy, pandas, scipy). It has two
halves:

(A) Analysis functions ported verbatim from the sibling ``evm-gas-repricings`` repo
    (``extract_param_values``, ``NNLSResults``, ``fit_NNLS``,
    ``prepare_non_simple_model_data``).

(B) A faithful reproduction of the ``ether-transfers-tx-base-value-gas`` notebook:
    it reads the fetched parquet/meta inputs from ``data/raw/`` and writes the
    consolidated ``data/results.json`` artifact.

Run with ``python scripts/analysis.py`` from the repo root.
"""

import json
import math
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Union

import numpy as np
import pandas as pd
from scipy.optimize import nnls

# ---------------------------------------------------------------------------
# PART A — Ported analysis functions (verbatim from evm-gas-repricings/src)
# ---------------------------------------------------------------------------


# Ported from evm-gas-repricings/src/data.py (extract_param_values).
def extract_param_values(params_str: str, param_name: str):
    if not isinstance(params_str, str):
        return np.nan
    regex_str = param_name + r"_(\d+)"
    values = re.findall(regex_str, params_str)
    if len(values) > 0:
        return values[0]
    else:
        return np.nan


# Ported verbatim from evm-gas-repricings/src/nnls_results.py (NNLSResults).
class NNLSResults:
    """
    Results wrapper for NNLS regression that mimics statsmodels interface.

    This class provides a statsmodels-compatible interface for NNLS (Non-Negative
    Least Squares) regression results, enabling drop-in replacement of OLS methods
    in existing code. Statistical inference is performed via bootstrap.

    Attributes:
        params (pd.Series): Coefficient estimates (including "const" for intercept)
        pvalues (pd.Series): Bootstrap-based p-values for each coefficient
        rsquared (float): R-squared value
        rsquared_adj (float): Adjusted R-squared value
        nobs (int): Number of observations
        fittedvalues (np.ndarray): Predicted values for training data
        resid (np.ndarray): Residuals (observed - fitted)
    """

    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        y_name: str,
        coefficients: np.ndarray,
        bootstrap_coefs: np.ndarray,
        feature_names: List[str],
        residual_norm: float,
    ):
        """
        Initialize NNLS results wrapper.

        Args:
            X: Feature matrix with constant column (n_obs × n_features)
            y: Target values (n_obs,)
            coefficients: NNLS coefficient estimates (n_features,)
            bootstrap_coefs: Bootstrap coefficient samples (n_bootstrap × n_features)
            feature_names: Names of features including "const"
            residual_norm: Residual norm from NNLS optimization
        """
        self._X = X
        self._y = y
        self._coefficients = coefficients
        self._bootstrap_coefs = bootstrap_coefs
        self._feature_names = feature_names
        self._residual_norm = residual_norm
        self._dep_var = y_name

        # Compute fitted values and residuals
        self._fittedvalues = X @ coefficients
        self._resid = y - self._fittedvalues

        # Compute R-squared
        ss_res = np.sum(self._resid**2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        self._rsquared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Compute adjusted R-squared
        n = len(y)
        k = len(coefficients) - 1  # Exclude intercept
        if n > k + 1:
            self._rsquared_adj = 1 - (1 - self._rsquared) * (n - 1) / (n - k - 1)
        else:
            self._rsquared_adj = self._rsquared

        # Compute additional metrics
        self._rmse = np.sqrt(np.mean(self._resid**2))
        self._mae = np.mean(np.abs(self._resid))

        # Lazy-initialized attributes
        self._influence = None
        self._params_series = None
        self._pvalues_series = None
        self._std_errors = None

    @property
    def params(self) -> pd.Series:
        """Coefficient values as Series with feature names as index."""
        if self._params_series is None:
            self._params_series = pd.Series(
                self._coefficients, index=self._feature_names
            )
        return self._params_series

    @property
    def pvalues(self) -> pd.Series:
        """P-values from bootstrap test"""
        if self._pvalues_series is None:
            p_vals = self._calculate_bootstrap_pvalues()
            self._pvalues_series = pd.Series(p_vals, index=self._feature_names)
        return self._pvalues_series

    @property
    def rsquared(self) -> float:
        """R-squared value."""
        return self._rsquared

    @property
    def rsquared_adj(self) -> float:
        """Adjusted R-squared value."""
        return self._rsquared_adj

    @property
    def nobs(self) -> int:
        """Number of observations."""
        return len(self._y)

    @property
    def fittedvalues(self) -> np.ndarray:
        """Fitted values (predictions on training data)."""
        return self._fittedvalues

    @property
    def resid(self) -> np.ndarray:
        """Residuals (observed - fitted)."""
        return self._resid

    def _calculate_bootstrap_pvalues(self) -> np.ndarray:
        """
        Calculate p-values from bootstrap distribution using percentile method.

        Returns:
            Array of p-values for each coefficient
        """
        eps = 1e-12  # Small constant to avoid division by zero
        # Calculate standard errors from bootstrap (for summary table)
        std_errors = np.std(self._bootstrap_coefs, axis=0)
        self._std_errors = std_errors
        p_values = []
        for i, coef in enumerate(self._coefficients):
            boot_dist = self._bootstrap_coefs[:, i]
            if coef == 0:
                # Coefficient constrained to zero by NNLS
                p_val = 1.0
            else:
                p_val = np.mean(boot_dist <= eps)
            p_values.append(p_val)
        return np.array(p_values)

    def conf_int(self, alpha: float = 0.05) -> pd.DataFrame:
        """
        One-sided confidence interval using bootstrap percentile method.

        Args:
            alpha: Significance level (default 0.05 for 95% CI)

        Returns:
            DataFrame with columns [0, 1] for lower and upper bounds
        """
        lower_percentile = 100 * (alpha / 2)
        upper_percentile = 100 * (1 - alpha / 2)
        conf_intervals_low = np.percentile(
            self._bootstrap_coefs, lower_percentile, axis=0
        )
        conf_intervals_high = np.percentile(
            self._bootstrap_coefs, upper_percentile, axis=0
        )
        ci_df = pd.DataFrame(
            {0: conf_intervals_low, 1: conf_intervals_high}, index=self._feature_names
        )
        return ci_df

    def summary(self) -> str:
        """
        Generate formatted summary table (statsmodels-style).

        Returns:
            Multi-line string with regression summary
        """
        width = 78
        lines = []

        # Header
        lines.append("=" * width)
        lines.append(f"{'NNLS Regression Results':^{width}}")
        lines.append("=" * width)
        lines.append(
            f"Dep. Variable:          {self._dep_var}"
            f"{'R-squared:':>{width - 54}}{self.rsquared:>15.3f}"
        )
        lines.append(
            f"Model:                  NNLS"
            f"{'Adj. R-squared:':>{width - 43}}{self.rsquared_adj:>15.3f}"
        )
        lines.append(
            f"No. Observations:       {self.nobs:<7}"
            f"{'RMSE:':>{width - 46}}{self._rmse:>15.2f}"
        )
        lines.append(
            f"Df Residuals:           {self.nobs - len(self.params):<7}"
            f"{'MAE:':>{width - 46}}{self._mae:>15.2f}"
        )
        lines.append(f"Df Model:               {len(self.params) - 1:<7}")
        lines.append("=" * width)

        # Coefficient table
        lines.append(
            f"{'':>14}{'coef':>12}{'std err':>12}{'P-value':>12}{'[0.025':>12}{'0.975]':>12}"
        )
        lines.append("-" * width)

        ci = self.conf_int()
        for name in self._feature_names:
            coef = self.params[name]
            pval = self.pvalues[name]
            ci_low = ci.loc[name, 0]
            ci_high = ci.loc[name, 1]
            se = self._std_errors[self._feature_names.index(name)]

            lines.append(
                f"{name:>14}{coef:>12.4f}{se:>12.4f}{pval:>12.3f}"
                f"{ci_low:>12.4f}{ci_high:>12.4f}"
            )

        lines.append("=" * width)
        lines.append(
            f"Notes: Non-negative least squares with bootstrap inference "
            f"({len(self._bootstrap_coefs)} iterations)"
        )
        lines.append("=" * width)

        return "\n".join(lines)

    def predict(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """
        Make predictions on new data.

        Args:
            X: Feature matrix (may or may not include constant column)

        Returns:
            Array of predictions
        """
        # Convert DataFrame to array if needed
        if isinstance(X, pd.DataFrame):
            X = X.values

        # Check if X has constant column
        if X.shape[1] == len(self._feature_names) - 1:
            # No constant column - add it
            X_with_const = np.column_stack([np.ones(len(X)), X])
        else:
            X_with_const = X

        return X_with_const @ self._coefficients


# Ported verbatim from evm-gas-repricings/src/nnls.py (fit_NNLS). The original
# sys.path.append / "from nnls_results import NNLSResults" lines are removed since
# NNLSResults is defined inline above.
def fit_NNLS(
    feature_df: pd.DataFrame,
    features: List[str],
    n_bootstrap: int = 1000,
    random_seed: int = 42,
) -> NNLSResults:
    """
    Fit NNLS regression with bootstrap inference.

    Performs Non-Negative Least Squares regression with statistical inference
    via bootstrap resampling. All coefficients are constrained to be non-negative,
    which is appropriate for runtime estimation where negative time contributions
    are physically meaningless.

    Args:
        feature_df: DataFrame with features and "run_duration_ms" target column
        features: List of feature column names (excluding constant term)
        n_bootstrap: Number of bootstrap iterations for inference (default 1000)
        random_seed: Random seed for reproducibility (default 42)

    Returns:
        NNLSResults object with statsmodels-compatible interface

    Raises:
        ValueError: If feature_df is empty or missing required columns
        KeyError: If specified features are not in feature_df

    Example:
        >>> df = pd.DataFrame({
        ...     'opcount': [1, 2, 3, 4, 5],
        ...     'run_duration_ms': [2.1, 5.0, 7.9, 11.1, 13.9]
        ... })
        >>> result = fit_NNLS(df, ['opcount'], n_bootstrap=100)
        >>> print(result.params)
        const      0.12
        opcount    2.80
        dtype: float64
    """
    # Validate inputs
    if feature_df.empty:
        raise ValueError("feature_df cannot be empty")
    if "run_duration_ms" not in feature_df.columns:
        raise ValueError("feature_df must contain 'run_duration_ms' column")
    for feature in features:
        if feature not in feature_df.columns:
            raise KeyError(f"Feature '{feature}' not found in feature_df")
    # Extract and prepare data
    X = feature_df[features].astype(float).values
    y = feature_df["run_duration_ms"].astype(float).values
    # Add constant column (intercept) at position 0
    X_with_const = np.column_stack([np.ones(len(X)), X])
    feature_names = ["const"] + features
    # Fit primary NNLS model
    coefficients, residual_norm = nnls(X_with_const, y)
    # Bootstrap for statistical inference
    np.random.seed(random_seed)
    bootstrap_coefs = np.zeros((n_bootstrap, X_with_const.shape[1]))
    n_successful = 0
    for i in range(n_bootstrap):
        try:
            # Resample with replacement
            indices = np.random.choice(len(y), size=len(y), replace=True)
            X_boot = X_with_const[indices]
            y_boot = y[indices]
            # Fit NNLS on bootstrap sample
            coef_boot, _ = nnls(X_boot, y_boot)
            bootstrap_coefs[i] = coef_boot
            n_successful += 1
        except Exception:
            # If bootstrap sample fails, use zeros (will be handled in results)
            bootstrap_coefs[i] = np.zeros(X_with_const.shape[1])
    # Warn if too many bootstrap failures
    success_rate = n_successful / n_bootstrap
    if success_rate < 0.95:
        import warnings

        warnings.warn(
            f"Only {success_rate:.1%} of bootstrap samples succeeded. "
            f"Statistical inference may be unreliable.",
            UserWarning,
        )
    # Create and return results object
    return NNLSResults(
        X=X_with_const,
        y=y,
        y_name="run_duration_ms",
        coefficients=coefficients,
        bootstrap_coefs=bootstrap_coefs,
        feature_names=feature_names,
        residual_norm=residual_norm,
    )


# Ported verbatim from evm-gas-repricings/src/runtime_estimation.py
# (prepare_non_simple_model_data). Calls extract_param_values defined above.
def prepare_non_simple_model_data(
    op_df: pd.DataFrame,
    params: List[str],
) -> tuple[pd.DataFrame, List[str]]:
    """Prepare data for non-simple operation modeling.

    Extracts parameter values, determines which features have data,
    and multiplies extra features by opcount.

    Returns (model_df, features) where features = ["opcount"] + active params.
    """
    for param in params:
        op_df[param] = op_df["test_params"].apply(
            lambda x: extract_param_values(x, param)
        )
    na_counts = op_df[params].isna().sum()
    non_all_na = na_counts[na_counts != len(op_df)].index.to_list()
    extra_features = [p for p in non_all_na if op_df[p].dropna().nunique() > 1]
    features = ["opcount"] + extra_features
    model_op_df = op_df.copy()
    model_op_df[extra_features] = model_op_df[extra_features].astype(float)
    model_op_df[extra_features] = model_op_df[extra_features].mul(
        model_op_df["opcount"], axis=0
    )
    return model_op_df, features


# ---------------------------------------------------------------------------
# PART B — Notebook reproduction (parquet in -> data/results.json out)
# ---------------------------------------------------------------------------

ANCHOR_RATE = 100 * 1e6  # gas / s
TX_BASE = 21_000  # current per-tx base gas
VALUE_GAS_CURRENT = 9_000  # current extra gas for non-zero value transfer
TEST_NAME = "test_ether_transfers_onchain_receivers"
EXCLUDED_CLIENTS = set()  # clients dropped from the analysis

# Resolve paths relative to this script so `python scripts/analysis.py` works
# from the repo root.
REPO_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_DIR / "data" / "raw"
BENCH_PARQUET = RAW_DIR / "bench_data.parquet"
TRACE_PARQUET = RAW_DIR / "trace.parquet"
META_JSON = RAW_DIR / "meta.json"
RESULTS_JSON = REPO_DIR / "data" / "results.json"
RUNS_DIR = REPO_DIR / "data" / "runs"  # committed history, one file per run


def _sanitize(obj):
    """Recursively replace non-finite floats (NaN/inf) with None so the result
    serializes to valid JSON (``json`` writes NaN as the invalid token ``NaN``)."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    # numpy scalar floats
    if isinstance(obj, np.floating):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _records(df: pd.DataFrame) -> list:
    """DataFrame -> list of plain dicts with NaN/inf turned into None."""
    return _sanitize(df.to_dict(orient="records"))


def load_meta() -> dict:
    """Read data/raw/meta.json defensively; return {} if absent/unparseable."""
    if not META_JSON.exists():
        return {}
    try:
        with open(META_JSON, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _extract_suite(meta_raw: dict):
    """Reduce meta.json's suite info to a comma-separated hash string."""
    suites = (
        meta_raw.get("suites") or meta_raw.get("suite") or meta_raw.get("suite_hash")
    )
    if isinstance(suites, list):
        hashes = [
            s.get("suite_hash") if isinstance(s, dict) else str(s) for s in suites
        ]
        hashes = [h for h in hashes if h]
        return ", ".join(hashes) if hashes else None
    return suites


def _make_run_id(window, suite, generated_at: str) -> str:
    """Build a stable, sortable run id from the data window + suite.

    Keyed on ``window["end"]`` so re-analyzing the same data produces the same id
    (and overwrites the same archive entry) rather than a duplicate. The end
    timestamp (e.g. ``2026-05-31T09:01:16Z``) is stripped of ``:``/``-`` so it is
    filesystem-safe and still sorts chronologically; the first suite hash token is
    appended to disambiguate same-window runs of different suites. Falls back to
    the ``generated_at`` stamp when the window is missing.
    """
    end = (window or {}).get("end") if isinstance(window, dict) else None
    stamp = end or generated_at
    stamp = re.sub(r"[:\-]", "", str(stamp))
    suite_token = ""
    if suite:
        suite_token = "_" + re.split(r"[,\s]+", str(suite).strip())[0]
    return f"{stamp}{suite_token}"


def _extract_case_id(test_params: str):
    """Extract the case_id, stripping the trailing block-size token.

    benchmarkoor-fetch's test_params look like
    ``...-case_id_diff_to_contract-benchmark_100M`` — the ``-benchmark_<N>M``
    suffix encodes the block gas limit, which is the regression variable
    (opcount scales with it), so it must NOT be part of the group key. The
    notebook's CSV had no such suffix; the ``re.sub`` is a no-op there, so this
    is faithful to the notebook on its own data and correct on the parquet.
    """
    if not isinstance(test_params, str):
        return np.nan
    m = re.search(r"case_id_(.+)$", test_params)
    if m is None:
        return np.nan
    return re.sub(r"-benchmark_\d+M$", "", m.group(1))


def build_results_df(df: pd.DataFrame) -> pd.DataFrame:
    """Fit NNLS per (client_name, case_id) and collect the per-fit records."""
    results_records = []
    for (client_name, case_id), group_df in df.groupby(["client_name", "case_id"]):
        fit_df = group_df.drop(columns=["transfer_amount"])
        try:
            model_df, features = prepare_non_simple_model_data(
                fit_df, ["transfer_amount"]
            )
            fit_df = model_df[features + ["run_duration_ms"]].dropna()
            if fit_df.empty:
                raise ValueError("No valid data remaining after dropping NaN values")
            result = fit_NNLS(fit_df, features)
        except Exception as e:
            print(f"Skipping ({client_name}, {case_id}): {e}")
            continue

        has_transfer = "transfer_amount" in result.params
        record = {
            "client_name": client_name,
            "case_id": case_id,
            "nobs": result.nobs,
            "rsquared": result.rsquared,
            "rsquared_adj": result.rsquared_adj,
            "intercept": result.params["const"],
            "intercept_pvalue": result.pvalues["const"],
            "slope": result.params["opcount"],
            "slope_pvalue": result.pvalues["opcount"],
            "slope_conf_int_low": result.conf_int().loc["opcount", 0],
            "slope_conf_int_high": result.conf_int().loc["opcount", 1],
            "transfer_amount": result.params.get("transfer_amount", np.nan),
            "transfer_amount_pvalue": result.pvalues.get("transfer_amount", np.nan),
            "transfer_amount_conf_int_low": (
                result.conf_int().loc["transfer_amount", 0] if has_transfer else np.nan
            ),
            "transfer_amount_conf_int_high": (
                result.conf_int().loc["transfer_amount", 1] if has_transfer else np.nan
            ),
        }
        results_records.append(record)

    results_df = (
        pd.DataFrame(results_records)
        .sort_values(["client_name", "case_id"])
        .reset_index(drop=True)
    )
    return results_df


def build_new_gas_df(results_df: pd.DataFrame) -> pd.DataFrame:
    """Convert the fitted coefficients into long-form new-gas estimates."""
    rename_map = {
        "slope": "TX_BASE",
        "transfer_amount": "VALUE_GAS",
    }
    current_gas_map = {
        "TX_BASE": TX_BASE,
        "VALUE_GAS": VALUE_GAS_CURRENT,
        # A value-bearing transfer pays a flat 21000 today (no separate value
        # charge ever existed for transfers), so its reference is TX_BASE.
        "VALUE_TRANSFER": TX_BASE,
    }

    long_frames = []
    for source_col, param_name in rename_map.items():
        sub = results_df[
            [
                "client_name",
                "case_id",
                source_col,
                f"{source_col}_conf_int_low",
                f"{source_col}_conf_int_high",
                f"{source_col}_pvalue",
                "rsquared",
            ]
        ].copy()
        sub = sub.rename(
            columns={
                source_col: "runtime_ms",
                f"{source_col}_conf_int_low": "conf_int_low",
                f"{source_col}_conf_int_high": "conf_int_high",
                f"{source_col}_pvalue": "pvalue",
            }
        )
        sub["param"] = param_name
        long_frames.append(sub)

    # Derived param VALUE_TRANSFER = TX_BASE + VALUE_GAS, the end-to-end cost of a
    # transfer that moves value. transfer_amount is a 0/1 indicator, so a value
    # transfer's modeled runtime is slope + transfer_amount within the SAME fit —
    # the two coefficients simply add. CI bounds are summed (a conservative
    # over-estimate of the paired-bootstrap CI, since it ignores the negative
    # covariance between the coefficients); pvalue is the max of the two, so the
    # total is flagged insignificant if either coefficient is; rsquared is shared.
    vt = results_df[["client_name", "case_id", "rsquared"]].copy()
    vt["runtime_ms"] = results_df["slope"] + results_df["transfer_amount"]
    vt["conf_int_low"] = (
        results_df["slope_conf_int_low"] + results_df["transfer_amount_conf_int_low"]
    )
    vt["conf_int_high"] = (
        results_df["slope_conf_int_high"] + results_df["transfer_amount_conf_int_high"]
    )
    vt["pvalue"] = results_df[["slope_pvalue", "transfer_amount_pvalue"]].max(axis=1)
    vt["param"] = "VALUE_TRANSFER"
    long_frames.append(vt)

    new_gas_df = pd.concat(long_frames, ignore_index=True)

    new_gas_df["new_gas"] = (ANCHOR_RATE * new_gas_df["runtime_ms"]) / 1e3
    new_gas_df["new_gas_rounded"] = np.ceil(new_gas_df["new_gas"])
    new_gas_df["new_gas_conf_int_low"] = np.ceil(
        (ANCHOR_RATE * new_gas_df["conf_int_low"]) / 1e3
    )
    new_gas_df["new_gas_conf_int_high"] = np.ceil(
        (ANCHOR_RATE * new_gas_df["conf_int_high"]) / 1e3
    )
    new_gas_df["current_gas"] = new_gas_df["param"].map(current_gas_map)
    new_gas_df["change"] = (
        new_gas_df["new_gas_rounded"] / new_gas_df["current_gas"] - 1
    ).round(2)

    new_gas_df = (
        new_gas_df[
            [
                "client_name",
                "case_id",
                "param",
                "runtime_ms",
                "conf_int_low",
                "conf_int_high",
                "pvalue",
                "rsquared",
                "new_gas",
                "new_gas_rounded",
                "new_gas_conf_int_low",
                "new_gas_conf_int_high",
                "current_gas",
                "change",
            ]
        ]
        .sort_values(["param", "client_name", "case_id"])
        .reset_index(drop=True)
    )
    return new_gas_df


def build_worst_cases(new_gas_df: pd.DataFrame):
    """Worst-case (max new_gas_rounded) per (param, case_id) and overall per param."""
    idx_by_case = new_gas_df.groupby(["param", "case_id"])["new_gas_rounded"].idxmax()
    worst_case_by_case = new_gas_df.loc[
        idx_by_case,
        [
            "param",
            "case_id",
            "client_name",
            "new_gas_rounded",
            "new_gas_conf_int_low",
            "new_gas_conf_int_high",
            "rsquared",
            "pvalue",
        ],
    ].reset_index(drop=True)

    idx_overall = new_gas_df.groupby("param")["new_gas_rounded"].idxmax()
    worst_case_overall = new_gas_df.loc[
        idx_overall,
        [
            "param",
            "client_name",
            "case_id",
            "new_gas_rounded",
            "new_gas_conf_int_low",
            "new_gas_conf_int_high",
            "rsquared",
            "pvalue",
            "current_gas",
            "change",
        ],
    ].reset_index(drop=True)

    return worst_case_by_case, worst_case_overall


def build_summary(new_gas_df: pd.DataFrame, worst_case_overall: pd.DataFrame) -> dict:
    """Computed (not pre-rendered prose) summary block."""

    def param_summary(param_name: str, current: int) -> dict:
        rows = worst_case_overall[worst_case_overall["param"] == param_name]
        if rows.empty:
            return None
        row = rows.iloc[0]
        new_gas = int(row["new_gas_rounded"])
        change_pct = (new_gas / current - 1) * 100
        return {
            "new_gas": new_gas,
            "client_name": row["client_name"],
            "case_id": row["case_id"],
            "rsquared": float(row["rsquared"]),
            "pvalue": float(row["pvalue"]),
            "current_gas": int(current),
            "change_pct": change_pct,
            "direction": "higher" if change_pct > 0 else "lower",
        }

    # Replicate the notebook's poor_in_worst logic: poor-fit (R² <= 0.5) rows from
    # new_gas_df whose (param, client, case) triple is one of the worst-case-overall
    # drivers.
    poor_fit_rows = new_gas_df[new_gas_df["rsquared"] <= 0.5]
    worst_pairs = set(
        zip(
            worst_case_overall["param"],
            worst_case_overall["client_name"],
            worst_case_overall["case_id"],
        )
    )
    poor_in_worst = poor_fit_rows[
        poor_fit_rows.apply(
            lambda r: (r["param"], r["client_name"], r["case_id"]) in worst_pairs,
            axis=1,
        )
    ]
    caveats = [
        {
            "param": r["param"],
            "client_name": r["client_name"],
            "case_id": r["case_id"],
            "rsquared": float(r["rsquared"]),
        }
        for _, r in poor_in_worst.iterrows()
    ]

    # Same idea for statistical significance: worst-case drivers whose coefficient
    # p-value > 0.05 (the converted gas is not significantly different from zero).
    insig_rows = new_gas_df[new_gas_df["pvalue"] > 0.05]
    insig_in_worst = insig_rows[
        insig_rows.apply(
            lambda r: (r["param"], r["client_name"], r["case_id"]) in worst_pairs,
            axis=1,
        )
    ]
    pvalue_caveats = [
        {
            "param": r["param"],
            "client_name": r["client_name"],
            "case_id": r["case_id"],
            "pvalue": float(r["pvalue"]),
        }
        for _, r in insig_in_worst.iterrows()
    ]

    return {
        "tx_base": param_summary("TX_BASE", TX_BASE),
        "value_gas": param_summary("VALUE_GAS", VALUE_GAS_CURRENT),
        # End-to-end cost of a value transfer (TX_BASE + VALUE_GAS) vs the flat
        # 21000 it pays today.
        "value_transfer": param_summary("VALUE_TRANSFER", TX_BASE),
        "caveats": caveats,
        "pvalue_caveats": pvalue_caveats,
    }


def run_analysis() -> dict:
    """Execute the full notebook reproduction and return the results dict."""
    if not BENCH_PARQUET.exists():
        print(
            f"ERROR: {BENCH_PARQUET} not found.\n"
            "Run `make fetch` first to download the benchmark data."
        )
        raise SystemExit(1)

    # 1. Load & filter ------------------------------------------------------
    bench_df = pd.read_parquet(BENCH_PARQUET)
    # benchmarkoor-fetch emits `test_runtime_ms`; the ported NNLS code needs
    # `run_duration_ms`. Rename right after loading.
    bench_df = bench_df.rename(columns={"test_runtime_ms": "run_duration_ms"})

    df = bench_df[bench_df["test_name"] == TEST_NAME].copy()
    if EXCLUDED_CLIENTS:
        df = df[~df["client_name"].isin(EXCLUDED_CLIENTS)].copy()
    df = df.dropna(axis=1, how="all")

    trace_df = pd.read_parquet(TRACE_PARQUET, columns=["test_title", "JUMP"])

    # 2. Derive transfer_amount and case_id --------------------------------
    df["transfer_amount"] = (
        df["test_params"]
        .apply(lambda s: extract_param_values(s, "transfer_amount"))
        .astype(int)
    )
    df["case_id"] = df["test_params"].apply(_extract_case_id)

    # 3. opcount "opcode trick" — ignore benchmarkoor's own opcount column and
    #    recompute. Drop bench opcount BEFORE the merge to avoid suffixes.
    if "opcount" in df.columns:
        df = df.drop(columns=["opcount"])
    df = df.merge(trace_df, on="test_title", how="left")
    floor_count = (df["block_limit_million"] * 1e6) // TX_BASE
    # Contract cases emit one JUMP/tx -> opcount=JUMP; EOA cases have NaN JUMP ->
    # opcount=floor(gas_limit/21000).
    df["opcount"] = df["JUMP"].where(df["JUMP"].notna(), floor_count).astype(float)
    df = df.drop(columns=["JUMP"])

    # 4. Fit per (client_name, case_id) ------------------------------------
    results_df = build_results_df(df)

    # 5. Convert coefficients to new gas -----------------------------------
    new_gas_df = build_new_gas_df(results_df)

    # 6. Worst-case selection ----------------------------------------------
    worst_case_by_case, worst_case_overall = build_worst_cases(new_gas_df)

    # 7. Summary block (computed values) -----------------------------------
    summary = build_summary(new_gas_df, worst_case_overall)

    # Meta -----------------------------------------------------------------
    meta_raw = load_meta()
    clients = sorted(df["client_name"].dropna().unique().tolist())
    cases = sorted(df["case_id"].dropna().unique().tolist())
    window = meta_raw.get("data_window")
    suite = _extract_suite(meta_raw)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {
        "anchor_rate": ANCHOR_RATE,
        "test_name": TEST_NAME,
        "window": window,
        "generated_from": "meta.json",
        "generated_at": generated_at,
        "run_id": _make_run_id(window, suite, generated_at),
        "clients": clients,
        "cases": cases,
        "benchmarkoor_fetch_version": meta_raw.get(
            "package_version", meta_raw.get("benchmarkoor_fetch_version")
        ),
        "suite": suite,
        "row_counts": meta_raw.get("row_counts"),
    }

    return {
        "meta": _sanitize(meta),
        "results": _records(results_df),
        "new_gas": _records(new_gas_df),
        "worst_case_overall": _records(worst_case_overall),
        "worst_case_by_case": _records(worst_case_by_case),
        "summary": _sanitize(summary),
    }


def main() -> None:
    warnings.filterwarnings("ignore")
    pd.options.mode.chained_assignment = None

    results = run_analysis()

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {RESULTS_JSON}")

    # Archive this run into the committed history (one file per run_id). Keyed on
    # the data window + suite, so re-analyzing the same data overwrites in place
    # rather than accumulating duplicates. results.json stays the "latest" pointer.
    run_id = results["meta"].get("run_id")
    if run_id:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_path = RUNS_DIR / f"{run_id}.json"
        with open(run_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Archived {run_path}")


if __name__ == "__main__":
    main()
