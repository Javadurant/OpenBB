from engine.pipeline import run_pipeline

def test_run_pipeline_contract():
    result = run_pipeline(symbol="AAPL", timeframe="1d")

    assert isinstance(result, dict)

    for key in ["data", "evidence", "prediction", "signal"]:
        assert key in result
