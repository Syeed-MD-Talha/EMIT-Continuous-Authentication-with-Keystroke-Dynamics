from desktop.windowizer import Windowizer


def make_event(t, hold=80.0):
    return {"d": t, "u": t + hold}


def test_emits_sliding_windows():
    w = Windowizer(window=4, stride=2, idle_gap=2.0)
    out = []
    for i in range(6):
        out.extend(w.feed(make_event(i * 200.0)))
    assert len(out) == 2
    assert len(out[0]) == 4
    assert out[0][0]["d"] == 0.0
    assert out[1][0]["d"] == 400.0


def test_idle_gap_resets_buffer():
    w = Windowizer(window=3, stride=1, idle_gap=1.0)
    w.feed(make_event(0.0))
    w.feed(make_event(200.0))
    assert w.pending == 2
    w.feed(make_event(5000.0))
    assert w.pending == 1


def test_rejects_invalid_configuration():
    import pytest

    with pytest.raises(ValueError):
        Windowizer(window=2)
    with pytest.raises(ValueError):
        Windowizer(window=10, stride=11)
