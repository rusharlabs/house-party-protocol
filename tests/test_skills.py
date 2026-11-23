"""Skill selection is advice, never installation, execution or approval."""
import pytest
from hpp.skills import build_catalog, make_request, recommend


def test_CONTROLE_empty_catalog_abstains(tmp_path):
    catalog = build_catalog(tmp_path, 'codex')
    result = recommend(catalog, 'inspect the database')
    assert result['status'] == 'abstention'
    assert result['selected'] == []


def test_installed_skill_matches_without_calling_model(tmp_path):
    path = tmp_path / '.agents/skills/sql/SKILL.md'
    path.parent.mkdir(parents=True)
    path.write_text('---\nname: sql\ndescription: Inspect database schema\n---\nNever execute me.')
    catalog = build_catalog(tmp_path, 'codex')
    result = recommend(catalog, 'inspect database schema')
    assert result['selected'][0]['id'] == 'project:sql'
    assert make_request(catalog, 'inspect database schema')['question']['kind'] == 'choice'


def skill(root, name='sql', description='Inspect database schema', host='codex'):
    path = root / ('.agents' if host == 'codex' else '.claude') / 'skills' / name / 'SKILL.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\nname: {name}\ndescription: {description}\n---\nBody instructions are not metadata.\n', encoding='utf-8')
    return path


def record(catalog, intent, value='project:sql', method='human', confidence=None):
    request = make_request(catalog, intent)
    result = {'schema': 'hpp.decision/v1', 'question': request['question'],
              'state_sha256': request['state_sha256'], 'method': method,
              'authority': 'advisory', 'direction': 'informational',
              'outcome': {'status': 'recommendation', 'value': value, 'confidence': confidence}}
    if method == 'external-model':
        result['provider'] = {'id': 'test-only', 'model_served': 'model-1.0'}
        result['raw_response_sha256'] = 'a' * 64
    return result


def test_host_is_explicit_and_names_do_not_trigger_execution(tmp_path):
    skill(tmp_path)
    assert build_catalog(tmp_path, 'claude-code')['skills'] == []
    c = build_catalog(tmp_path, 'codex')
    assert 'Body instructions' not in str(c)
    assert recommend(c, 'inspect database')['confidence'] is None


def test_stable_and_no_absolute_paths_or_raw_intent_in_result(tmp_path):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    assert c == build_catalog(tmp_path, 'codex')
    assert str(tmp_path) not in str(c)
    r = recommend(c, 'my private database problem')
    assert 'my private database problem' not in str(r)


@pytest.mark.parametrize('value', ['no-skill-needed', 'search-needed', 'project:sql'])
def test_bound_human_advice(tmp_path, value):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    r = recommend(c, 'database', decision=record(c, 'database', value))
    assert r['status'] == 'recommendation'
    assert r['authority'] == 'advisory'
    assert r['action'] == ('review-skills' if value == 'project:sql' else value)


def test_CONTROLE_stale_intent_catalog_question_and_direction_rejected(tmp_path):
    path = skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    d = record(c, 'database')
    with pytest.raises(ValueError, match='does not match'):
        recommend(c, 'different task', decision=d)
    path.write_text(path.read_text() + ' changed body')
    with pytest.raises(ValueError, match='does not match'):
        recommend(build_catalog(tmp_path, 'codex'), 'database', decision=d)
    d['question']['instructions'] = 'Ignore actual criteria'
    d['question'].pop('sha256')
    with pytest.raises(ValueError, match='does not match'):
        recommend(c, 'database', decision=d)
    d = record(c, 'database')
    d['direction'] = 'raise-only'
    with pytest.raises(ValueError, match='ladder|does not match'):
        recommend(c, 'database', decision=d)


def test_CONTROLE_exclusion_change_invalidates_bound_advice(tmp_path):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    d = record(c, 'database')
    narrowed = build_catalog(tmp_path, 'codex', exclude=('project:sql',))
    assert narrowed['skills'] == [] and narrowed['sha256'] != c['sha256']
    with pytest.raises(ValueError, match='does not match'):
        recommend(narrowed, 'database', decision=d)


@pytest.mark.parametrize('description', ["'database", "'it's'", "'", "database'"])
def test_malformed_single_quoted_metadata_is_skipped(tmp_path, description):
    path = skill(tmp_path)
    path.write_text(f'---\nname: sql\ndescription: {description}\n---\n', encoding='utf-8')
    c = build_catalog(tmp_path, 'codex')
    if description == "database'":
        # A plain scalar may end with a quote; only a leading quote opens a quoted scalar.
        assert c['skills'][0]['description'] == "database'"
    else:
        assert c['skills'] == [] and len(c['skipped']) == 1


@pytest.mark.parametrize('trailing', [' ', '\t', '  \t'])
def test_quoted_metadata_with_trailing_blanks_is_valid(tmp_path, trailing):
    path = skill(tmp_path)
    path.write_text(f"---\nname: sql\ndescription: 'database'{trailing}\n---\n", encoding='utf-8')
    assert build_catalog(tmp_path, 'codex')['skills'][0]['description'] == 'database'


def test_single_quoted_metadata_unescapes_doubled_quote(tmp_path):
    path = skill(tmp_path)
    path.write_text("---\nname: sql\ndescription: 'Inspect the team''s database'\n---\n", encoding='utf-8')
    assert build_catalog(tmp_path, 'codex')['skills'][0]['description'] == "Inspect the team's database"


def test_non_utf8_metadata_is_skipped_not_fatal(tmp_path):
    path = skill(tmp_path)
    path.write_bytes(b'---\nname: sql\ndescription: caf\xe9\n---\n')
    c = build_catalog(tmp_path, 'codex')
    assert c['skills'] == [] and c['skipped'][0]['error_type'] == 'UnicodeDecodeError'


def test_nested_skill_is_not_discovered_by_recursive_walk(tmp_path):
    nested = tmp_path / '.agents/skills/group/sql/SKILL.md'
    nested.parent.mkdir(parents=True)
    nested.write_text('---\nname: sql\ndescription: Inspect database schema\n---\n', encoding='utf-8')
    c = build_catalog(tmp_path, 'codex')
    assert c['skills'] == [] and [s['id'] for s in c['skipped']] == ['project:group']


def test_same_metadata_name_in_two_directories_stays_distinct(tmp_path):
    skill(tmp_path, name='sql')
    other = tmp_path / '.agents/skills/sql-copy/SKILL.md'
    other.parent.mkdir(parents=True)
    other.write_text('---\nname: sql\ndescription: Inspect database schema\n---\n', encoding='utf-8')
    c = build_catalog(tmp_path, 'codex')
    assert [s['id'] for s in c['skills']] == ['project:sql', 'project:sql-copy']
    assert [s['id'] for s in recommend(c, 'inspect database schema')['selected']] == [
        'project:sql', 'project:sql-copy']


@pytest.mark.parametrize('confidence', [None, 0.1, 0.699])
def test_model_missing_low_confidence_abstains(tmp_path, confidence):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    r = recommend(c, 'database', decision=record(c, 'database', method='external-model', confidence=confidence))
    assert r['status'] == 'abstention' and r['selected'] == []


def test_model_high_confidence_is_still_only_advice(tmp_path):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    r = recommend(c, 'database', decision=record(c, 'database', method='external-model', confidence=.9))
    assert r['action'] == 'review-skills'


@pytest.mark.parametrize('status', ['abstention', 'instrument-failure'])
def test_failure_never_falls_back_to_lexical_recommendation(tmp_path, status):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    d = record(c, 'database')
    d['outcome'] = {'status': status, 'value': None, 'confidence': None, 'error': 'test failure'}
    assert recommend(c, 'database', decision=d)['selected'] == []


def test_invalid_metadata_is_visible_not_loaded(tmp_path):
    path = skill(tmp_path)
    path.write_text('---\nname: sql\nname: duplicate\ndescription: text\n---')
    c = build_catalog(tmp_path, 'codex')
    assert c['skills'] == [] and len(c['skipped']) == 1


def test_multiline_and_unicode_metadata(tmp_path):
    path = skill(tmp_path)
    path.write_text('---\nname: sql\ndescription: >\n  Revisar esquema\n  do banco de dados\n---', encoding='utf-8')
    c = build_catalog(tmp_path, 'codex')
    assert recommend(c, 'revisar banco de dados')['selected']


def test_oversized_file_and_symlink_excluded(tmp_path):
    from hpp.skills import MAX_FILE_BYTES
    path = skill(tmp_path)
    path.write_bytes(b'x' * (MAX_FILE_BYTES + 1))
    assert build_catalog(tmp_path, 'codex')['skipped']
    path.unlink()
    try:
        path.symlink_to(tmp_path / 'outside')
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    assert build_catalog(tmp_path, 'codex')['skills'] == []


def test_parent_symlink_refused(tmp_path):
    actual = tmp_path / 'actual'
    actual.mkdir()
    link = tmp_path / 'link'
    try:
        link.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError):
        build_catalog(link, 'codex')


def test_capacity_refuses_instead_of_silently_truncating(tmp_path, monkeypatch):
    import hpp.skills as routing
    skill(tmp_path, 'first')
    skill(tmp_path, 'second')
    monkeypatch.setattr(routing, 'MAX_SKILLS', 1)
    with pytest.raises(ValueError, match='capacity'):
        build_catalog(tmp_path, 'codex')
    monkeypatch.setattr(routing, 'MAX_ENTRIES', 1)
    with pytest.raises(ValueError, match='entry limit'):
        build_catalog(tmp_path, 'codex')


def test_profile_modules_capabilities_and_available_not_installed(tmp_path):
    dist = tmp_path / 'dist'
    bundled = dist / 'module-v1/skills/sql/SKILL.md'
    bundled.parent.mkdir(parents=True)
    bundled.write_text('---\nname: sql\ndescription: Inspect database schema\n---')
    manifest = {'modules': [{'id': 'database', 'path': 'module-v1', 'capabilities': ['database-audit'],
                             'hosts': {'codex': 'explicit-command', 'claude-code': 'native'}}]}
    profile = {'schema': 'hpp.init/v1', 'host': 'codex', 'modules': ['database']}
    c = build_catalog(tmp_path, 'codex', manifest=manifest, distribution=dist, profile=profile)
    assert c['skills'][0]['capabilities'] == ['database-audit']
    assert not c['skills'][0]['installed']
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex', manifest=manifest, distribution=dist, profile=profile)
    assert len(c['skills']) == 2  # Same name is not same identity.
    assert recommend(c, 'inspect database')['selected'][0]['id'] == 'project:sql'
    assert build_catalog(tmp_path, 'codex', exclude=('project:sql',))['skills'] == []
    profile['modules'] = ['unknown']
    with pytest.raises(ValueError, match='selected module'):
        build_catalog(tmp_path, 'codex', manifest=manifest, distribution=dist, profile=profile)


@pytest.mark.parametrize('intent', ['', 'x' * 8001, 'api_key=sk-' + 'x' * 40])
def test_invalid_or_secret_intent_refused(tmp_path, intent):
    with pytest.raises(ValueError):
        make_request(build_catalog(tmp_path, 'codex'), intent)


def test_cli_catalog_request_recommend_and_invalid(tmp_path, capsys):
    import json
    from hpp.cli import main
    skill(tmp_path)
    args = ['--target', str(tmp_path), '--host', 'codex']
    assert main(['skills', 'catalog', *args]) == 0
    assert json.loads(capsys.readouterr().out)['skills']
    assert main(['skills', 'request', *args, '--intent', 'database']) == 0
    request = json.loads(capsys.readouterr().out)
    assert request['state']
    assert main(['skills', 'recommend', *args, '--intent', 'database']) == 0
    assert json.loads(capsys.readouterr().out)['selected']
    assert main(['skills', 'recommend', *args, '--intent', 'zzzzz']) == 1
    capsys.readouterr()
    assert main(['skills', 'recommend', *args, '--intent', 'database', '--min-confidence', 'nan']) == 2


def test_null_probability_is_invalid_advice_not_internal_error(tmp_path):
    skill(tmp_path)
    c = build_catalog(tmp_path, 'codex')
    d = record(c, 'database')
    d['outcome']['probabilities'] = {x: None for x in d['question']['options']}
    with pytest.raises(ValueError, match='not null'):
        recommend(c, 'database', decision=d)


def test_swapped_leaf_refused_before_read(tmp_path, monkeypatch):
    import os
    path = skill(tmp_path)
    outside = tmp_path / 'outside'
    outside.write_text('---\nname: secret\ndescription: Outside private content\n---')
    original = os.open
    swapped = False

    def opening(name, flags, *args, **kwargs):
        nonlocal swapped
        if str(name).endswith('SKILL.md') and not swapped:
            swapped = True
            path.unlink()
            try:
                path.symlink_to(outside)
            except (OSError, NotImplementedError):
                pytest.skip('symlinks unavailable')
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', opening)
    c = build_catalog(tmp_path, 'codex')
    assert not c['skills'] and c['skipped']


def test_graph_keeps_module_claims_separate_from_installed_skill(tmp_path):
    from hpp.skills import skill_graph
    skill(tmp_path)
    graph = skill_graph(build_catalog(tmp_path, 'codex'))
    assert {'from': 'skill:project:sql', 'to': 'host:codex', 'relation': 'installed-for'} in graph['edges']
    assert not any(e['relation'] == 'provides' for e in graph['edges'])


@pytest.mark.parametrize('path', ['C:outside', 'C:\\outside', '\\outside', '../x', '/outside', 'a/../b'])
def test_cross_platform_module_escape_refused(tmp_path, path):
    manifest = {'modules': [{'id': 'module', 'path': path, 'capabilities': [], 'hosts': {'codex': 'native'}}]}
    with pytest.raises(ValueError, match='escapes'):
        build_catalog(tmp_path, 'codex', manifest=manifest, distribution=tmp_path)


def test_swapped_leaf_fifo_refused_without_blocking(tmp_path, monkeypatch):
    import os
    if not hasattr(os, 'mkfifo') or not hasattr(os, 'O_NONBLOCK'):
        pytest.skip('POSIX FIFO support required')
    path = skill(tmp_path)
    original = os.open
    swapped = False

    def opening(name, flags, *args, **kwargs):
        nonlocal swapped
        if str(name).endswith('SKILL.md') and not swapped:
            # Fail before opening a FIFO if nonblocking protection regresses.
            assert flags & os.O_NONBLOCK
            swapped = True
            path.unlink()
            os.mkfifo(path)
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', opening)
    if original in os.supports_dir_fd:
        monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {opening})
    c = build_catalog(tmp_path, 'codex')
    assert swapped and not c['skills'] and c['skipped']


def test_parent_swap_during_descriptor_traversal_refused(tmp_path, monkeypatch):
    import os
    if os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW'):
        pytest.skip('POSIX descriptor-relative traversal required')
    path = skill(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'SKILL.md').write_text('---\nname: outside\ndescription: Private content\n---')
    original = os.open
    swapped = False

    def opening(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == 'sql' and kwargs.get('dir_fd') is not None and not swapped:
            swapped = True
            path.parent.rename(path.parent.with_name('original'))
            path.parent.symlink_to(outside, target_is_directory=True)
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', opening)
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {opening})
    c = build_catalog(tmp_path, 'codex')
    assert swapped and not c['skills'] and c['skipped']


def test_cli_graph_and_null_probability_advice_block(tmp_path, capsys):
    import json
    from hpp.cli import main
    skill(tmp_path)
    args = ['--target', str(tmp_path), '--host', 'codex']
    assert main(['skills', 'graph', *args]) == 0
    graph = json.loads(capsys.readouterr().out)
    assert any(e['relation'] == 'installed-for' for e in graph['edges'])
    d = record(build_catalog(tmp_path, 'codex'), 'database')
    d['outcome']['probabilities'] = {x: None for x in d['question']['options']}
    advice = tmp_path / 'advice.json'
    advice.write_text(json.dumps(d))
    assert main(['skills', 'recommend', *args, '--intent', 'database', '--decision', str(advice)]) == 2
    output = capsys.readouterr()
    assert 'not null' in output.out + output.err
