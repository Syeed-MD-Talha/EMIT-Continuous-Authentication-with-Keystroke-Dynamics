import pytest

from features import WINDOW_FEATURE_NAMES, events_to_features, window_features


def test_events_to_features_values():
    events = [
        {"d": 100.0, "u": 150.0},
        {"d": 200.0, "u": 260.0},
        {"d": 300.0, "u": 340.0},
        {"d": 400.0, "u": 470.0},
    ]
    features = events_to_features(events)
    assert len(features) == 4 * 4 - 4
    expected = [0.05, 0.06, 0.04, 0.07, 0.1, 0.1, 0.1, 0.05, 0.04, 0.06, 0.2, 0.2]
    assert features == pytest.approx(expected)


def test_events_to_features_sorts_by_keydown():
    events = [
        {"d": 300.0, "u": 340.0},
        {"d": 100.0, "u": 150.0},
        {"d": 400.0, "u": 470.0},
        {"d": 200.0, "u": 260.0},
    ]
    sorted_events = [
        {"d": 100.0, "u": 150.0},
        {"d": 200.0, "u": 260.0},
        {"d": 300.0, "u": 340.0},
        {"d": 400.0, "u": 470.0},
    ]
    assert events_to_features(events) == pytest.approx(events_to_features(sorted_events))


def test_window_features_shape():
    events = [{"d": i * 150.0, "u": i * 150.0 + 80.0} for i in range(100)]
    feats = window_features(events)
    assert len(feats) == len(WINDOW_FEATURE_NAMES) == 30
    assert all(isinstance(value, float) for value in feats)


def test_window_features_are_position_independent():
    """Same rhythm, different absolute times -> identical features."""
    base = [{"d": i * 150.0, "u": i * 150.0 + 80.0} for i in range(20)]
    shifted = [{"d": e["d"] + 5000.0, "u": e["u"] + 5000.0} for e in base]
    assert window_features(base) == pytest.approx(window_features(shifted))


def test_window_features_rejects_short_input():
    with pytest.raises(ValueError):
        window_features([{"d": 0.0, "u": 50.0}, {"d": 100.0, "u": 150.0}])
