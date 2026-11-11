import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from controller_model import ControllerState, Outcome, decide  # noqa: E402
from acceptance import (  # noqa: E402
    contains_question,
    contains_route,
    fallback_is_disclosed,
    interest_is_persisted,
    is_zero_beginner_profile,
    asks_for_gist,
    unanswered_main_item_has_no_evidence,
)
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
        self.assertEqual(result.state.repairs_used, 0)

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

    def test_failed_check_on_sealed_drops_only_to_pending(self):
        result = decide(ControllerState(level="Sealed", load=1), Outcome.DELAYED_CHECK_FAILURE)
        self.assertEqual(result.state.level, "Pending")

    def test_failure_on_learning_stays_learning(self):
        result = decide(ControllerState(level="Learning"), Outcome.DELAYED_CHECK_FAILURE)
        self.assertEqual(result.state.level, "Learning")

    def test_third_evaluated_repair_parks_instead_of_looping(self):
        state = ControllerState(repairs_used=2)
        result = decide(state, Outcome.REPAIR_FAILURE)
        self.assertEqual(result.action, "park_point")
        self.assertTrue(result.state.parked)

    def test_presented_but_unanswered_repair_is_not_counted(self):
        result = decide(ControllerState(), Outcome.REPAIR_PRESENTED)
        self.assertEqual(result.state.repairs_used, 0)
        self.assertEqual(result.action, "await_repair_answer")

    def test_two_session_reference_sequence(self):
        state = ControllerState()
        scaffolded = decide(state, Outcome.ASSISTED)
        self.assertEqual(scaffolded.evidence, "E1")
        independent = decide(scaffolded.state, Outcome.INDEPENDENT)
        self.assertEqual(independent.evidence, "E2")
        local = decide(independent.state, Outcome.LOCAL_ERROR)
        self.assertTrue(local.preserve_main_point)
        self.assertEqual(local.action, "correct_and_raise_one_variable")
        self.assertEqual(local.state.load, 1)
        blocking = decide(local.state, Outcome.BLOCKING_ERROR)
        presented = decide(blocking.state, Outcome.REPAIR_PRESENTED)
        self.assertEqual(presented.state.repairs_used, 0)
        pending = decide(presented.state, Outcome.FRESH_SCENE_SUCCESS)
        self.assertEqual(pending.state.level, "Pending")
        later = decide(pending.state, Outcome.LATER_SESSION_SUCCESS)
        self.assertEqual(later.state.level, "Sealed")
        self.assertEqual(later.evidence, "E4")


class TemplateTests(unittest.TestCase):
    def test_repository_template_is_valid(self):
        self.assertEqual(validate(ROOT), [])

    def test_validator_detects_private_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for relative in (
                "README.md", "AGENTS.md", "CLAUDE.md", "LICENSE", "learner-profile.md",
                "config/daily-briefing.md", "records/mastery.md", "docs/syllabus.md",
                "session-protocol.md", "scripts/controller_model.py", "scripts/acceptance.py",
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

    def test_setup_completion_is_atomic_and_mastery_owns_route(self):
        protocol = (ROOT / "session-protocol.md").read_text(encoding="utf-8")
        self.assertIn("Route authority: only `records/mastery.md`", protocol)
        self.assertIn("write `Setup Status: Completed` last", protocol)
        self.assertIn("If any required write is missing", protocol)

    def test_enabled_briefing_is_a_hard_session_gate(self):
        protocol = (ROOT / "session-protocol.md").read_text(encoding="utf-8")
        self.assertIn("HARD GATE", protocol)
        self.assertIn("must end after asking only for the gist", protocol)
        self.assertIn("must not contain teaching or a main-line item", protocol)

    def test_scaffolded_first_attempt_cannot_be_e2(self):
        protocol = (ROOT / "session-protocol.md").read_text(encoding="utf-8")
        self.assertIn("same construction or answer frame", protocol)
        self.assertIn("the next correct response is capped at E1", protocol)

    def test_delayed_check_is_never_disclosed(self):
        protocol = (ROOT / "session-protocol.md").read_text(encoding="utf-8")
        self.assertIn("Never disclose its content, format, timing, or position", protocol)
        self.assertIn("future session; undisclosed", protocol)

    def test_template_contains_no_learner_name_seed(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in ROOT.rglob("*")
            if path.is_file() and path.suffix in {"", ".md", ".py"} and ".git" not in path.parts
        )
        self.assertNotIn("Jia" + "jun", combined)

    def test_acceptance_question_detection(self):
        self.assertTrue(contains_question("你希望用哪种语言？"))
        self.assertFalse(contains_question("设置完成。"))

    def test_acceptance_route_and_gist_are_bilingual(self):
        self.assertTrue(contains_route("Short term: a\nMid term: b\nLong term: c"))
        self.assertTrue(contains_route("短期：a\n中期：b\n长期：c"))
        self.assertTrue(asks_for_gist("你大致读懂了什么？"))
        self.assertTrue(asks_for_gist("What is the gist?"))

    def test_acceptance_handles_equivalent_bilingual_wording(self):
        self.assertTrue(interest_is_persisted("Primary Interest: Coffee and travel photography"))
        self.assertTrue(interest_is_persisted("主要兴趣：咖啡与旅行摄影"))
        self.assertTrue(fallback_is_disclosed("这是常识性内容，不是当前新闻。"))
        self.assertTrue(fallback_is_disclosed("This is evergreen material, not current news."))
        self.assertTrue(is_zero_beginner_profile("Placement Status: Complete（零基础初始化）\nWorking Level: A1 beginner"))
        self.assertTrue(is_zero_beginner_profile("Placement Status: Not required (zero beginner)\nWorking Level: A1 beginner (initial)"))

    def test_zero_beginner_accepts_english_none_prior_study(self):
        self.assertTrue(is_zero_beginner_profile(
            "Prior Study: None\nWorking Level: A1 beginner\nPlacement Status: Complete"))
        self.assertTrue(is_zero_beginner_profile(
            "Prior Study: No prior study\nWorking Level: A1 beginner\nPlacement Status: Complete"))
        self.assertTrue(is_zero_beginner_profile(
            "Prior Study: 从未学过意大利语\nWorking Level: A1 beginner\nPlacement Status: Complete"))
        self.assertFalse(is_zero_beginner_profile(
            "Prior Study: Two years of classes\nWorking Level: A1 beginner\nPlacement Status: Complete"))

    def test_briefing_gist_evidence_does_not_fail_unanswered_main_item_check(self):
        mastery = """## Mastery ledger
| Very short reading gist | Learning (E2) | today | central theme |
| Basic greetings and self-introduction | Untested | — | first answer due |
## Vocabulary
"""
        self.assertTrue(unanswered_main_item_has_no_evidence(mastery))
        credited = mastery.replace("| Untested |", "| Learning (E2) |")
        self.assertFalse(unanswered_main_item_has_no_evidence(credited))


if __name__ == "__main__":
    unittest.main()
