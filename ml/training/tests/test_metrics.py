from ml_pipeline.metrics import correlation, mae, peak_recall


def test_mae_basic():
    assert abs(mae([1, 2, 3], [1, 2, 4]) - (1 / 3)) < 1e-9


def test_correlation_perfect_positive():
    assert abs(correlation([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-9


def test_peak_recall_with_tolerance():
    true_values = [0, 1, 8, 1, 0, 9, 0]
    pred_values = [0, 1, 0, 7, 0, 8, 0]
    score = peak_recall(true_values, pred_values, top_k=2, tolerance=1)
    assert score >= 0.5
