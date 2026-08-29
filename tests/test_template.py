import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from controller_model import ControllerState, Outcome, decide  # noqa: E402
from validate_template import validate  # noqa: E402


class ControllerTests(unittest.TestCase):
    def test_two_independent_successes_raise_one_variable(self):
        first = decide(ControllerState(), Outcome.INDEPENDENT)
        second = decide(first.state, Outcome.INDEPENDENT)
        self.assertEqual(first.action, "continue")
        self.assertEqual(second.action, "raise_one_variable")
        self.assertEqual(second.state.load, 1)

    def test_assisted_success_stays_e1_and_lowers_after_two(self):
        first = decide(ControllerState(), Outcome.ASSISTED)
        second = decide(first.state, Outcome.ASSISTED)
        self.assertEqual(first.evidence, "E1")
        self.assertEqual(second.evidence, "E1")
        self.assertEqual(second.state.load, -1)

    def test_blocking_error_lowers_load(self):
        result = decide(ControllerState(load=2), Outcome.BLOCKING_ERROR)
        self.assertEqual(result.action, "lower_one_variable")
        self.assertEqual(result.state.load, 1)
        self.assertEqual(result.state.repairs_used, 1)

    def test_local_error_preserves_main_direction(self):
        result = decide(ControllerState(main_point="articles"), Outcome.LOCAL_ERROR)
        self.assertEqual(result.action, "correct_and_delayed_check")
        self.assertEqual(result.state.main_point, "articles")
        self.assertTrue(result.preserve_main_point)

    def test_fresh_scene_success_becomes_pending(self):
        result = decide(ControllerState(), Outcome.FRESH_SCENE_SUCCESS)
        self.assertEqual(result.state.level, "Pending")
        self.assertEqual(result.evidence, "E3")

    def test_later_session_success_seals(self):
        result = decide(ControllerState(level="Pending"), Outcome.LATER_SESSION_SUCCESS)
        self.assertEqual(result.state.level, "Sealed")
        self.assertEqual(result.evidence, "E4")

    def test_failed_delayed_check_returns_to_learning(self):
        result = decide(ControllerState(level="Pending", load=1), Outcome.DELAYED_CHECK_FAILURE)
        self.assertEqual(result.state.level, "Learning")
        self.assertEqual(result.state.load, 0)

    def test_third_blocking_failure_parks_instead_of_looping(self):
        state = ControllerState(repairs_used=2)
        result = decide(state, Outcome.BLOCKING_ERROR)
        self.assertEqual(result.action, "park_point")
        self.assertTrue(result.state.parked)


class TemplateTests(unittest.TestCase):
    def test_repository_template_is_valid(self):
        self.assertEqual(validate(ROOT), [])

    def test_validator_detects_private_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for relative in (
                "README.md", "AGENTS.md", "CLAUDE.md", "LICENSE", "learner-profile.md",
                "config/daily-briefing.md", "records/mastery.md", "docs/syllabus.md",
                "session-protocol.md", "scripts/controller_model.py",
            ):
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = ROOT / relative
                destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            private_path = "/" + "Users/private/path"
            (target / "README.md").write_text(private_path, encoding="utf-8")
            self.assertTrue(any(("/" + "Users/") in error for error in validate(target)))

    def test_onboarding_covers_zero_beginner_prior_study_and_exam(self):
        protocol = (ROOT / "session-protocol.md").read_text(encoding="utf-8")
        self.assertIn("reports no prior Italian", protocol)
        self.assertIn("has prior study", protocol)
        self.assertIn("If exam: ask its exact name and date", protocol)
        self.assertIn("verify requirements from an official source", protocol)

    def test_briefing_has_verified_and_no_web_paths(self):
        protocol = (ROOT / "session-protocol.md").read_text(encoding="utf-8")
        self.assertIn("verify them first with a reliable source", protocol)
        self.assertIn("use evergreen content", protocol)
        self.assertIn("it is not current news", protocol)

    def test_blank_copy_starts_unconfigured(self):
        profile = (ROOT / "learner-profile.md").read_text(encoding="utf-8")
        mastery = (ROOT / "records/mastery.md").read_text(encoding="utf-8")
        self.assertIn("Setup Status: Not completed", profile)
        self.assertIn("Focus now: Complete onboarding", mastery)
        self.assertIn("No formal sessions recorded", mastery)


if __name__ == "__main__":
    unittest.main()
