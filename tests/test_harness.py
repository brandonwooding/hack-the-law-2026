from tests.conftest import FakeDriver


def test_fake_driver_returns_canned_rows_by_substring():
    driver = FakeDriver({"queryNodes": [{"id": "x"}]})
    with driver.session() as s:
        rows = s.run("CALL db.index.fulltext.queryNodes('provision_text', $q)", q="abc")
    assert [r.data() for r in rows] == [{"id": "x"}]
    assert driver.calls[0][1] == {"q": "abc"}
