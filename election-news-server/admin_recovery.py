"""Local administrator recovery with proof of possession; no anonymous reset."""
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from fastapi import HTTPException
from scripts.manage_admin_token import reset_token

class AdminRecovery:
    def __init__(self,auth):
        self.auth=auth
        self.root=auth.path.parent
        self.secret_path=self.root/'admin-recovery.json'
        self.guide=self.root/'admin-recovery.txt'
        self.attempts={}

    def issue_code(self):
        code=secrets.token_urlsafe(32)
        # The plaintext guide stays on the operator's PC; APIs never return the code.
        text='관리자 토큰 복구 코드\n\nrecovery: '+code+'\n\n관리자 로그인 화면의 토큰 재발급에서 복구 코드 확인을 선택하세요.\n이 코드는 외부에 공개하지 마세요. 토큰 재발급 후 새 코드로 바뀝니다.\n'
        digest=hashlib.sha256(code.encode()).hexdigest()
        guide_temp=self.guide.with_name(self.guide.name+'.'+secrets.token_hex(6)+'.tmp')
        hash_temp=self.secret_path.with_name(self.secret_path.name+'.'+secrets.token_hex(6)+'.tmp')
        try:
            guide_temp.write_text(text,encoding='utf-8-sig')
            hash_temp.write_text(json.dumps(dict(sha256=digest)),encoding='utf-8')
            os.replace(guide_temp,self.guide)
            os.replace(hash_temp,self.secret_path)
        finally:
            guide_temp.unlink(missing_ok=True);hash_temp.unlink(missing_ok=True)

    def ensure(self):
        with self.auth.lock:
            if self.secret_path.exists() and self.guide.exists():
                match=re.search(r'^recovery:[ \t]*(\S+)',self.guide.read_text(encoding='utf-8-sig'),re.MULTILINE)
                if match and secrets.compare_digest(hashlib.sha256(match.group(1).encode()).hexdigest(),json.loads(self.secret_path.read_text(encoding='utf-8'))['sha256']):return
            self.issue_code()

    def reset(self,name,verification,method,peer):
        with self.auth.lock:
            timestamp=time.monotonic()
            self.attempts={k:v for k,v in self.attempts.items() if timestamp-v[0]<300}
            start,count=self.attempts.get(peer,(timestamp,0))
            if count>=5:raise HTTPException(429,'복구 확인 시도가 많습니다. 5분 후 다시 시도하세요.')
            admin=next((u for u in self.auth.users() if u['name']==name and u['role']=='admin' and u.get('active',True)),None)
            expected=admin['token_hash'] if admin and method=='current_token' else None
            if admin and method=='recovery_code' and self.secret_path.exists():
                expected=json.loads(self.secret_path.read_text(encoding='utf-8'))['sha256']
            valid=bool(name=='admin' and expected and secrets.compare_digest(hashlib.sha256(verification.encode()).hexdigest(),expected))
            if not valid:
                self.attempts[peer]=(start,count+1)
                raise HTTPException(401,'아이디 또는 확인 정보가 올바르지 않습니다.')
            output_root=self.root.parent if self.root.name=='news' else self.root
            access=reset_token(output_root,accounts_path=self.auth.path)
            self.auth.sessions={k:v for k,v in self.auth.sessions.items() if v['role']!='admin'}
            self.auth.attempts.pop(peer,None)
            self.issue_code()
            self.attempts.pop(peer,None)
            token=re.search(r'^admin:[ \t]*(\S+)',access.read_text(encoding='utf-8-sig'),re.MULTILINE).group(1)
            return dict(name=name,token=token)
