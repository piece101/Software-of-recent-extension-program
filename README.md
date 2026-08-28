# ReclipSubs

크롬 확장 [Extension-program-Of-Audio-to-text-file](https://github.com/piece101/Extension-program-Of-Audio-to-text-file) 과
**같은 기능(음성 → SRT/VTT/TXT 자막)** 을 하는 **Windows 설치형 프로그램**입니다.
브라우저 없이 독립 실행되고, 엔진을 `faster-whisper`(CTranslate2)로 바꿔 **훨씬 빠릅니다.**

- 완전 오프라인 · 무료 · 파일이 외부로 나가지 않음
- 모델은 **최초 1회만** 내려받아 이후 모든 파일·모든 실행에서 재사용
- 한국어·영어 등 다국어 + 자동 언어 감지, 여러 파일 일괄 변환
- 변환 완료 시 자막 파일 자동 저장

---

## 일반 사용자 — 설치해서 쓰기

1. 이 저장소의 **[Releases](../../releases)** 탭으로 이동
2. 최신 버전의 **`ReclipSubs-Setup-x.y.z.exe`** 다운로드
3. 실행 → 설치 (관리자 권한 불필요, 시작 메뉴에 등록됨)
4. **ReclipSubs** 실행 → 파일 추가 → 속도/언어/형식 선택 → **변환 시작**
5. 완료되면 원본 파일 옆(또는 지정 폴더)에 `이름.srt` 등이 저장됩니다

> **첫 변환 때 한 번만** Whisper 모델을 내려받습니다
> (빠름 ≈ 75MB · 균형 ≈ 145MB · 정확 ≈ 480MB).
> 저장 위치: `%LOCALAPPDATA%\ReclipSubs\models` — 이후엔 인터넷 없이 동작합니다.
> 앱의 **모델 관리…** 에서 받은 모델 확인·삭제 가능.

Windows 10/11 64비트. 별도 런타임(Python·ffmpeg) 설치 불필요.

---

## 확장 대비 개선점

| # | 개선 | 방법 |
|---|------|------|
| 1 | 파일마다 모델을 다시 받지 않음 | 고정 폴더(`%LOCALAPPDATA%\ReclipSubs\models`)에 1회 저장 후 재사용 |
| 2 | 같은 하드웨어에서 더 빠름 | `faster-whisper`(C++·CTranslate2) + **전 CPU 코어** + INT8 양자화 + **무음 건너뛰기(VAD)** + **배치 추론** |
| 3 | 추가 요금 0 / 사양 그대로 | 위 방식 모두 로컬·무료. NVIDIA GPU가 있으면 자동으로 CUDA 사용(선택) |

체감 속도: 브라우저(WASM) 대비 CPU만으로도 보통 5~15배.

**속도 프리셋**

| 프리셋 | 모델 | beam | batch | 용도 |
|--------|------|------|-------|------|
| 빠름 | tiny | 1 | 16 | 빠른 초안 |
| 균형 | base | 1 | 8 | 기본값 |
| 정확 | small | 5 | 4 | 정확도 우선 |

---

## 유지보수자 — 설치본(.exe) 만들기

`.exe` 는 **GitHub Actions 가 자동으로 빌드**합니다. 태그만 올리면 됩니다.

```bash
git tag v0.1.0
git push origin v0.1.0
```

→ `.github/workflows/build.yml` 이 실행되어 PyInstaller + Inno Setup 으로
`ReclipSubs-Setup-0.1.0.exe` 를 만들고 **Releases 에 첨부**합니다.
(수동 실행: Actions 탭 → build-installer → Run workflow)

### 로컬에서 직접 빌드 (선택)

필요: Python 3.10~3.12, [Inno Setup 6](https://jrsoftware.org/isdl.php)
(`winget install -e --id JRSoftware.InnoSetup`)

```bat
build.bat
```

→ `packaging\installer_out\ReclipSubs-Setup-0.1.0.exe`

### 개발 중 실행 (빌드 없이)

```bash
pip install -r requirements.txt
python -m app
```

---

## 구조

```
run.py                      PyInstaller 진입점
app/
  core.py                   변환 엔진 (faster-whisper, 모델 캐시, 배치/VAD/멀티코어)
  gui.py                    Tkinter GUI + 모델 관리 대화상자
  subtitles.py              SRT / VTT / TXT 작성
assets/icon.ico             앱 아이콘
packaging/
  app.spec                  PyInstaller 설정 (onedir)
  installer.iss             Inno Setup 스크립트
build.bat                   로컬 빌드
.github/workflows/build.yml  태그 푸시 시 설치본 자동 빌드 → Release
```

## 라이선스

MIT (이 저장소 코드). Whisper 모델·faster-whisper·CTranslate2 는 각각 MIT.
