# Streamlit Community Cloud 배포 가이드

> 자체 Gitea → GitHub → Streamlit Community Cloud 순서로 배포합니다.
> 아래 명령어는 **본인 PC의 터미널(PowerShell/CMD)** 에서 실행하세요.
> (Cowork 샌드박스는 `.git`에 쓰기 권한이 없어 git 작업은 PC에서 직접 해야 합니다.)

---

## 0. 사전 준비 (이미 완료된 항목)

- [x] `.gitignore` 정비 — `.venv`, `__pycache__`, `.idea`, `.env`, `secrets.toml` 제외
- [x] `.streamlit/secrets.toml.example` 생성 — 클라우드에 붙여넣을 secrets 템플릿
- `database.py`는 `os.getenv()`를 쓰므로 **코드 수정 불필요**.
  Streamlit Cloud는 루트 레벨 secrets를 환경변수로 노출하므로 그대로 동작합니다.

---

## 1. git 인덱스 복구 + 커밋

```powershell
cd "C:\Users\son2\Desktop\Project\실시간모니터링\실시간 모니터링"

# (필요시) 잠긴 락 파일 제거 + 인덱스 재생성
del .git\index.lock
git reset

# .idea 추적 해제 + 변경사항 커밋
git rm -r --cached .idea
git add -A
git commit -m "Streamlit Cloud 배포 준비: .gitignore 정비, secrets 템플릿 추가, .idea 추적 제거"
```

---

## 2. GitHub 새 저장소 만들고 푸시

1. github.com 로그인 → **New repository** 클릭
2. 저장소 이름 예: `streamlit-mes-mon` / **Private** 권장 / README·gitignore 체크 안 함 → Create
3. 생성 후 나오는 주소(예: `https://github.com/<내아이디>/streamlit-mes-mon.git`)로 아래 실행:

```powershell
# 기존 Gitea remote는 origin 그대로 두고, GitHub를 github 라는 이름으로 추가
git remote add github https://github.com/<내아이디>/streamlit-mes-mon.git
git push -u github master
```

> 푸시 시 GitHub 로그인 창이 뜨면 계정/토큰으로 인증하세요.
> (비밀번호 대신 **Personal Access Token** 필요. GitHub → Settings → Developer settings → Tokens)

---

## 3. Streamlit Community Cloud 배포

1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인/연동
2. **Create app → Deploy a public app from GitHub** 선택
3. 입력:
   - Repository: `<내아이디>/streamlit-mes-mon`
   - Branch: `master`
   - Main file path: `app.py`
4. **Advanced settings → Secrets** 칸에 `.streamlit/secrets.toml.example` 내용을
   **실제 값으로 채워서** 붙여넣기. (섹션 `[ ]` 없이 평면 키 그대로!)

   ```toml
   DB_HOST = "ssonj11.tplinkdns.com"
   DB_PORT = "3306"
   DB_NAME = "kkimesdb"
   DB_USER = "실제_사용자명"
   DB_PASSWORD = "실제_비밀번호"
   MILL_CD = "0001"
   REFRESH_INTERVAL_MS = "10000"
   CACHE_TTL_SEC = "9"
   ```
5. **Deploy!** 클릭 → 빌드 로그 확인

---

## 4. 배포 후 점검 체크리스트

- [ ] 앱이 떴는데 DB 연결 에러가 뜨면 → **DB가 외부 인터넷에서 접속 가능한지** 확인
  - 라우터에서 `3306` 포트 포워딩 / 방화벽 허용
  - MariaDB 사용자가 외부 호스트(`'user'@'%'`)에서 접속 허용되는지 확인
  - (보안) Streamlit Cloud는 고정 IP가 없으므로, 가능하면 별도 읽기 전용 계정 사용 권장
- [ ] 페이지 하단의 `DB: ... · 사업장: ...` 표시가 올바른지 확인
- [ ] 자동 갱신(autorefresh)이 동작하는지 확인

---

## 참고: 보안 주의

- 공개(public) 앱으로 배포하면 **URL을 아는 누구나 대시보드를 볼 수 있습니다.**
  민감 데이터라면 Streamlit의 **인증 기능**(`[auth]`)이나 앱 내 비밀번호 게이트를 고려하세요.
- DB 비밀번호는 절대 코드/저장소에 넣지 말고 항상 Secrets로만 관리하세요.
