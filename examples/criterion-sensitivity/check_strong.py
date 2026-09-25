"""A criterion that pins both boundaries and both branches."""
from discount import discount

assert discount(100, False) == 90.0
assert discount(99.99, False) == 99.99
assert discount(50, True) == 45.0
assert discount(49.99, True) == 49.99
assert discount(60, False) == 60
