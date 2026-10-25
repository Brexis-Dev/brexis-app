"""Guard the security-relevant dependency floors."""
import os
import re

MINIMUMS = {
    "flask": (3, 1, 3),
    "requests": (2, 33, 0),
    "python-dotenv": (1, 2, 2),
}


def _parse():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "requirements.txt")
    pins = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^([A-Za-z0-9_.-]+)==([0-9]+(?:\.[0-9]+)*)", line.strip())
            if m:
                pins[m.group(1).lower()] = tuple(int(x) for x in m.group(2).split("."))
    return pins


def test_vulnerable_versions_bumped():
    pins = _parse()
    for pkg, floor in MINIMUMS.items():
        assert pkg in pins, f"{pkg} missing from requirements.txt"
        assert pins[pkg] >= floor, f"{pkg}=={pins[pkg]} is below the required {floor}"
