"""Evidence compute seam: frequentist (scipy) and Bayesian (conjugate normal)."""

from __future__ import annotations

import pytest
from scipy import stats

from sgc.models.enums import EvidenceMethod
from sgc.research.compute import LocalEvidenceComputer


def test_frequentist_matches_scipy():
    sample = [5.1, 4.9, 5.2, 5.0, 4.8, 5.3]
    computer = LocalEvidenceComputer()
    outcome = computer.run(
        EvidenceMethod.frequentist, dataset_ref="ds://x",
        params={"sample": sample, "popmean": 5.0},
    )
    expected = stats.ttest_1samp(sample, 5.0)
    t_row = next(r for r in outcome.results if r.statistic == "t")
    assert t_row.value == pytest.approx(float(expected.statistic))
    assert t_row.p_value == pytest.approx(float(expected.pvalue))
    mean_row = next(r for r in outcome.results if r.statistic == "mean")
    assert mean_row.ci_low < mean_row.value < mean_row.ci_high
    # Reproducibility metadata is recorded; no verdict in the summary.
    assert "seed=" in outcome.summary
    assert "supported" not in outcome.summary.lower()
    assert "refuted" not in outcome.summary.lower()


def test_bayesian_posterior_is_deterministic_with_credible_interval():
    sample = [5.1, 4.9, 5.2, 5.0, 4.8, 5.3]
    computer = LocalEvidenceComputer()
    a = computer.run(EvidenceMethod.bayesian, dataset_ref=None, params={"sample": sample})
    b = computer.run(EvidenceMethod.bayesian, dataset_ref=None, params={"sample": sample})
    row = a.results[0]
    assert row.statistic == "posterior_mean"
    assert row.ci_low < row.value < row.ci_high
    assert row.posterior_ref.startswith("memory://posterior/")
    # Seeded → deterministic posterior ref.
    assert a.results[0].posterior_ref == b.results[0].posterior_ref


def test_requires_minimum_sample():
    with pytest.raises(ValueError):
        LocalEvidenceComputer().run(
            EvidenceMethod.frequentist, dataset_ref=None, params={"sample": [1.0]}
        )
