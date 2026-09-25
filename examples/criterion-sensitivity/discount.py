"""A price rule with two boundaries: the code under test in this example."""


def discount(total: float, member: bool) -> float:
    """10% off from 100.00 up, and members get it from 50.00 up."""
    if member and total >= 50:
        return round(total * 0.9, 2)
    if total >= 100:
        return round(total * 0.9, 2)
    return total
