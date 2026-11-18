from urllib.parse import parse_qs, urlparse

from backend.learning_resources import get_learning_resources


def test_learning_resources_include_free_and_paid_options_per_skill():
    resources = get_learning_resources(["Machine Learning", "SQL"])

    assert [item["skill"] for item in resources] == ["Machine Learning", "SQL"]
    assert [course["price_type"] for course in resources[0]["courses"]] == ["Free", "Paid"]

    free_link = urlparse(resources[0]["courses"][0]["url"])
    paid_link = urlparse(resources[0]["courses"][1]["url"])
    assert free_link.netloc == "www.youtube.com"
    assert parse_qs(free_link.query)["search_query"] == ["Machine Learning free full course"]
    assert paid_link.netloc == "www.udemy.com"
    assert parse_qs(paid_link.query) == {
        "q": ["Machine Learning"],
        "price": ["price-paid"]
    }


def test_learning_resources_skip_blank_and_duplicate_skill_names():
    resources = get_learning_resources([" Python ", "python", "", None])

    assert len(resources) == 1
    assert resources[0]["skill"] == "Python"
