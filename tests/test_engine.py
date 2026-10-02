import json
import unittest
from cryptolab import *

EXAMPLE = json.loads(
    '{"timestamp": 1000, "assets": {"ETH": {"price": "2000", "liquidation_threshold": "0.8", "updated_at": 900}, "USD": {"price": "1", "liquidation_threshold": "0", "updated_at": 900}}, "positions": [{"asset": "ETH", "amount": "1", "side": "collateral"}, {"asset": "USD", "amount": "1200", "side": "debt"}], "scenarios": [{"name": "base"}, {"name": "crash", "price_multipliers": {"ETH": "0.5"}}]}'
)


class EngineTests(unittest.TestCase):
    def test_health(self):
        rows = analyze(EXAMPLE)["scenarios"]
        self.assertFalse(rows[0]["liquidatable"])
        self.assertTrue(rows[1]["liquidatable"])

    def test_stale(self):
        with self.assertRaises(ValueError):
            analyze({**EXAMPLE, "timestamp": 99999})

    def test_seize_cap(self):
        row = analyze(EXAMPLE)["scenarios"][1]
        self.assertLessEqual(
            Decimal(row["seize_value"]), Decimal(row["collateral_value"])
        )

    def test_deterministic(self):
        self.assertEqual(analyze(EXAMPLE), analyze(EXAMPLE))

    def test_cli_json(self):
        import subprocess, sys

        result = subprocess.run(
            [sys.executable, "-m", "cryptolab", "examples/input.json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), analyze(EXAMPLE))

    def test_cli_csv(self):
        import subprocess, sys, csv, io

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cryptolab",
                "examples/input.json",
                "--format",
                "csv",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            list(csv.reader(io.StringIO(result.stdout)))[0], ["path", "value"]
        )

    def test_duplicate_json_keys(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                load_input(path)

    def test_atomic_output(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            self.assertEqual(main(["examples/input.json", "--output", str(path)]), 0)
            self.assertEqual(json.loads(path.read_text()), analyze(EXAMPLE))

    def test_input_unchanged(self):
        import copy

        before = copy.deepcopy(EXAMPLE)
        analyze(EXAMPLE)
        self.assertEqual(before, EXAMPLE)


if __name__ == "__main__":
    unittest.main()
