from __future__ import annotations

from soundbook.ingest.metrics import boundary_f1, parse_key


def test_parse_key():
    assert parse_key("OEBPS/Text/ch1.xhtml|7") == ("OEBPS/Text/ch1.xhtml", 7)


def test_perfect_match():
    gold = ["a.xhtml|0", "a.xhtml|5", "b.xhtml|0"]
    assert boundary_f1(gold, gold) == 1.0


def test_tolerance_window():
    gold = ["a.xhtml|0", "a.xhtml|5"]
    assert boundary_f1(["a.xhtml|0", "a.xhtml|6"], gold, tolerance_blocks=1) == 1.0
    assert boundary_f1(["a.xhtml|0", "a.xhtml|6"], gold, tolerance_blocks=0) < 1.0


def test_href_must_match():
    gold = ["a.xhtml|0"]
    assert boundary_f1(["b.xhtml|0"], gold, tolerance_blocks=99) == 0.0


def test_empty_sets():
    assert boundary_f1([], []) == 1.0
    assert boundary_f1(["a|0"], []) == 0.0
    assert boundary_f1([], ["a|0"]) == 0.0


def test_precision_and_recall_are_balanced():
    gold = ["a.xhtml|0", "a.xhtml|10", "a.xhtml|20", "a.xhtml|30"]
    pred = ["a.xhtml|0", "a.xhtml|10"]
    # 2 matches / 2 predicted = P 1.0, 2/4 = R 0.5 → F1 0.6667
    assert abs(boundary_f1(pred, gold) - (2 / 3)) < 1e-9


def test_one_gold_boundary_is_not_matched_twice():
    gold = ["a.xhtml|5"]
    pred = ["a.xhtml|5", "a.xhtml|5"]
    assert abs(boundary_f1(pred, gold) - (2 / 3)) < 1e-9
