import json
import unittest
from pathlib import Path


class CuratedObservationsTest(unittest.TestCase):
    def test_variant_totals_exclude_focused_retries(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "leaderboards/data/reconciled-observations-20261008.json").read_text())
        for item in data["observations"][:2]:
            records = item["records"]
            totals = [sum(record["score"] for record in records if record["run"] == run) for run in (1, 2)]
            self.assertEqual(totals, item["complete_pass_totals"])
            self.assertEqual(len([record for record in records if record["run"] == 3]), 3)
            self.assertTrue(all(record["judge_protocol"] == "source-aware-v2" for record in records))
        qwen = data["observations"][2]
        self.assertEqual(sum(record["score"] for record in qwen["records"]), 51)
        self.assertFalse(qwen["mixed_protocol_total_rankable"])
        self.assertEqual(qwen["mixed_protocol_total"], 55)
        # Curated data contains only evidence metadata, never raw candidate answers.
        self.assertNotIn('"answer":', json.dumps(data))

    def test_changed_chart_rows_match_curated_data(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "leaderboards/data/reconciled-observations-20261008.json").read_text())
        chart_rows = []
        for line in (root / "codex_claude_matrix.html").read_text().splitlines():
            if line.strip().startswith("["):
                try:
                    chart_rows.append(json.loads(line.strip().rstrip(",")))
                except json.JSONDecodeError:
                    pass
        for row in data["presentation_rows"]:
            self.assertIn(row, chart_rows)
        for row in data["presentation_rows"]:
            if row[1].startswith("Muse"):
                self.assertEqual(row[8], "-")
