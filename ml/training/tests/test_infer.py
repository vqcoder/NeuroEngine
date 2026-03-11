from __future__ import annotations

import pandas as pd

from ml_pipeline.infer import predictions_to_records


def test_predictions_to_records_emits_reward_proxy_and_attention_alias() -> None:
    prediction_frame = pd.DataFrame(
        [
            {
                "second": 0,
                "reward_proxy": 61.5,
                "blink_inhibition": 0.72,
                "dial": 47.0,
            }
        ]
    )

    rows = predictions_to_records(prediction_frame)

    assert len(rows) == 1
    assert rows[0]["reward_proxy"] == 61.5
    assert rows[0]["attention"] == 61.5
    assert rows[0]["blink_inhibition"] == 0.72


def test_predictions_to_records_backfills_reward_proxy_from_attention() -> None:
    prediction_frame = pd.DataFrame(
        [
            {
                "second": 1,
                "attention": 55.0,
                "blink_inhibition": 0.6,
                "dial": 52.0,
            }
        ]
    )

    rows = predictions_to_records(prediction_frame)

    assert rows[0]["attention"] == 55.0
    assert rows[0]["reward_proxy"] == 55.0
