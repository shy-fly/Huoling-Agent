from app.services.research_compare_extraction import validateExperiments


def test_keeps_groups_and_metric_units_separate():
    evidence = [{"id": 1, "page": 4, "evidenceText": "M1 TAN 4 g/L; T1 FAN 200 mg/L."}]
    raw = [
        dict(group="M1", dimension="TAN", rawValue="4", rawUnit="g/L",
             chunkId=1, quote="M1 TAN 4 g/L", sourceKind="primary"),
        dict(group="T1", dimension="FAN", rawValue="200", rawUnit="mg/L",
             chunkId=1, quote="T1 FAN 200 mg/L", sourceKind="primary"),
    ]
    observations, rejected = validateExperiments("paper", evidence, raw)
    assert rejected == 0
    assert [(o.group, o.dimension, o.rawUnit, o.page) for o in observations] == [
        ("M1", "TAN", "g/L", 4), ("T1", "FAN", "mg/L", 4),
    ]


def test_rejects_cross_group_value_and_unverified_quote():
    evidence = [{"id": 1, "page": 4, "evidenceText": "M1 TAN 40 g/L; T1 TAN 7 g/L."}]
    base = dict(group="M1", dimension="TAN", rawValue="4", rawUnit="g/L",
                chunkId=1, quote="M1 TAN 40 g/L", sourceKind="primary")
    proposals = [base, {**base, "rawValue": "7", "quote": "T1 TAN 7 g/L"},
                 {**base, "rawValue": "9", "quote": "M1 TAN 9 g/L"}]
    assert validateExperiments("paper", evidence, proposals) == ([], 3)


def test_secondary_claim_is_retained_as_context():
    quote = "Study A reported a 50% decrease."
    evidence = [{"id": 1, "page": 3, "evidenceText": quote}]
    proposal = dict(group="Study A", dimension="decrease", rawValue="50", rawUnit="%",
                    chunkId=1, quote=quote, sourceKind="secondary")
    observations, rejected = validateExperiments("review", evidence, [proposal])
    assert rejected == 0
    assert observations[0].sourceKind == "secondary"

