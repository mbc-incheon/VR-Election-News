"""Interactive local administrator recovery. Never prints a plaintext token."""
import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]

def account(root,accounts_path=None):
    path=Path(accounts_path) if accounts_path else Path(root)/'news/users.json'
    if not path.exists():raise ValueError('계정 파일이 없습니다. 먼저 setup.ps1로 시스템을 설치하세요.')
    users=json.loads(path.read_text(encoding='utf-8-sig'))
    admin=next((u for u in users if u.get('name')=='admin' and u.get('role')=='admin'),None)
    if not admin:raise ValueError('관리자 계정이 없습니다. scripts/init_users.py --add-admin으로 먼저 발급하세요.')
    return path,users,admin

def token_file_valid(root,accounts_path=None):
    _,_,admin=account(root,accounts_path)
    path=Path(root)/'admin-access.txt'
    if not path.exists():return False
    match=re.search(r'^admin:[ \t]*(\S+)',path.read_text(encoding='utf-8-sig'),re.MULTILINE)
    return bool(match and secrets.compare_digest(hashlib.sha256(match.group(1).encode()).hexdigest(),admin['token_hash']))

def reset_token(root,accounts_path=None):
    root=Path(root)
    path,users,admin=account(root,accounts_path)
    token=secrets.token_urlsafe(32)
    admin['token_hash']=hashlib.sha256(token.encode()).hexdigest()
    admin['token_rotated_at']=datetime.now(timezone.utc).isoformat()
    access=root/'admin-access.txt'
    message='관리자 로그인 안내\n\n아이디: admin\nadmin: '+token+'\n\nadmin: 뒤의 문자열만 토큰 칸에 입력하세요.\n로그인: http://127.0.0.1:8202/admin/login\n\n로그인 세션은 최대 8시간이며, 만료 시 이 토큰으로 다시 로그인하세요.\n토큰 재발급이 필요하면 프로젝트 폴더의 관리자_토큰_관리.cmd를 실행하세요.\n토큰을 공개하거나 GitHub에 올리지 마세요.\n'
    user_temp=path.with_name('users.recovery-'+secrets.token_hex(6)+'.tmp')
    access_temp=access.with_name('admin-access-'+secrets.token_hex(6)+'.tmp')
    old_access=access.read_bytes() if access.exists() else None
    try:
        user_temp.write_text(json.dumps(users,ensure_ascii=False,indent=2),encoding='utf-8')
        access_temp.write_text(message,encoding='utf-8-sig')
        os.replace(access_temp,access)
        try:os.replace(user_temp,path)
        except Exception:
            if old_access is None:access.unlink(missing_ok=True)
            else:access.write_bytes(old_access)
            raise
    finally:
        user_temp.unlink(missing_ok=True);access_temp.unlink(missing_ok=True)
    if not token_file_valid(root,accounts_path):raise ValueError('발급 결과 확인에 실패했습니다. 다시 실행하세요.')
    return access

def open_file(path):
    if os.name!='nt':raise ValueError('자동 열기는 Windows에서 지원합니다. 안내 파일을 직접 여세요.')
    subprocess.Popen(['notepad.exe',str(Path(path).resolve())])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=PROJECT/'runtime')
    parser.add_argument('--check',action='store_true',help='Validate saved token without revealing it')
    args=parser.parse_args()
    if args.check:
        if not token_file_valid(args.root):raise ValueError('안내 파일의 토큰이 없거나 현재 계정과 일치하지 않습니다.')
        print('안내 파일의 관리자 토큰이 현재 계정과 일치합니다.');return
    print('\nVR 선거보도 시스템 · 관리자 토큰 관리\n')
    print('로그인만 만료됐다면 토큰을 다시 발급할 필요가 없습니다.')
    print('1. 기존 관리자 토큰 안내 파일 열기 (권장)')
    print('2. 관리자 토큰 새로 발급 후 안내 파일 열기')
    print('0. 종료\n')
    choice=input('번호를 입력하세요 [1]: ').strip() or '1'
    if choice=='0':return
    if choice=='1':
        if not token_file_valid(args.root):raise ValueError('안내 파일의 토큰이 없거나 일치하지 않습니다. 파일을 다시 실행해 2번을 선택하세요.')
        open_file(args.root/'admin-access.txt');return
    if choice!='2':raise ValueError('0, 1, 2 중 하나를 선택하세요.')
    print('\n재발급하면 기존 관리자 토큰과 관리자 로그인 세션이 만료됩니다.')
    print('작성자·편집자 계정과 토큰은 유지됩니다.')
    if input('진행하려면 재발급 을 입력하세요: ').strip()!='재발급':
        print('취소했습니다.');return
    access=reset_token(args.root)
    print('재발급을 완료했습니다. 열린 안내 파일에서 새 토큰을 확인하세요.')
    open_file(access)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,StopIteration) as error:
        print('\n처리하지 못했습니다: '+str(error))
        raise SystemExit(1)
