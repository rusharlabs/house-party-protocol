"""A user policy only hardens: it adds `BLOCK`/`MANUAL` rules or raises a built-in class, never lowers one.

`hpp/policy.py` ships fixed rules. A project can declare more in `.hpp/policy.json` — a pattern,
the class it earns and the reason — and can raise a built-in `MANUAL` rule to `BLOCK`. The file
cannot exempt anything: a rule with action `ALLOW`, a raise that keeps or lowers a class, or a rule
that reuses a built-in id is refused before any command is classified. A refused policy is a refused
`policy check` (exit 2), never a silent fallback to the built-ins: a project that asked for a policy
and did not get it must not read `ALLOW`.
"""
from __future__ import annotations

import json

import pytest

from hpp import cli
from hpp.policy import POLICY_SCHEMA, PolicyError, assess, load_policy, validate_policy

BLOCK_RULE = {"id": "prod-deploy", "action": "BLOCK", "pattern": r"\bkubectl\s+apply\b.*\bprod\b",
              "reason": "production deploys go through the release gate"}
MANUAL_RULE = {"id": "image-push", "action": "MANUAL", "pattern": r"\bdocker\s+push\b",
               "reason": "pushing an image is a publication"}


def _policy(**body):
    return {"schema": POLICY_SCHEMA, **body}


def _write(tmp_path, document, name="policy.json"):
    path = tmp_path / ".hpp" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- hardening

def test_a_user_block_rule_blocks_a_command_no_built_in_rule_knows():
    command = "kubectl apply -f deploy/prod.yaml"
    assert assess(command)["action"] == "ALLOW"  # the built-ins alone let it through
    verdict = assess(command, validate_policy(_policy(rules=[BLOCK_RULE])))
    assert verdict["action"] == "BLOCK"
    assert verdict["rule"] == "prod-deploy"
    assert verdict["reason"] == BLOCK_RULE["reason"]
    assert verdict["source"] == "policy"


def test_a_user_manual_rule_adds_a_human_gate():
    command = "docker push registry.example.com/app:1.0"
    assert assess(command)["action"] == "ALLOW"
    verdict = assess(command, validate_policy(_policy(rules=[MANUAL_RULE])))
    assert verdict["action"] == "MANUAL" and verdict["rule"] == "image-push" and verdict["source"] == "policy"


def test_a_built_in_manual_rule_can_be_raised_to_block():
    command = "curl -s https://example.com/data"
    assert assess(command) == {"action": "MANUAL", "rule": "external-send",
                               "reason": "external transfer needs a human gate", "source": "built-in"}
    raised = assess(command, validate_policy(_policy(**{"raise": {"external-send": "BLOCK"}})))
    assert raised["action"] == "BLOCK" and raised["rule"] == "external-send" and raised["source"] == "policy"


def test_user_rules_are_matched_case_insensitively_like_the_built_ins():
    verdict = assess("KUBECTL APPLY -f PROD.yaml", validate_policy(_policy(rules=[BLOCK_RULE])))
    assert verdict["action"] == "BLOCK"


# --------------------------------------------------------------------------- what is refused

@pytest.mark.parametrize("document, fragment", [
    (_policy(**{"raise": {"force-push": "MANUAL"}}), "force-push"),          # lowers a BLOCK
    (_policy(**{"raise": {"force-push": "ALLOW"}}), "force-push"),           # exempts a BLOCK
    (_policy(**{"raise": {"external-send": "MANUAL"}}), "external-send"),    # keeps the class
    (_policy(**{"raise": {"external-send": "ALLOW"}}), "external-send"),     # exempts a MANUAL
    (_policy(**{"raise": {"no-such-rule": "BLOCK"}}), "no-such-rule"),       # unknown built-in
    (_policy(rules=[{**BLOCK_RULE, "action": "ALLOW"}]), "ALLOW"),           # an exemption rule
    (_policy(rules=[{**BLOCK_RULE, "id": "force-push"}]), "force-push"),     # shadows a built-in id
    (_policy(rules=[{**BLOCK_RULE, "pattern": "("}]), "pattern"),            # invalid regex
    (_policy(rules=[BLOCK_RULE, BLOCK_RULE]), "prod-deploy"),                # duplicate id
    (_policy(rules=[{**BLOCK_RULE, "reason": ""}]), "reason"),               # a rule without a reason
    (_policy(rules=[{**BLOCK_RULE, "extra": 1}]), "extra"),                  # a key outside the contract
    (_policy(allow=["git push"]), "allow"),                                  # no allow list exists
    ({"schema": "hpp.policy/v0", "rules": []}, "schema"),                    # wrong schema
    ("not an object", "object"),
])
def test_a_policy_that_would_lower_a_class_or_break_the_contract_is_refused(document, fragment):
    with pytest.raises(PolicyError) as caught:
        validate_policy(document)
    assert fragment in str(caught.value)


def test_a_refusal_names_the_rule_and_says_the_direction():
    with pytest.raises(PolicyError, match="force-push.*BLOCK.*MANUAL"):
        validate_policy(_policy(**{"raise": {"force-push": "MANUAL"}}))


# --------------------------------------------------------------------------- controls

REPRESENTATIVE = [
    "rm -rf /tmp/data", "git push --force origin main", "git push origin feature-branch",
    "curl https://example.com/data", "python -m pytest -q", "ls -la", "", "DROP TABLE users;",
]


def test_CONTROLE_an_empty_policy_changes_no_verdict():
    """Control: the policy path is not a second classifier -- with nothing declared, every verdict,
    rule and reason is the built-in one."""
    empty = validate_policy(_policy())
    for command in REPRESENTATIVE:
        assert assess(command, empty) == assess(command), command


def test_CONTROLE_every_built_in_verdict_reports_its_source():
    for command in REPRESENTATIVE:
        assert assess(command)["source"] == "built-in", command


def test_CONTROLE_a_user_manual_rule_cannot_soften_a_built_in_block():
    """Control: BLOCK rules are tried before MANUAL rules whatever their origin, so a user MANUAL
    rule that also matches a destructive command never wins over the built-in BLOCK."""
    soft = validate_policy(_policy(rules=[{"id": "any-rm", "action": "MANUAL", "pattern": r"\brm\b",
                                           "reason": "look before deleting"}]))
    verdict = assess("rm -rf /tmp/data", soft)
    assert verdict["action"] == "BLOCK" and verdict["rule"] == "recursive-delete" and verdict["source"] == "built-in"
    assert assess("rm notes.txt", soft)["action"] == "MANUAL"


def test_CONTROLE_assess_still_reads_only_its_arguments(tmp_path, monkeypatch):
    """Design control: `assess` never opens `.hpp/policy.json` by itself; the CLI loads it and
    passes it in. A policy file in the cwd changes nothing for a direct call."""
    _write(tmp_path, _policy(rules=[BLOCK_RULE]))
    monkeypatch.chdir(tmp_path)
    assert assess("kubectl apply -f prod.yaml")["action"] == "ALLOW"


# --------------------------------------------------------------------------- the call site

def test_policy_check_reads_the_policy_file_of_the_workspace(tmp_path, monkeypatch, capsys):
    _write(tmp_path, _policy(rules=[BLOCK_RULE]))
    monkeypatch.chdir(tmp_path)
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "kubectl apply -f prod.yaml"])
    report = json.loads(capsys.readouterr().out)
    assert code == 2
    assert report["action"] == "BLOCK" and report["rule"] == "prod-deploy" and report["source"] == "policy"
    assert report["policy"].replace("\\", "/").endswith(".hpp/policy.json")


def test_policy_check_accepts_an_explicit_policy_path(tmp_path, monkeypatch, capsys):
    path = _write(tmp_path, _policy(**{"raise": {"external-push": "BLOCK"}}), name="team-policy.json")
    monkeypatch.chdir(tmp_path)
    code = cli.main(["policy", "check", "--mode", "enforce", "--policy", str(path),
                     "--command", "git push origin feature"])
    report = json.loads(capsys.readouterr().out)
    assert code == 2 and report["action"] == "BLOCK" and report["rule"] == "external-push"


def test_a_refused_policy_file_refuses_the_check_instead_of_falling_back(tmp_path, monkeypatch, capsys):
    """A project that declared a policy and got the built-ins instead would read ALLOW for the very
    command it wanted blocked. The check exits 2 with the reason, and prints no verdict."""
    _write(tmp_path, _policy(**{"raise": {"force-push": "MANUAL"}}))
    monkeypatch.chdir(tmp_path)
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "ls"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "force-push" in captured.err and "policy" in captured.err


def test_CONTROLE_without_a_policy_file_the_check_reports_none_and_the_built_in_verdict(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = cli.main(["policy", "check", "--mode", "enforce", "--command", "kubectl apply -f prod.yaml"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["action"] == "ALLOW" and report["policy"] is None


def test_load_policy_refuses_a_file_that_is_not_json(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicyError, match="JSON"):
        load_policy(path)
