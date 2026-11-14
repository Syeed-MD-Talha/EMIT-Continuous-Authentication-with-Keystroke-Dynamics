from desktop import autostart


def test_command_contains_launcher_when_not_frozen():
    value = autostart.command()
    assert str(autostart.LAUNCHER) in value
    assert value.startswith('"')


def test_command_uses_executable_when_frozen(monkeypatch):
    monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", r"C:\Apps\EMITDesktop.exe")
    assert autostart.command() == '"C:\\Apps\\EMITDesktop.exe"'


def test_is_enabled_returns_bool():
    assert isinstance(autostart.is_enabled(), bool)
