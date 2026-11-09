"""Tests for the skip/replace behaviour of data_ingestion.py.
No database server is needed: a temporary SQLite file stands in for
PostgreSQL and a small in-memory class stands in for the MongoDB collection."""
import os
import sys

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_ingestion  # noqa: E402
from data_ingestion import get_ingest_mode, ingest, should_load  # noqa: E402

CSV = (
    "﻿InvoiceNo,StockCode,Description,Quantity,InvoiceDate,UnitPrice,CustomerID,Country\n"
    "536365,85123A,WHITE HANGING HEART T-LIGHT HOLDER,6,01/12/10 08:26,2.55,17850.0,United Kingdom\n"
    "536366,22633,HAND WARMER UNION JACK,6,01/12/10 08:28,1.85,,United Kingdom\n"
    "C536379,D,Discount,-1,01/12/10 09:41,27.5,14527,United Kingdom\n"
)


class FakeCollection:
    def __init__(self):
        self.docs = []

    def insert_many(self, docs):
        self.docs.extend(docs)

    def delete_many(self, _filter):
        self.docs.clear()

    def count_documents(self, _filter):
        return len(self.docs)


@pytest.fixture
def env(tmp_path):
    csv_path = tmp_path / "online_retail.csv"
    csv_path.write_text(CSV, encoding="utf-8")
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    return engine, FakeCollection(), str(csv_path)


def sql_count(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM sales_data")).scalar()


@pytest.mark.parametrize("rows, mode, expected", [
    (0, "", True),
    (5, "", False),
    (0, "replace", True),
    (5, "replace", True),
])
def test_should_load(rows, mode, expected):
    assert should_load(rows, mode) is expected


def test_get_ingest_mode(monkeypatch):
    monkeypatch.delenv("INGEST_MODE", raising=False)
    assert get_ingest_mode() == ""
    monkeypatch.setenv("INGEST_MODE", " Replace ")
    assert get_ingest_mode() == "replace"
    monkeypatch.setenv("INGEST_MODE", "append")
    with pytest.raises(ValueError):
        get_ingest_mode()


def test_first_run_loads_into_both_stores(env):
    engine, collection, path = env
    assert ingest(engine, collection, path) == 3
    assert sql_count(engine) == 3
    assert collection.count_documents({}) == 3


def test_customer_ids_stored_as_whole_number_text(env):
    engine, collection, path = env
    ingest(engine, collection, path)
    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text('SELECT "CustomerID" FROM sales_data ORDER BY "InvoiceNo"'))]
    assert ids == ["17850", None, "14527"]
    assert [d["CustomerID"] for d in collection.docs] == ["17850", None, "14527"]


def test_second_run_skips_when_table_has_rows(env, capsys):
    engine, collection, path = env
    ingest(engine, collection, path)
    capsys.readouterr()

    assert ingest(engine, collection, path) == 0
    assert "skipping ingestion" in capsys.readouterr().out
    assert sql_count(engine) == 3
    assert collection.count_documents({}) == 3


def test_skip_does_not_need_the_dataset_file(env):
    engine, collection, path = env
    ingest(engine, collection, path)
    assert ingest(engine, collection, "does/not/exist.csv") == 0


def test_replace_empties_both_stores_and_reloads(env, capsys):
    engine, collection, path = env
    ingest(engine, collection, path)
    collection.insert_many([{"stale": True}])   # extra doc that replace must remove
    capsys.readouterr()

    assert ingest(engine, collection, path, mode="replace") == 3
    assert "INGEST_MODE=replace" in capsys.readouterr().out
    assert sql_count(engine) == 3
    assert collection.count_documents({}) == 3
    assert not any(d.get("stale") for d in collection.docs)


def test_main_honours_ingest_mode_env(env, monkeypatch):
    engine, collection, path = env
    ingest(engine, collection, path)
    monkeypatch.setattr(data_ingestion, "create_engine", lambda _url: engine)
    monkeypatch.setattr(data_ingestion, "MongoClient",
                        lambda _uri: {"OnlineRetail": {"unstructured_data": collection}})
    monkeypatch.setattr(data_ingestion, "DATASET_PATH", path)

    monkeypatch.delenv("INGEST_MODE", raising=False)
    data_ingestion.main()
    assert sql_count(engine) == 3

    monkeypatch.setenv("INGEST_MODE", "replace")
    data_ingestion.main()
    assert sql_count(engine) == 3 and collection.count_documents({}) == 3
