from app.services.prose_contrasts import readProseContrasts


def test_pairs_explicit_percentages_and_doses_in_order():
    text = "The yield of the samples increased from 20% in the untreated control group to 30 and 35% when 1 and 2 g of material, respectively, were added."
    report, = readProseContrasts(text, 3)
    assert [(item["treatment"]["group"], item["treatment"]["verifiedValue"]) for item in report["contrasts"]] == [
        ("1 g material", "30%"), ("2 g material", "35%"),
    ]
    assert report["contrasts"][0]["control"]["verifiedValue"] == "20%"
    assert not readProseContrasts(text.replace("1 and 2 g", "1, 2, and 3 g"), 3)
