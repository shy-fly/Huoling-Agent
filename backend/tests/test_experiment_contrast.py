from app.services.experiment_contrast import verifyContrast


def test_verified_contrast_keeps_each_arm_on_its_source_page():
    evidence = [
        {"id": 1, "page": 2, "evidenceText": "Group A and group B were paired."},
        {"id": 2, "page": 4, "evidenceText": "Group A produced methane at 40 mL."},
        {"id": 3, "page": 5, "evidenceText": "group B produced methane at 60 mL."},
    ]
    proposal = {
        "designChunkId": 1, "designQuote": evidence[0]["evidenceText"],
        "treatment": {"chunkId": 2, "quote": evidence[1]["evidenceText"],
                      "group": "Group A", "outcome": "methane", "rawValue": "40", "rawUnit": "mL"},
        "control": {"chunkId": 3, "quote": evidence[2]["evidenceText"],
                    "group": "group B", "outcome": "methane", "rawValue": "60", "rawUnit": "mL"},
    }
    result = verifyContrast(proposal, evidence)
    assert (result["designPage"], result["treatment"]["page"], result["control"]["page"]) == (2, 4, 5)
    assert result["compatible"]
    proposal["treatment"]["rawValue"] = "60"
    assert verifyContrast(proposal, evidence) is None

