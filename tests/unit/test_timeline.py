import pytest

from videoflow.domain.timeline import find_overlaps, is_packed


def test_no_spans_means_no_overlaps() -> None:
    assert find_overlaps([]) == []


def test_disjoint_and_touching_spans_do_not_overlap() -> None:
    assert find_overlaps([(0, 10), (10, 20)]) == []


def test_overlap_is_reported() -> None:
    assert find_overlaps([(0, 10), (5, 15)]) == [(0, 1)]


def test_unsorted_input_still_finds_the_pair_in_index_order() -> None:
    assert find_overlaps([(20, 30), (0, 10), (5, 8)]) == [(1, 2)]


def test_inverted_spans_are_rejected() -> None:
    with pytest.raises(ValueError):
        find_overlaps([(10, 1)])
    with pytest.raises(ValueError):
        find_overlaps([(0, 5), (5, 1)])
    with pytest.raises(ValueError):
        find_overlaps([(0, 5), (2, 1)])


def test_packed_from_origin() -> None:
    assert is_packed([])
    assert is_packed([(0, 10), (10, 20)])
    assert is_packed([(100, 110), (110, 120)], origin=100)


def test_gap_and_wrong_origin_are_not_packed() -> None:
    assert not is_packed([(5, 10)])
    assert not is_packed([(0, 10), (11, 20)])


def test_overlap_and_inverted_span_are_not_packed() -> None:
    assert not is_packed([(0, 10), (5, 20)])
    assert not is_packed([(0, 10), (20, 10)])
