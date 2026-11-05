from app.services.experiment_design import DesignRequest, planExperiment


def test_factorial_reproducible_control_and_capacity():
    request = DesignRequest(question="Compare factors", outcome="yield", replicates=3, maxUnits=12,
                            factors=[{"name":"A","levels":["0","1"]},{"name":"B","levels":["x","y"]}],
                            control={"A":"0","B":"x"})
    draft = planExperiment(request)
    assert draft["designType"] == "full_factorial"
    assert draft["totalExperimentalUnits"] == 12
    assert sum(group.isControl for group in draft["groups"]) == 1
    assert draft["randomizationOrder"] == planExperiment(request)["randomizationOrder"]
    assert planExperiment(request.model_copy(update={"maxUnits":11}))["groups"] == []


def test_missing_inputs_remain_pending():
    draft = planExperiment(DesignRequest(question="What changes?"))
    assert not draft["groups"]
    assert draft["hypotheses"]["null"] is None
    assert draft["totalExperimentalUnits"] is None
