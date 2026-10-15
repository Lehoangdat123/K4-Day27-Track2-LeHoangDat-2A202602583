from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def make_verdict(alert, pillar, reason, confidence=0.9):
    return Verdict(
        alert=alert,
        confidence=confidence,
        reason=reason,
        pillar=pillar,
    )


def check_data_batch(payload, ctx):
    batch_id = payload.get("batch_id")
    if not batch_id:
        return make_verdict(False, "data_quality", "Missing batch_id")

    result = ctx.tools.batch_profile(batch_id)

    if not isinstance(result, dict) or "error" in result:
        return make_verdict(False, "data_quality", "Unable to profile batch")

    baseline = ctx.baseline
    reasons = []

    row_count = result.get("row_count")
    if row_count is not None:
        if row_count < baseline["row_count_min"]:
            reasons.append("row count below baseline")
        elif row_count > baseline["row_count_max"]:
            reasons.append("row count above baseline")

    null_rate = result.get("null_rate", {})
    if isinstance(null_rate, dict):
        customer_null_rate = null_rate.get("customer_id")
        if (
            customer_null_rate is not None
            and customer_null_rate > baseline["null_rate_max"]
        ):
            reasons.append("customer_id null rate too high")

    mean_amount = result.get("mean_amount")
    if mean_amount is not None:
        if (
            mean_amount < baseline["mean_amount_min"]
            or mean_amount > baseline["mean_amount_max"]
        ):
            reasons.append("mean amount outside baseline")

    staleness = result.get("staleness_min")
    if (
        staleness is not None
        and staleness > baseline["staleness_min_max"]
    ):
        reasons.append("batch is too stale")

    return make_verdict(
        bool(reasons),
        "data_quality",
        "; ".join(reasons) if reasons else "Batch within baseline",
        0.95 if reasons else 0.8,
    )


def check_contract_checkpoint(payload, ctx):
    contract_id = payload.get("contract_id")
    batch_id = payload.get("checkpoint_batch_id")

    if not contract_id or not batch_id:
        return make_verdict(
            False, "contract", "Missing contract or checkpoint identifier"
        )

    result = ctx.tools.contract_diff(contract_id, batch_id)

    if not isinstance(result, dict) or "error" in result:
        return make_verdict(False, "contract", "Unable to check contract")

    reasons = []
    violations = result.get("violations", [])

    if violations:
        reasons.append("contract violations detected")

    delay = result.get("freshness_delay_min")
    if (
        delay is not None
        and delay > ctx.baseline["freshness_delay_max_min"]
    ):
        reasons.append("freshness delay exceeds baseline")

    return make_verdict(
        bool(reasons),
        "contract",
        "; ".join(reasons) if reasons else "Contract within baseline",
        0.95 if reasons else 0.8,
    )


def check_lineage_run(payload, ctx):
    run_id = payload.get("run_id")
    if not run_id:
        return make_verdict(False, "lineage", "Missing run_id")

    result = ctx.tools.lineage_graph_slice(run_id)

    if not isinstance(result, dict) or "error" in result:
        return make_verdict(False, "lineage", "Unable to inspect lineage")

    reasons = []

    duration = result.get("duration_ms")
    if (
        duration is not None
        and duration > ctx.baseline["lineage_duration_ms_max"]
    ):
        reasons.append("lineage run is unusually slow")

    downstream = result.get("actual_downstream_count")
    if downstream is not None and downstream == 0:
        reasons.append("lineage has no downstream consumers")

    upstream = result.get("actual_upstream")
    if isinstance(upstream, list):
        expected = payload.get("expected_upstream", [])
        if expected:
            missing = set(expected) - set(upstream)
            if missing:
                reasons.append("expected upstream dependencies missing")

    return make_verdict(
        bool(reasons),
        "lineage",
        "; ".join(reasons) if reasons else "Lineage within baseline",
        0.95 if reasons else 0.8,
    )


def check_feature_materialization(payload, ctx):
    feature_view = payload.get("feature_view")
    ref = (
    payload.get("batch_id")
    or payload.get("checkpoint_batch_id")
    or payload.get("run_id")
    or payload.get("chunk_batch_id")
    or payload.get("ref")
    )

    if not feature_view or ref is None:
        return make_verdict(
            False, "feature_drift", "Missing feature view or reference"
        )

    result = ctx.tools.feature_drift(feature_view, ref)

    if not isinstance(result, dict) or "error" in result:
        return make_verdict(
            False, "feature_drift", "Unable to inspect feature drift"
        )

    shift = result.get("mean_shift_sigma")
    threshold = ctx.baseline["feature_mean_shift_sigma_max"]

    import sys
    print(
        f"[feature_drift] ref={ref!r}, "
        f"shift={shift!r}, baseline={threshold!r}",
        file=sys.stderr,
    )

    if shift is not None and shift > threshold:
        return make_verdict(
            True,
            "feature_drift",
            f"Feature mean shift is elevated: {shift:.3f} sigma",
            0.95,
        )

    return make_verdict(
    False,
    "feature_drift",
    f"Feature drift within expected range: "
    f"shift={shift!r}, threshold={threshold!r}",
    0.8,
)


def check_embedding_batch(payload, ctx):
    corpus = payload.get("corpus")
    ref = payload.get("chunk_batch_id") or payload.get("ref")

    if not corpus or ref is None:
        return make_verdict(
            False, "embedding_drift", "Missing corpus or reference"
        )

    result = ctx.tools.embedding_drift(corpus, ref)

    if not isinstance(result, dict) or "error" in result:
        return make_verdict(
            False, "embedding_drift", "Unable to inspect embedding drift"
        )

    reasons = []

    shift = result.get("centroid_shift")
    if shift is not None and shift > 0.0395:
        reasons.append("embedding centroid shift is elevated")

    age = result.get("avg_doc_age_days")
    if age is not None and age > 44:
        reasons.append("corpus documents are unusually old")

    return make_verdict(
        bool(reasons),
        "embedding_drift",
        "; ".join(reasons) if reasons else "Embedding drift within expected range",
        0.95 if reasons else 0.8,
    )
