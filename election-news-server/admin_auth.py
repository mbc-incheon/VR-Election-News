"""Local administrator token login and role management; secrets never enter audit logs."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
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

    def login(self,name,token,peer):
        with self.lock:
            now=time.monotonic()
            self.attempts={k:v for k,v in self.attempts.items() if now-v[0]<300}
            started,count=self.attempts.get(peer,(now,0))
            if count>=5:raise HTTPException(429,'로그인 시도가 많습니다. 5분 후 다시 시도하세요.')
            hashed=hashlib.sha256(token.encode()).hexdigest()
            user=next((u for u in self.users() if u['name']==name and u['role']=='admin' and secrets.compare_digest(u['token_hash'],hashed)),None)
            if not user:
                self.attempts[peer]=(started,count+1)
                raise HTTPException(401,'관리자 아이디 또는 토큰이 올바르지 않습니다.')
            self.attempts.pop(peer,None)
            self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
            secret=secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(secret.encode()).hexdigest()]=dict(name=name,role='admin',token_hash=hashed,expires=now+28800)
            return secret

    def session(self,secret):
        with self.lock:
            digest=hashlib.sha256(secret.encode()).hexdigest()
            session=self.sessions.get(digest)
            if not session:return None
            valid=session['expires']>time.monotonic() and any(u['name']==session['name'] and u['role']=='admin' and secrets.compare_digest(u['token_hash'],session['token_hash']) for u in self.users())
            if not valid:
                self.sessions.pop(digest,None)
                return None
            return dict(name=session['name'],role='admin')

    def logout(self,secret):
        with self.lock:self.sessions.pop(hashlib.sha256(secret.encode()).hexdigest(),None)

    def create(self,name,role):
        if not re.fullmatch(r'[A-Za-z0-9가-힣_-]{2,40}',name):raise HTTPException(422,'아이디는 2~40자의 한글·영문·숫자·밑줄·하이픈을 사용하세요.')
        if role not in ('writer','editor'):raise HTTPException(422,'작성자 또는 편집자 역할을 선택하세요.')
        with self.lock:
            users=self.users()
            if any(u['name']==name for u in users):raise HTTPException(409,'이미 사용 중인 아이디입니다.')
            token=secrets.token_urlsafe(32)
            users.append(dict(name=name,role=role,token_hash=hashlib.sha256(token.encode()).hexdigest()))
            self.write(users)
            return dict(name=name,role=role,token=token)
