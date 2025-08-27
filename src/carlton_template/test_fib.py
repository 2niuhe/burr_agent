import unittest

from .fib import fib


class TestAddThree(unittest.TestCase):
    def test_add_three(self):
        self.assertEqual(fib(3), 2)
