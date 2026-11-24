"""Local administrator token login and role management; secrets never enter audit logs."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException

class AdminAuth:
    def __init__(self, root):
        self.path=Path(root)/'users.json'
        self.lock=threading.RLock()
        self.sessions={}
        self.attempts={}

    def users(self):
        return json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else []

    def write(self,users):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_name('users.'+secrets.token_hex(6)+'.tmp')
        try:
            temp.write_text(json.dumps(users,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp,self.path)
        finally:
            temp.unlink(missing_ok=True)

    def login(self,name,token,peer,roles=('admin',)):
        with self.lock:
            now=time.monotonic()
            self.attempts={k:v for k,v in self.attempts.items() if now-v[0]<300}
            started,count=self.attempts.get(peer,(now,0))
            if count>=5:raise HTTPException(429,'로그인 시도가 많습니다. 5분 후 다시 시도하세요.')
            hashed=hashlib.sha256(token.encode()).hexdigest()
            user=next((u for u in self.users() if u['name']==name and u['role'] in roles and u.get('active',True) and secrets.compare_digest(u['token_hash'],hashed)),None)
            if not user:
                self.attempts[peer]=(started,count+1)
                raise HTTPException(401,'아이디 또는 토큰이 올바르지 않습니다.')
            self.attempts.pop(peer,None)
            self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
            secret=secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(secret.encode()).hexdigest()]=dict(name=name,role=user['role'],token_hash=hashed,expires=now+28800)
            users=self.users()
            for stored in users:
                if stored['name']==name:stored['last_login_at']=datetime.now(timezone.utc).isoformat()
            self.write(users)
            return secret

    def session(self,secret):
        with self.lock:
            digest=hashlib.sha256(secret.encode()).hexdigest()
            session=self.sessions.get(digest)
            if not session:return None
            valid=session['expires']>time.monotonic() and any(u['name']==session['name'] and u['role']==session['role'] and u.get('active',True) and secrets.compare_digest(u['token_hash'],session['token_hash']) for u in self.users())
            if not valid:
                self.sessions.pop(digest,None)
                return None
            return dict(name=session['name'],role=session['role'])

    def logout(self,secret):
        with self.lock:self.sessions.pop(hashlib.sha256(secret.encode()).hexdigest(),None)

    def create(self,name,role,display_name=None):
        if not re.fullmatch(r'[A-Za-z0-9가-힣_-]{2,40}',name):raise HTTPException(422,'아이디는 2~40자의 한글·영문·숫자·밑줄·하이픈을 사용하세요.')
        if role not in ('writer','editor'):raise HTTPException(422,'작성자 또는 편집자 역할을 선택하세요.')
        with self.lock:
            users=self.users()
            if any(u['name']==name for u in users):raise HTTPException(409,'이미 사용 중인 아이디입니다.')
            token=secrets.token_urlsafe(32)
            users.append(dict(name=name,role=role,display_name=display_name or name,active=True,created_at=datetime.now(timezone.utc).isoformat(),token_hash=hashlib.sha256(token.encode()).hexdigest()))
            self.write(users)
            return dict(name=name,role=role,token=token)

    def profile(self,name,display_name,active):
        with self.lock:
            users=self.users()
            user=next((u for u in users if u['name']==name),None)
            if not user:raise HTTPException(404,'계정을 찾을 수 없습니다.')
            if user['role']=='admin':raise HTTPException(403,'관리자 계정은 이 화면에서 변경하지 않습니다.')
            user.update(display_name=display_name,active=active,updated_at=datetime.now(timezone.utc).isoformat())
            self.write(users)
            if not active:self.sessions={k:v for k,v in self.sessions.items() if v['name']!=name}
            return dict(name=name,display_name=display_name,active=active,role=user['role'])

    def rotate(self,name):
        with self.lock:
            users=self.users()
            user=next((u for u in users if u['name']==name),None)
            if not user:raise HTTPException(404,'계정을 찾을 수 없습니다.')
            if user['role']=='admin':raise HTTPException(403,'관리자 토큰은 이 화면에서 변경하지 않습니다.')
            if not user.get('active',True):raise HTTPException(409,'계정을 활성화한 뒤 토큰을 재발급하세요.')
            token=secrets.token_urlsafe(32)
            user.update(token_hash=hashlib.sha256(token.encode()).hexdigest(),token_rotated_at=datetime.now(timezone.utc).isoformat())
            self.write(users)
            self.sessions={k:v for k,v in self.sessions.items() if v['name']!=name}
            return dict(name=name,role=user['role'],token=token)

    def listing(self):
        with self.lock:
            return [dict(name=u['name'],role=u['role'],display_name=u.get('display_name',u['name']),active=u.get('active',True),created_at=u.get('created_at'),last_login_at=u.get('last_login_at'),token_rotated_at=u.get('token_rotated_at')) for u in self.users()]
