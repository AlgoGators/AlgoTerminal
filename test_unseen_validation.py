import numpy as np
import pandas as pd
import pytest

import unseen_validation as uv


def test_fold_has_ninety_completed_session_purge():
    index = pd.bdate_range("2020-01-01", periods=500)
    folds = uv.make_folds(index, validation_sessions=50, purge_sessions=90)
    assert folds
    for fold in folds:
        assert fold.train_end_pos + 90 < fold.validation_start_pos
        assert fold.validation_start_pos - fold.train_end_pos - 1 == 90
        assert fold.validation_start_pos <= fold.validation_end_pos


def test_non_eq_weight_fit_ends_before_purge_gap():
    index = pd.bdate_range("2020-01-01", periods=500)
    returns = pd.DataFrame({"a": np.arange(500), "b": np.arange(500)[::-1]}, index=index)
    fold = uv.make_folds(index, validation_sessions=50, purge_sessions=90)[0]
    weights, fit_end = uv.fit_weights(returns, ["a", "b"], "INV", fold)
    assert fit_end == fold.train_end
    assert sum(weights.values()) == pytest.approx(1.0)


def test_manifest_contains_declared_families_without_selection():
    manifest = uv.variant_manifest()
    families = {row["family"] for row in manifest}
    assert {"v4", "v5", "v7", "vNext"} <= families
    assert len(manifest) == len({row["variant_id"] for row in manifest})
    assert all(row["release_rank"] == "not_used" for row in manifest)


def test_apply_purge_never_scores_purge_rows():
    index = pd.bdate_range("2020-01-01", periods=300)
    fold = uv.make_folds(index, validation_sessions=40, purge_sessions=90)[0]
    scored = uv.scored_slice(index, fold)
    assert scored[0] == fold.validation_start
    assert scored[-1] == fold.validation_end
    assert not set(index[fold.train_end_pos + 1 : fold.validation_start_pos]).intersection(scored)
