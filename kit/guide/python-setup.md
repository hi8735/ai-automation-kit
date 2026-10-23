# Python 확인과 설치

엑셀(.xlsx) 파일을 읽고 만들거나, 많은 양을 똑같이 처리할 때 Python 이 필요하다. 문서·글 위주의 자동화에는 필요 없다. **필요할 때만** 설치하고, **반드시 본인 동의를 먼저 받는다.**

사용자에게는 이렇게 설명한다:
> "엑셀 파일을 다루려면 'Python' 이라는 무료 도구가 필요해요. 제가 설치해 드릴 수 있고 5분 정도 걸려요. 설치하는 동안 확인 창이 뜨면 '예' 를 눌러주시면 돼요. 회사 PC 라서 설치가 막혀 있으면 다른 방법으로 할게요. 설치해도 될까요?"

---

## Windows

### 있는지 확인하는 법
`python --version` 만 믿지 않는다. 윈도우는 Python 이 없을 때 **Microsoft Store 바로가기**가 대신 실행돼서, 아무것도 안 나오거나 "Python was not found" 가 나온다.

순서대로 확인:
1. `py --version` → `Python 3.x.x` 가 나오면 **있음**. 이후 명령은 `py` 로 실행한다.
2. `where python` → 경로가 `...\WindowsApps\python.exe` 하나뿐이면 **없음** (Store 바로가기).
3. `%LOCALAPPDATA%\Programs\Python\` 아래에 `Python3xx` 폴더가 있으면 설치는 되어 있는데 경로가 안 잡힌 것 → 그 안의 `python.exe` 를 직접 쓴다.

### 설치
```
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
```
- 사용자 범위 설치라 보통 관리자 권한이 필요 없다.
- `winget` 이 없다고 나오면 (오래된 윈도우 10): https://www.python.org/downloads/ 에서 내려받아 설치하도록 안내하고, 설치 첫 화면에서 **"Add python.exe to PATH" 체크**를 꼭 하라고 알려준다.
- 회사 정책으로 막히면 (권한 오류, 차단 메시지) **우회하지 않는다.** → 아래 "설치가 안 될 때" 로.

### 설치 직후 — 가장 흔한 함정
설치가 끝나도 **이미 열려 있는 창은 Python 을 못 찾는다.** 둘 중 하나:
- 바로 쓰기: 설치 경로의 python.exe 를 직접 호출
  `"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"` (Git Bash 에서는 `"$LOCALAPPDATA/Programs/Python/Python312/python.exe"`)
- 깔끔하게: 사용자에게 "Claude Code 를 한 번 껐다가 이 폴더에서 다시 열고 `/build` 를 쳐주세요. 하던 데서 이어서 할게요." (기록 파일이 있으므로 이어진다)

### 엑셀용 도구 설치
```
py -m pip install openpyxl pandas
```
(`py` 가 안 되면 위 python.exe 전체 경로 + `-m pip install openpyxl pandas`)

---

## Mac

### 있는지 확인하는 법
- `python3 --version` → 버전이 나오면 있음.
- "개발자 도구를 설치하시겠습니까?" 창이 뜨면 아직 없는 것. 그 창에서 설치를 진행해도 되고(10분 이상 걸릴 수 있음), https://www.python.org/downloads/ 에서 설치해도 된다.
- `brew` 가 있으면 `brew install python` 도 가능.

### 엑셀용 도구 설치
```
python3 -m pip install openpyxl pandas
```
"externally-managed-environment" 오류가 나면 `python3 -m pip install --user openpyxl pandas` 또는 키트 폴더 안에 가상환경을 만든다 (`python3 -m venv .venv` 후 `.venv/bin/pip install openpyxl pandas`).

---

## 한글 깨짐 방지

- 키트 설정에 `PYTHONUTF8=1` 이 들어 있다.
- 프로그램에서 파일을 열 때 항상 인코딩을 지정한다. 결과 CSV 는 `utf-8-sig` 로 저장해야 윈도우 엑셀에서 한글이 안 깨진다.
- 읽을 CSV 는 `utf-8-sig` 로 먼저 시도하고, 실패하면 `cp949` 로 다시 읽는다 (윈도우 엑셀이 만든 CSV).

## 설치가 안 될 때

- 억지로 우회하지 않는다 (보안 프로그램 끄기, 관리자 권한 요청 등 권하지 않는다).
- 대안: 엑셀에서 **"다른 이름으로 저장 → CSV UTF-8 (쉼표로 분리)"** 로 저장한 사본을 쓰면 Python 없이 읽을 수 있다. 결과도 CSV 나 글로 만들고, 사용자가 엑셀로 열면 된다.
- 기록과 리포트에 `python: 설치 실패` 와 이유(회사 PC 정책 등)를 남긴다. 진행자가 1:1 에서 볼 수 있다.
