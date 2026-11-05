from app.services.design_evidence import suggestFromEvidence
from app.services.experiment_design import DesignRequest, planExperiment
from app.services.prose_contrasts import readProseContrasts


def test_question_only_draft_requires_matching_no_treatment_control():
    text = "The yield of the samples increased from 20% in the no-ABC control group to 30 and 35% when 1 and 2 g of ABC, respectively, were added."
    evidence = {"groupTables": {"p": readProseContrasts(text, 4)}}
    req = DesignRequest(question="Does ABC increase yield?")
    proposed, basis = suggestFromEvidence(req, evidence)
    assert basis["page"] == 4
    draft = planExperiment(proposed, sourceType="proposed")
    assert len(draft["groups"]) == 3 and draft["groups"][0].isControl
    assert all(group.sourceType == "proposed" for group in draft["groups"])
    assert draft["totalExperimentalUnits"] is None
    assert suggestFromEvidence(DesignRequest(question="Does XYZ increase yield?"), evidence)[1] is None


def test_verified_figure_caption_supplies_reported_levels_and_baseline():
    caption = ("Fig. 2. Curve of root length versus time for sodium chloride in tray A "
               "at treatment concentrations of 0 (positive control [PC]), 5, 10, and 20 mg/L.")
    evidence = {"papers": {"p": [{"page": 6, "evidenceText": caption}]}}
    req = DesignRequest(question="How does sodium chloride change root length over time?")
    proposed, basis = suggestFromEvidence(req, evidence)
    assert basis["page"] == 6 and basis["excerpt"] == caption
    assert proposed.outcome == "root length"
    assert proposed.factors[0].levels == ["0 mg/L", "5 mg/L", "10 mg/L", "20 mg/L"]
    assert proposed.control == {"sodium chloride": "0 mg/L"}
    assert suggestFromEvidence(req.model_copy(update={"outcome": "leaf count"}), evidence)[1] is None
    evidence["papers"]["p"][0]["evidenceText"] = caption.replace("0 (positive control [PC])", "0")
    assert suggestFromEvidence(req, evidence)[1] is None
