"""Issue local demo credentials. Plaintext is printed once, never saved."""
import hashlib,json,secrets
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('--root',default='runtime/news');p.add_argument('--add-admin',action='store_true');args=p.parse_args()
root=Path(args.root);root.mkdir(parents=True,exist_ok=True)
target=root/'users.json'
if target.exists() and not args.add_admin:raise SystemExit('users.json exists. Existing credentials preserved.')
users=json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else []
if args.add_admin and any(u['name']=='admin' for u in users):raise SystemExit('admin exists. Existing credentials preserved.')
accounts=[('admin','admin')] if args.add_admin else [('writer','writer'),('editor','editor'),('admin','admin')]
for name,role in accounts:
    token=secrets.token_urlsafe(24)
    users.append(dict(name=name,role=role,token_hash=hashlib.sha256(token.encode()).hexdigest()))
    print(f'{name}: {token}')
target.write_text(json.dumps(users),encoding='utf-8')
print('로컬 개발용 토큰입니다. 서로 다른 담당자에게 전달하고 외부 공개 서버에서 사용하지 마세요.')
