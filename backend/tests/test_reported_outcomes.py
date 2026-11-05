from app.services.reported_outcomes import extractReportedOutcomes, reviewReportedOutcomes


def test_original_threshold_extracted_and_secondary_threshold_skipped():
    base = dict(source_id="a", source="a.pdf", collection="literature_x", page=5)
    records = extractReportedOutcomes([{**base, "evidenceText":
        "Smith reported 50% inhibition at 2 mM. The oleic acid concentration of 4.4 mM resulting in 50% inhibition in our experiments."}])
    assert [(r["page"], r["metric"], r["value"], r["unit"]) for r in records] == [(5, "oleic acid", "4.4", "mM")]


def test_no_significant_effect_limits_claim_without_refuting_it():
    evidence = [dict(source_id="a", source="a.pdf", collection="literature_x", page=3,
        evidenceText="the tested ammonia levels had no significant effect (P > 0.05) on methane production for group A (Fig. 1).")]
    records = extractReportedOutcomes(evidence)
    result = reviewReportedOutcomes("Does ammonia always reduce methane production?", records)
    assert [item["classification"] for item in result] == ["conditional"]
    assert reviewReportedOutcomes("Does ammonia always reduce biomass?", records) == []

