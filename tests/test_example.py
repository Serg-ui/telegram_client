import pytest

x = 0

def test_none():
    pass

def test_zero():
    assert x == 0

def test_not_zero():
    assert x != 0

def test_exception():
    raise Exception('text')