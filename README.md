# Italian Agent Tutor / AI 意大利语私教

A reusable, text-only Italian tutor for project-based AI agents such as Codex, Claude Code, and Cursor. It adapts after every answer, keeps one challenge active at a time, and stores progress in this workspace.

这是一个可复用的纯文字意大利语训练模板。它会在每次回答后实时判断正误、独立程度和当前负荷，只推进一个合适的小挑战，并把进度保存在你的项目副本中。

## Quick start / 快速开始

1. Click **Use this template** on GitHub and create your own repository, or download this folder.
2. Open your copy as the active workspace in a file-capable AI agent.
3. Say: `开始设置意大利语私教` or `Set up my Italian tutor`.
4. Answer the setup questions. Complete a short placement only if you have studied Italian before.
5. Later, say `开始意大利语训练` / `Start Italian training`.

The agent asks setup questions one at a time. Do not edit configuration files first.

Agent 会逐项询问你的解释语言、目标、基础和兴趣主题，不需要先手动改配置文件。

## Commands / 指令

- `开始设置意大利语私教` / `Set up my Italian tutor`
- `开始意大利语训练` / `Start Italian training`
- `继续意大利语训练` / `Continue Italian training`
- `结束训练` / `End training`

An ordinary vocabulary, grammar, or translation question is answered directly and does not update records.

普通的单词、语法或翻译问题不会自动开启正式训练，也不会修改学习记录。

## What makes it adaptive / 自适应机制

The Controller evaluates every answer in a fixed order: task completion, independence, error severity, evidence strength, load fit, and next action. Two independent successes raise only one load variable. Errors lower support or trigger at most two transfer items in a new noun, scene, or format. A skill is sealed only by an unannounced independent retrieval in a later session.

详细规则在 `session-protocol.md`，当前状态在 `records/mastery.md`。

## Boundaries / 边界

- Trains reading, grammar in context, writing, and written interaction.
- Does not claim to train or measure listening, pronunciation, or spoken production.
- Current-interest briefings use verified sources when web access exists; otherwise the agent clearly uses evergreen material.
- Records are written locally. Automatic Git commits are disabled by default.
- A chat-only assistant without workspace read/write access cannot reliably preserve progress across days.

## Validate / 验证

```bash
python3 scripts/validate_template.py .
python3 -m unittest discover -s tests -v
python3 scripts/acceptance.py --agent claude --scenario zero-beginner
python3 scripts/acceptance.py --all --runs 2
```

## Files / 文件

- `AGENTS.md`: portable workspace governance
- `learner-profile.md`: setup, goal, and placement
- `config/daily-briefing.md`: interest-based opening configuration
- `records/mastery.md`: current mastery, queue, route, vocabulary, and short session log
- `session-protocol.md`: onboarding, Controller, session, and record-writing protocol
- `docs/syllabus.md`: adaptive A1–B2 direction

Licensed under the MIT License.
