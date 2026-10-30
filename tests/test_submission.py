import copy
import io
import json
import shutil
import unittest
import uuid
from contextlib import redirect_stdout

from scripts.check_submission import check_evidence
from src.domain import ROOT
from src.evaluate import main as evaluate_main


class SubmissionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = ROOT / "runtime/tests" / uuid.uuid4().hex
        cls.base.mkdir(parents=True)
        shutil.copytree(ROOT / "data", cls.base / "data")
        shutil.copytree(ROOT / "examples/inputs", cls.base / "examples/inputs")
        with redirect_stdout(io.StringIO()):
            result = evaluate_main(["--mode", "mock", "--out", str(cls.base / "examples/mock"), "--env-file", str(cls.base / "no-env")])
        if result != 0:
            raise AssertionError("offline evidence fixture did not pass")

    @classmethod
    def tearDownClass(cls):
        assert cls.base.resolve().is_relative_to((ROOT / "runtime/tests").resolve())
        shutil.rmtree(cls.base)

    def setUp(self):
        self.temp = ROOT / "runtime/tests" / uuid.uuid4().hex
        shutil.copytree(self.base, self.temp)

    def tearDown(self):
        assert self.temp.resolve().is_relative_to((ROOT / "runtime/tests").resolve())
        shutil.rmtree(self.temp)

    def write_json(self, relative, value):
        path = self.temp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_json(self, relative):
        return json.loads((self.temp / relative).read_text(encoding="utf-8"))

    def test_complete_evidence_passes(self):
        self.assertEqual(check_evidence(self.temp, "mock"), [])

    def test_summary_without_real_outputs_is_rejected(self):
        self.write_json("examples/real/results.json", json.loads((ROOT / "examples/real/results.json").read_text(encoding="utf-8")))
        issues = check_evidence(self.temp, "real")
        self.assertTrue(any("normal.output.json" in issue for issue in issues))
        self.assertTrue(any("normal.trace.md" in issue for issue in issues))

    def test_missing_trace_is_rejected(self):
        (self.temp / "examples/mock/normal.trace.md").unlink()
        self.assertTrue(any("normal.trace.md" in issue for issue in check_evidence(self.temp, "mock")))

    def test_invalid_output_json_is_rejected(self):
        (self.temp / "examples/mock/normal.output.json").write_text("invalid json", encoding="utf-8")
        self.assertTrue(any("mock/normal" in issue for issue in check_evidence(self.temp, "mock")))

    def test_unrelated_trace_is_rejected(self):
        (self.temp / "examples/mock/normal.trace.md").write_text("unrelated trace", encoding="utf-8")
        self.assertTrue(any("Trace 内容" in issue for issue in check_evidence(self.temp, "mock")))

    def test_duplicate_case_cannot_replace_missing_case(self):
        data = self.read_json("examples/mock/results.json")
        data["cases"][-1] = copy.deepcopy(data["cases"][0])
        self.write_json("examples/mock/results.json", data)
        self.assertTrue(any("用例集合" in issue for issue in check_evidence(self.temp, "mock")))

    def test_output_mode_must_match_summary(self):
        data = self.read_json("examples/mock/normal.output.json")
        data["runs"][0]["mode"] = "real"
        self.write_json("examples/mock/normal.output.json", data)
        self.assertTrue(any("mock/normal" in issue for issue in check_evidence(self.temp, "mock")))

    def test_changed_input_cannot_reuse_old_output(self):
        data = self.read_json("examples/inputs/normal.json")
        data["budget"] += 1
        self.write_json("examples/inputs/normal.json", data)
        self.assertTrue(any("mock/normal" in issue for issue in check_evidence(self.temp, "mock")))

    def test_material_changes_require_new_evidence(self):
        data = self.read_json("data/materials.json")
        data[0]["content"] = "修改后的资料"
        self.write_json("data/materials.json", data)
        self.assertTrue(any("素材与当前数据不一致" in issue for issue in check_evidence(self.temp, "mock")))

    def test_summary_actions_are_recomputed_from_outputs(self):
        data = self.read_json("examples/mock/results.json")
        data["cases"][0]["actions"] = ["finish"]
        self.write_json("examples/mock/results.json", data)
        self.assertTrue(any("动作路径" in issue for issue in check_evidence(self.temp, "mock")))

    def test_corrupt_summary_returns_an_issue_instead_of_crashing(self):
        (self.temp / "examples/mock/results.json").write_text("[]", encoding="utf-8")
        self.assertTrue(check_evidence(self.temp, "mock"))


if __name__ == "__main__":
    unittest.main()
