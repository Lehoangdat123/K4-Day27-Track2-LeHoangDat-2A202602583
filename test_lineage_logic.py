import sys
from pathlib import Path

sys.path.insert(0, str(Path("harness/child_env").resolve()))`r`nsys.path.insert(0, str(Path("solution").resolve()))

from defense import check_lineage_run


class FakeTools:
    def __init__(self, result):
        self.result = result

    def lineage_graph_slice(self, run_id):
        return self.result


class FakeContext:
    def __init__(self, result):
        self.tools = FakeTools(result)
        self.baseline = {
            "lineage_duration_ms_max": 5134.9804
        }


def run_test(name, payload, result, expected_alert):
    verdict = check_lineage_run(payload, FakeContext(result))
    passed = verdict.alert == expected_alert
    print(
        f"{'PASS' if passed else 'FAIL'} | {name} | "
        f"expected alert={expected_alert}, got={verdict.alert} | "
        f"reason={verdict.reason}"
    )
    return passed


tests = [
    (
        "missing upstream dependency",
        {"run_id": "test-run", "expected_upstream": ["source_A", "source_B"]},
        {
            "duration_ms": 1000,
            "actual_upstream": ["source_A"],
            "actual_downstream_count": 1,
        },
        True,
    ),
    (
        "all expected upstream dependencies present",
        {"run_id": "test-run", "expected_upstream": ["source_A"]},
        {
            "duration_ms": 1000,
            "actual_upstream": ["source_A"],
            "actual_downstream_count": 1,
        },
        False,
    ),
    (
        "no expected upstream field",
        {"run_id": "test-run"},
        {
            "duration_ms": 1000,
            "actual_upstream": ["source_A"],
            "actual_downstream_count": 1,
        },
        False,
    ),
]

results = [
    run_test(name, payload, result, expected)
    for name, payload, result, expected in tests
]

print(f"\n{sum(results)}/{len(results)} tests passed")
sys.exit(0 if all(results) else 1)
