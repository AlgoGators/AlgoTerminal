from lean_runner import probe_capabilities


def test_probe_reports_missing_runtime_and_data(monkeypatch, tmp_path):
    monkeypatch.setattr("lean_runner.which", lambda name: None)

    result = probe_capabilities(tmp_path / "lean_fixture")

    assert result.status == "unavailable"
    assert result.missing == (
        "dotnet runtime",
        "QuantConnect LEAN CLI",
        "LEAN fixture data",
    )
    assert result.render() == (
        "status=unavailable; missing=dotnet runtime, QuantConnect LEAN CLI, "
        "LEAN fixture data"
    )
