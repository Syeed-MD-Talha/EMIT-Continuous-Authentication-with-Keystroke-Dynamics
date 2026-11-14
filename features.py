
import numpy as np
import pandas as pd


def build_features(df, kind="tri"):
    """CMU dataframe -> feature table.
    kind: 'hold' | 'digraph' | 'tri' (hold + digraph + trigraph)
    """
    H = [c for c in df.columns if c.startswith("H.")]
    DD = [c for c in df.columns if c.startswith("DD.")]
    UD = [c for c in df.columns if c.startswith("UD.")]
    if kind == "hold":
        return df[H].copy()
    X = df[H + DD + UD].copy()
    if kind == "tri":
        for i in range(len(DD) - 1):
            # trigraph = time from key i going down to key i+2 going down
            X[f"TRI{i}"] = df[DD[i]] + df[DD[i + 1]]
    return X


def events_to_features(events):
    """Live keystrokes -> one feature row (seconds).
    events: list of {"k": key code, "d": keydown ms, "u": keyup ms}
    Order: H (n) + DD (n-1) + UD (n-1) + TRI (n-2)
    """
    ev = sorted(events, key=lambda e: e["d"])
    d = [e["d"] / 1000.0 for e in ev]
    u = [e["u"] / 1000.0 for e in ev]
    n = len(ev)
    H = [u[i] - d[i] for i in range(n)]
    DD = [d[i + 1] - d[i] for i in range(n - 1)]
    UD = [d[i + 1] - u[i] for i in range(n - 1)]
    TRI = [DD[i] + DD[i + 1] for i in range(n - 2)]
    return H + DD + UD + TRI


WINDOW_FEATURE_NAMES = [
    "H_mean", "H_std", "H_median", "H_p10", "H_p90", "H_cv", "H_skew", "H_mad",
    "DD_mean", "DD_std", "DD_median", "DD_p10", "DD_p90", "DD_cv", "DD_skew", "DD_mad",
    "UD_mean", "UD_std", "UD_median", "UD_p10", "UD_p90", "UD_cv", "UD_skew", "UD_mad",
    "overlap_ratio", "keys_per_second", "pause_ratio", "burst_count", "duration",
    "speed_std",
]


def _stats(values):
    """Eight summary statistics: mean, std, median, p10, p90, cv, skew, mad."""
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std())
    median = float(np.median(arr))
    return [
        mean,
        std,
        median,
        float(np.percentile(arr, 10)),
        float(np.percentile(arr, 90)),
        std / mean if abs(mean) > 1e-9 else 0.0,
        (mean - median) / std if std > 1e-9 else 0.0,
        float(np.mean(np.abs(arr - median))),
    ]


def window_features(events):
    """Position-independent features for free typing (any text, any length).

    Unlike events_to_features, feature i does not mean "key i" - it is an
    aggregate over the window, so the same model works for any typed text.
    """
    ev = sorted(events, key=lambda e: e["d"])
    if len(ev) < 3:
        raise ValueError("window_features needs at least 3 keystrokes")

    down = np.array([e["d"] for e in ev], dtype=float) / 1000.0
    up = np.array([e["u"] for e in ev], dtype=float) / 1000.0
    hold = up - down
    dd = np.diff(down)
    ud = down[1:] - up[:-1]

    features = _stats(hold) + _stats(dd) + _stats(ud)
    duration = float(down[-1] - down[0])
    features.extend(
        [
            float(np.mean(ud < 0)),                                  # rollover typing
            (len(ev) - 1) / duration if duration > 1e-9 else 0.0,    # keys per second
            float(np.mean(dd > 0.5)),                                # long-pause ratio
            float(np.sum(dd > 0.3)),                                 # burst count
            duration,
            float(np.std(1.0 / np.clip(dd, 1e-3, None))),            # speed variability
        ]
    )
    return features
