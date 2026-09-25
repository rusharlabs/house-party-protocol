"""A criterion that is green and checks one comfortable case per branch."""
from discount import discount

assert discount(200, False) == 180.0
assert discount(80, True) == 72.0
assert discount(10, False) == 10
