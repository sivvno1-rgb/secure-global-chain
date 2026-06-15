"""Evidence computation seam (AGENTS_AND_COMPUTE.md §3).

Two schools (JASP heritage): **frequentist** (scipy.stats) and **Bayesian**.
Runs are reproducible — seed pinned, library versions + dataset hash recorded.
Crucially, the code computes *statistics only*; the interpretation
(supported/refuted) is a human disposition, never set here.

In production these run in the locked-down enclave Celery worker (`evidence`
queue, no outbound network). Here :class:`LocalEvidenceComputer` runs them
synchronously so the flow is testable. The Bayesian path uses a conjugate
normal-normal posterior (numpy); the PyMC enclave is the production target. Swap
via the ``get_evidence_computer`` dependency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import scipy
from scipy import stats

from ..models.enums import EvidenceMethod

# Pinned for reproducibility (recorded on each packet summary).
SEED = 1729


@dataclass(frozen=True)
class ResultRow:
    statistic: str
    value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    posterior_ref: str | None = None


@dataclass(frozen=True)
class EvidenceOutcome:
    summary: str
    results: list[ResultRow]
    generated_by: str


class EvidenceComputer(Protocol):
    def run(
        self, method: EvidenceMethod, *, dataset_ref: str | None, params: dict
    ) -> EvidenceOutcome: ...


def _dataset_hash(dataset_ref: str | None, sample: list[float]) -> str:
    payload = json.dumps({"ref": dataset_ref, "sample": sample}, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:16]


class LocalEvidenceComputer:
    """Synchronous evidence runner for dev/tests (statistics only)."""

    def __init__(self) -> None:
        self.generated_by = (
            f"local:numpy-{np.__version__}/scipy-{scipy.__version__}"
        )

    def run(
        self, method: EvidenceMethod, *, dataset_ref: str | None, params: dict
    ) -> EvidenceOutcome:
        sample = [float(x) for x in params.get("sample", [])]
        if len(sample) < 2:
            raise ValueError("params.sample must contain at least two observations")
        if method is EvidenceMethod.frequentist:
            return self._frequentist(dataset_ref, sample, params)
        return self._bayesian(dataset_ref, sample, params)

    def _frequentist(self, dataset_ref, sample, params) -> EvidenceOutcome:
        popmean = float(params.get("popmean", 0.0))
        arr = np.asarray(sample, dtype=float)
        result = stats.ttest_1samp(arr, popmean)
        n = arr.size
        mean = float(arr.mean())
        sem = float(stats.sem(arr))
        # 95% CI on the mean via the t distribution.
        half = float(stats.t.ppf(0.975, df=n - 1) * sem) if sem > 0 else 0.0
        rows = [
            ResultRow(
                statistic="t",
                value=float(result.statistic),
                p_value=float(result.pvalue),
            ),
            ResultRow(
                statistic="mean",
                value=mean,
                ci_low=mean - half,
                ci_high=mean + half,
            ),
        ]
        summary = (
            f"One-sample t-test vs {popmean}: t={result.statistic:.4f}, "
            f"p={result.pvalue:.4g}, n={n}. Reproducibility: seed={SEED}, "
            f"{self.generated_by}, dataset={_dataset_hash(dataset_ref, sample)}."
        )
        return EvidenceOutcome(summary=summary, results=rows, generated_by=self.generated_by)

    def _bayesian(self, dataset_ref, sample, params) -> EvidenceOutcome:
        # Conjugate normal-normal posterior for the mean (known-variance approx).
        rng = np.random.default_rng(SEED)
        arr = np.asarray(sample, dtype=float)
        n = arr.size
        data_mean = float(arr.mean())
        data_var = float(arr.var(ddof=1)) or 1.0
        prior_mean = float(params.get("prior_mean", 0.0))
        prior_var = float(params.get("prior_var", 1e6))  # weak prior
        like_var = data_var / n
        post_var = 1.0 / (1.0 / prior_var + 1.0 / like_var)
        post_mean = post_var * (prior_mean / prior_var + data_mean / like_var)
        post_sd = post_var ** 0.5
        lo, hi = stats.norm.ppf([0.025, 0.975], loc=post_mean, scale=post_sd)
        # Posterior draws would be persisted to object storage in the enclave.
        draws = rng.normal(post_mean, post_sd, size=8)
        posterior_ref = "memory://posterior/" + hashlib.sha256(
            draws.tobytes()
        ).hexdigest()[:16]
        rows = [
            ResultRow(
                statistic="posterior_mean",
                value=post_mean,
                ci_low=float(lo),
                ci_high=float(hi),
                posterior_ref=posterior_ref,
            )
        ]
        summary = (
            f"Bayesian posterior mean={post_mean:.4f}, 95% CrI=[{lo:.4f}, {hi:.4f}], "
            f"n={n}. Reproducibility: seed={SEED}, {self.generated_by}, "
            f"dataset={_dataset_hash(dataset_ref, sample)}."
        )
        return EvidenceOutcome(summary=summary, results=rows, generated_by=self.generated_by)


def get_evidence_computer() -> EvidenceComputer:
    return LocalEvidenceComputer()
