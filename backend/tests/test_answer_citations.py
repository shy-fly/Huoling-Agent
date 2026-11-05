import pytest


def test_repair_out_of_range_citations():
    from app.services.answer_citations import validateAnswer
    calls = []

    def repair(messages):
        calls.append(messages)
        return "Correct source [1]."

    assert validateAnswer("Original bibliography [25].", 2, [], repair) == "Correct source [1]."
    assert len(calls) == 1
    assert validateAnswer("Supported [2].", 2, [], repair) == "Supported [2]."
    assert len(calls) == 1


def test_unrepaired_citations_are_not_accepted():
    from app.services.answer_citations import validateAnswer
    with pytest.raises(ValueError, match="citation"):
        validateAnswer("Unsupported [25].", 1, [], lambda _: "Still unsupported [9].")
