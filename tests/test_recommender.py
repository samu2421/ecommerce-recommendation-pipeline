"""Unit tests for the recommendation engine. No database is required:
the engine is fitted directly from a small hand-made DataFrame."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newapp import MAX_RECOMMENDATIONS, ModelNotTrainedError, RecommendationEngine  # noqa: E402


def make_sales():
    rows = [
        # customer, stock code, description, quantity
        ("17850", "A", "Lantern", 6),
        ("17850", "B", "Heart holder", 4),
        ("13047", "A", "Lantern", 5),
        ("13047", "B", "Heart holder", 3),
        ("13047", "C", "Alarm clock", 10),
        ("12583", "A", "Lantern", 2),
        ("12583", "D", "Tea set", 8),
        ("12583", "D", "Tea set", -3),                     # partial return -> net 5
        ("12583", "Z", "Giant order", 1000),
        ("12583", "Z", "Giant order", -1000),              # fully cancelled -> net 0
        ("16000", "X", "Returned item", 3),
        ("16000", "X", "Returned item", -3),               # customer's only purchase, cancelled
        (None, "E", "Anonymous purchase", 500),            # no customer
    ]
    # Twelve extra products bought by one customer, so n can exceed 10
    rows += [("15100", f"P{i:02d}", f"Product {i}", 1) for i in range(12)]
    rows += [("15100", "A", "Lantern", 1)]
    return pd.DataFrame(rows, columns=["CustomerID", "StockCode", "Description", "Quantity"])


@pytest.fixture
def engine():
    return RecommendationEngine().fit(make_sales())


def codes(recs):
    return [r["stock_code"] for r in recs]


def test_untrained_engine_raises():
    with pytest.raises(ModelNotTrainedError):
        RecommendationEngine().get_recommendations("17850")


# --- Netting of cancellations -------------------------------------------------

def test_matrix_uses_net_quantity_per_customer_and_product(engine):
    m = engine.user_item_matrix
    assert m.loc["12583", "D"] == 5            # 8 bought, 3 returned
    assert m.loc["17850", "A"] == 6


def test_fully_cancelled_products_and_customers_drop_out(engine):
    m = engine.user_item_matrix
    assert "Z" not in m.columns                # net 0
    assert "X" not in m.columns
    assert "16000" not in m.index              # only purchase was cancelled
    assert (m.values >= 0).all()


def test_anonymous_rows_not_in_matrix(engine):
    assert "E" not in engine.user_item_matrix.columns
    assert None not in engine.user_item_matrix.index


def test_popular_fallback_uses_net_quantity_across_all_rows(engine):
    recs = engine.get_recommendations("99999", 10)
    # Anonymous sales count towards popularity; cancelled products do not appear
    assert codes(recs)[:5] == ["E", "A", "C", "B", "D"]
    assert [r["score"] for r in recs[:5]] == [500.0, 14.0, 10.0, 7.0, 5.0]
    assert "Z" not in codes(recs) and "X" not in codes(recs)
    assert recs[1]["description"] == "Lantern"


def test_unknown_customer_gets_popular_products(engine):
    assert codes(engine.get_recommendations("99999", 3)) == ["E", "A", "C"]
    # A customer whose purchases were all cancelled is "unknown" to the matrix
    assert engine.get_recommendations("16000", 3) == engine.get_recommendations("99999", 3)


# --- Personalised recommendations ---------------------------------------------

def test_personalised_recommendations_for_known_customer(engine):
    recs = engine.get_recommendations("17850", 3)
    assert 1 <= len(recs) <= 3
    # 13047 is the most similar customer and bought C
    assert codes(recs)[0] == "C"
    assert all({"stock_code", "description", "score"} <= r.keys() for r in recs)
    assert recs == sorted(recs, key=lambda r: r["score"], reverse=True)


def test_already_bought_products_are_excluded(engine):
    m = engine.user_item_matrix
    for customer in m.index:
        owned = set(m.columns[m.loc[customer] > 0])
        recs = engine.get_recommendations(customer, MAX_RECOMMENDATIONS)
        assert owned.isdisjoint(codes(recs)), customer
    assert {"A", "B"}.isdisjoint(codes(engine.get_recommendations("17850", 10)))


def test_partially_returned_product_still_counts_as_bought(engine):
    # 12583 kept 5 of D, so D must not be recommended back to them
    assert "D" not in codes(engine.get_recommendations("12583", 10))


# --- n and customer ID handling -----------------------------------------------

@pytest.mark.parametrize("requested, expected_max", [(50, MAX_RECOMMENDATIONS), (0, 1), (-3, 1)])
def test_n_is_limited_to_1_to_10(engine, requested, expected_max):
    assert MAX_RECOMMENDATIONS == 10
    for customer in ("17850", "99999"):
        recs = engine.get_recommendations(customer, requested)
        assert 1 <= len(recs) <= expected_max


def test_n_capped_at_10_when_more_candidates_exist(engine):
    # 12583 resembles 15100, who bought 13 products
    assert len(engine.get_recommendations("12583", 50)) == 10
    assert len(engine.get_recommendations("99999", 50)) == 10


def test_customer_id_formats_are_equivalent(engine):
    assert engine.get_recommendations("17850.0", 5) == engine.get_recommendations("17850", 5)


def test_float_customer_ids_in_training_data():
    sales = make_sales()
    sales["CustomerID"] = sales["CustomerID"].map(lambda c: float(c) if c else None)
    engine = RecommendationEngine().fit(sales)
    assert "17850" in engine.user_item_matrix.index
    assert engine.get_recommendations("17850", 3) == RecommendationEngine().fit(
        make_sales()).get_recommendations("17850", 3)
