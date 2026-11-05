from app.services.falsification_report import reviseHypothesis


def test_without_evidence_keeps_hypothesis_unresolved():
    result = reviseHypothesis([])
    assert result.revisedClaim is None
    assert result.status == "insufficient_evidence"


def test_condition_difference_is_linked_without_claiming_refutation():
    result = reviseHypothesis([
        {"evidenceId": "meso", "classification": "support", "reason": "处理组达到预设终点。"},
        {"evidenceId": "thermo", "classification": "conditional", "reason": "另一组未达到同一终点。"},
    ])
    assert result.status == "no_counterexample_found"
    assert result.evidenceIds == ["meso", "thermo"]
    assert "未达到" in result.revisedClaim


def test_pending_review_does_not_imply_insufficient_evidence():
    result = reviseHypothesis([], reviewPending=True)
    assert result.status == "not_reviewed"
    assert result.revisedClaim is None
