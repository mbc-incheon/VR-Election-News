import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('admin_recovery',ROOT/'scripts/manage_admin_token.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
sys.path.insert(0,str(ROOT/'election-news-server'))
from admin_auth import AdminAuth

def setup_accounts(root):
    path=root/'news/users.json';path.parent.mkdir(parents=True)
    users=[dict(name='writer',role='writer',token_hash='TEST-writer-preserved'),dict(name='editor',role='editor',token_hash='TEST-editor-preserved'),dict(name='admin',role='admin',token_hash=hashlib.sha256(b'TEST-old-admin').hexdigest())]
    path.write_text(json.dumps(users),encoding='utf-8')
    (root/'admin-access.txt').write_text('admin: TEST-old-admin\n',encoding='utf-8-sig')
    return path,users

def test_recovery_invalidates_only_admin_and_saves_matching_utf8_token(tmp_path):
    path,before=setup_accounts(tmp_path)
    manager=AdminAuth(tmp_path/'news')
    session=manager.login('admin','TEST-old-admin','TEST-peer')
    assert manager.session(session)['role']=='admin'
    assert recovery.token_file_valid(tmp_path)
    output=recovery.reset_token(tmp_path)
    after=json.loads(path.read_text(encoding='utf-8'))
    assert before[:2]==after[:2]
    assert after[-1]['token_hash']!=before[-1]['token_hash']
    assert recovery.token_file_valid(tmp_path)
    assert manager.session(session) is None
    assert '관리자_토큰_관리.cmd' in output.read_text(encoding='utf-8-sig')
    assert not list(path.parent.glob('*.tmp'))
    output.write_text('admin: \n',encoding='utf-8')
    assert not recovery.token_file_valid(tmp_path)

def test_recovery_rolls_back_token_file_if_account_commit_fails(tmp_path,monkeypatch):
    path,_=setup_accounts(tmp_path)
    users_before=path.read_bytes();access=tmp_path/'admin-access.txt';access_before=access.read_bytes()
    original=recovery.os.replace
    def replace(source,target):
        if Path(target)==path:raise OSError('TEST simulated write failure')
        return original(source,target)
    monkeypatch.setattr(recovery.os,'replace',replace)
    with pytest.raises(OSError):recovery.reset_token(tmp_path)
    assert path.read_bytes()==users_before
    assert access.read_bytes()==access_before
    assert recovery.token_file_valid(tmp_path)
    assert not list(path.parent.glob('*.tmp'))

def test_recovery_refuses_missing_admin_without_creating_accounts(tmp_path):
    with pytest.raises(ValueError):recovery.reset_token(tmp_path)
    assert not (tmp_path/'news/users.json').exists()
