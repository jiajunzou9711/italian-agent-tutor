#!/usr/bin/env python3
"""Run a real-agent cold-start acceptance test in an isolated disposable copy."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/jiajunzou9711/italian-agent-tutor.git"
APP_CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
QUESTION_LABELS = ("[中译意", "[填空", "[问答", "[改错", "[阅读理解", "[Translate", "[Complete")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    result: str
    agent: str
    scenario: str
    run: int
    workspace: str
    checks: list[Check]
    turns: list[str]
    error: str = ""

    def to_json(self) -> dict:
        data = asdict(self)
        data["checks"] = [asdict(check) for check in self.checks]
        return data


class AgentInfraError(RuntimeError):
    pass


def run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )


class ClaudeRunner:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.session_id: str | None = None

    def turn(self, prompt: str) -> str:
        command = [
            "claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits",
            "--allowedTools", "Read,Edit,Write", "--no-chrome", "--strict-mcp-config",
        ]
        if self.session_id:
            command.extend(["-r", self.session_id])
        command.append(prompt)
        completed = run_command(command, cwd=self.workspace)
        if completed.returncode != 0:
            raise AgentInfraError(completed.stderr.strip() or "Claude exited without a result")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AgentInfraError(f"Claude returned invalid JSON: {error}") from error
        if payload.get("is_error"):
            raise AgentInfraError(payload.get("result") or "Claude reported an error")
        self.session_id = payload.get("session_id") or self.session_id
        if not self.session_id:
            raise AgentInfraError("Claude did not return a session id")
        return payload.get("result", "").strip()


class CodexRunner:
    def __init__(self, workspace: Path, temp_root: Path):
        self.workspace = workspace
        self.session_id: str | None = None
        self.codex = APP_CODEX if APP_CODEX.is_file() else Path(shutil.which("codex") or "")
        if not self.codex or not self.codex.exists():
            raise AgentInfraError("Codex CLI not found")
        self.codex_home = temp_root / "codex-home"
        self.codex_home.mkdir()
        auth = Path.home() / ".codex" / "auth.json"
        if not auth.is_file():
            raise AgentInfraError("Codex auth.json not found")
        (self.codex_home / "auth.json").symlink_to(auth)

    def turn(self, prompt: str) -> str:
        output = self.codex_home.parent / "codex-last-message.txt"
        events = self.codex_home.parent / "codex-events.jsonl"
        if self.session_id:
            command = [str(self.codex), "exec", "resume", self.session_id, prompt, "--json"]
        else:
            command = [
                str(self.codex), "exec", "-C", str(self.workspace), "--sandbox", "workspace-write",
                "--json", "--output-last-message", str(output), prompt,
            ]
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        completed = run_command(command, cwd=self.workspace, env=env)
        if completed.returncode != 0:
            raise AgentInfraError(completed.stderr.strip() or "Codex exited without a result")
        event_text = completed.stdout
        events.write_text(event_text, encoding="utf-8")
        messages: list[str] = []
        for line in event_text.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                self.session_id = event.get("thread_id")
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                messages.append(item.get("text", ""))
        if not self.session_id:
            raise AgentInfraError("Codex did not return a thread id")
        if not messages and output.is_file():
            messages.append(output.read_text(encoding="utf-8"))
        result = "\n".join(message.strip() for message in messages if message.strip())
        if not result:
            raise AgentInfraError("Codex returned no agent message")
        return result


def disposable_workspace(source: str) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="italian-agent-acceptance."))
    workspace = temp_root / "italian-agent-tutor"
    if source == "remote":
        completed = run_command(["git", "clone", "--quiet", REMOTE, str(workspace)], cwd=temp_root)
        if completed.returncode != 0:
            raise AgentInfraError(completed.stderr.strip() or "Anonymous clone failed")
    else:
        shutil.copytree(ROOT, workspace, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    return temp_root, workspace


def contains_question(text: str) -> bool:
    return "?" in text or "？" in text


def contains_route(text: str) -> bool:
    lowered = text.lower()
    english = all(token in lowered for token in ("short term", "mid term", "long term"))
    chinese = all(token in text for token in ("短期", "中期", "长期"))
    return english or chinese


def asks_for_gist(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("大意", "意思", "gist", "讲什么", "读懂了什么", "理解了什么"))


def interest_is_persisted(text: str) -> bool:
    lowered = text.lower()
    coffee = "咖啡" in text or "coffee" in lowered
    photography = "旅行摄影" in text or ("travel" in lowered and "photograph" in lowered)
    return coffee and photography


def fallback_is_disclosed(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in ("非即时", "常青", "常识性", "not current", "evergreen", "不是当天", "不是当前")
    )


def is_zero_beginner_profile(text: str) -> bool:
    lowered = text.lower()
    a1 = "a1 beginner" in lowered
    no_prior = any(
        token in lowered
        for token in (
            "zero-beginner", "zero beginner", "complete beginner", "零基础",
            "从未学过", "never studied", "no prior", "prior study: none",
        )
    )
    placement_not_pending = "placement status: not started" not in lowered and "placement status: pending" not in lowered
    return a1 and no_prior and placement_not_pending


def unanswered_main_item_has_no_evidence(mastery: str) -> bool:
    ledger = mastery.split("## Mastery ledger", 1)[-1].split("## Vocabulary", 1)[0]
    target = re.compile(r"(self[- ]?introduction|greeting|自我介绍|问候|mi chiamo)", re.IGNORECASE)
    credited = re.compile(r"(E2|E3|E4|Pending|Sealed)", re.IGNORECASE)
    return not any(target.search(line) and credited.search(line) for line in ledger.splitlines())


def git_head(workspace: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=workspace, text=True, capture_output=True
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def run_zero_beginner(agent: str, run_number: int, source: str, keep: bool) -> Report:
    temp_root, workspace = disposable_workspace(source)
    turns: list[str] = []
    checks: list[Check] = []
    try:
        initial_head = git_head(workspace)
        runner = ClaudeRunner(workspace) if agent == "claude" else CodexRunner(workspace, temp_root)
        prompts = [
            "开始设置意大利语私教",
            "中文",
            "我想在意大利日常生活交流，能够处理购物、餐厅和邻居聊天。",
            "完全零基础，从来没有学过意大利语。",
            "我对咖啡和旅行摄影很感兴趣，备用主题是意大利美食。",
        ]
        for index, prompt in enumerate(prompts):
            response = runner.turn(prompt)
            turns.append(response)
            if index < 4:
                checks.append(Check(f"setup_turn_{index + 1}_asks_one_question", contains_question(response)))

        profile = (workspace / "learner-profile.md").read_text(encoding="utf-8")
        briefing = (workspace / "config/daily-briefing.md").read_text(encoding="utf-8")
        mastery = (workspace / "records/mastery.md").read_text(encoding="utf-8")
        checks.extend([
            Check("setup_completed", "Setup Status: Completed" in profile),
            Check("zero_beginner_skips_placement", is_zero_beginner_profile(profile)),
            Check("interest_persisted", interest_is_persisted(briefing)),
            Check("mastery_route_persisted", "Pending onboarding" not in mastery and "Complete onboarding" not in mastery),
            Check("profile_does_not_duplicate_route", "\nRoute:" not in profile),
        ])

        opening = runner.turn("开始意大利语训练")
        turns.append(opening)
        has_route = contains_route(opening)
        no_main_item = not any(label in opening for label in QUESTION_LABELS)
        evergreen_disclosed = fallback_is_disclosed(opening)
        checks.extend([
            Check("opening_contains_route", has_route),
            Check("opening_uses_interest", any(token in opening.lower() for token in ("咖啡", "coffee", "caffè", "fotograf"))),
            Check("opening_discloses_no_web_fallback", evergreen_disclosed),
            Check("opening_asks_for_gist", asks_for_gist(opening)),
            Check("opening_has_no_main_item", no_main_item),
            Check("agent_does_not_infer_learner_name", "jia" + "jun" not in opening.lower()),
        ])

        after_gist = runner.turn("这段话大意是一个人喝咖啡，并用相机记录旅行。")
        turns.append(after_gist)
        checks.extend([
            Check("post_gist_explains_briefing", any(token in after_gist for token in ("准确", "意思", "译", "meaning"))),
            Check("post_gist_has_one_main_item", sum(after_gist.count(label) for label in QUESTION_LABELS) == 1),
        ])

        end = runner.turn("结束训练")
        turns.append(end)
        final_mastery = (workspace / "records/mastery.md").read_text(encoding="utf-8")
        checks.extend([
            Check("unanswered_item_creates_no_mastery_evidence", unanswered_main_item_has_no_evidence(final_mastery)),
            Check("agent_never_infers_learner_name", all("jia" + "jun" not in turn.lower() for turn in turns)),
            Check("end_does_not_reveal_delayed_check", not any(token in end for token in ("下次前", "下节第", "前三题", "第1题", "第 1 题"))),
            Check("no_automatic_commit", git_head(workspace) == initial_head),
        ])

        failed = [check for check in checks if not check.passed]
        result = "PASS" if not failed else "TEMPLATE_FAIL"
        report = Report(result, agent, "zero-beginner", run_number, str(workspace), checks, turns)
    except AgentInfraError as error:
        report = Report("INFRA_FAIL", agent, "zero-beginner", run_number, str(workspace), checks, turns, str(error))
    except Exception as error:  # An unexpected harness failure is infrastructure, never a pass.
        report = Report("INFRA_FAIL", agent, "zero-beginner", run_number, str(workspace), checks, turns, repr(error))

    artifact = ROOT / "artifacts" / "acceptance"
    artifact.mkdir(parents=True, exist_ok=True)
    report_path = artifact / f"{agent}-zero-beginner-run-{run_number}.json"
    report_path.write_text(json.dumps(report.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    if not keep and report.result == "PASS":
        shutil.rmtree(temp_root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude"))
    parser.add_argument("--scenario", choices=("zero-beginner",), default="zero-beginner")
    parser.add_argument("--all", action="store_true", help="Run both agents")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--source", choices=("local", "remote"), default="local")
    parser.add_argument("--keep-workspaces", action="store_true")
    args = parser.parse_args()
    if not args.all and not args.agent:
        parser.error("choose --agent or --all")
    agents = ("codex", "claude") if args.all else (args.agent,)
    reports: list[Report] = []
    for agent in agents:
        for run_number in range(1, args.runs + 1):
            report = run_zero_beginner(agent, run_number, args.source, args.keep_workspaces)
            reports.append(report)
            print(f"{report.result}: {agent} zero-beginner run {run_number}")
            for check in report.checks:
                if not check.passed:
                    print(f"  FAIL {check.name}: {check.detail}")
            if report.error:
                print(f"  {report.error}")
    return 0 if reports and all(report.result == "PASS" for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
