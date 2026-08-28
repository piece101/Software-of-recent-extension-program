"""
로컬 Whisper 음성 -> 자막 변환 엔진 (faster-whisper / CTranslate2).

개선점
- 모델은 고정 폴더에 '한 번만' 다운로드하고 이후 모든 파일/실행에서 재사용
  (%LOCALAPPDATA%/ReclipSubs/models). 첫 변환 이후엔 인터넷 불필요.
- 같은 하드웨어에서 속도 향상: 모든 CPU 코어 사용 + INT8 양자화 +
  무음 구간 건너뛰기(VAD) + 배치 추론(BatchedInferencePipeline).
- NVIDIA GPU가 있으면 자동으로 CUDA 사용(없으면 CPU).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Iterable, Optional

from .subtitles import WRITERS, Segment, output_path

APP_NAME = "ReclipSubs"

# ── 모델 영구 저장 위치 ───────────────────────────────────────────────
_base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home())
MODELS_DIR = Path(_base) / APP_NAME / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

SUPPORTED_MODELS = ["tiny", "base", "small", "medium", "large-v3"]

# 속도 프리셋: model / beam_size / batch_size
PRESETS: dict[str, dict] = {
    "빠름":  {"model": "tiny",  "beam_size": 1, "batch_size": 16},
    "균형":  {"model": "base",  "beam_size": 1, "batch_size": 8},
    "정확":  {"model": "small", "beam_size": 5, "batch_size": 4},
}

LANGUAGES: dict[str, Optional[str]] = {
    "자동 감지": None,
    "한국어": "ko",
    "영어": "en",
    "일본어": "ja",
    "중국어": "zh",
    "스페인어": "es",
    "프랑스어": "fr",
    "독일어": "de",
    "러시아어": "ru",
}

# on_progress(progress: float 0~1 (음수=불확정), message: str)
ProgressCallback = Callable[[float, str], None]

_model_cache: dict[tuple, object] = {}


def _resolve_device(device: str, compute_type: Optional[str]) -> tuple[str, str]:
    # 환경변수로 강제 가능:  RECLIPSUBS_DEVICE = cpu | cuda | auto
    env = (os.environ.get("RECLIPSUBS_DEVICE") or "").strip().lower()
    if env in ("cpu", "cuda", "auto"):
        device = env

    # 'auto' 는 CPU 를 기본값으로 한다. GPU 는 CUDA 런타임(cuBLAS/cuDNN)이
    # 따로 설치돼 있어야 하는데 대부분의 PC 에는 없으므로, 명시적으로 'cuda'
    # 를 골랐을 때만 GPU 를 쓴다(그때도 실패하면 호출부에서 CPU 로 되돌린다).
    resolved = "cpu"
    if device == "cuda":
        try:
            import ctranslate2

            resolved = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            resolved = "cpu"
    if compute_type is None:
        compute_type = "float16" if resolved == "cuda" else "int8"
    return resolved, compute_type


def load_model(model_size: str, *, device: str = "auto", compute_type: Optional[str] = None):
    """WhisperModel 를 만들거나 캐시에서 재사용. 첫 호출 시 모델 다운로드."""
    from faster_whisper import WhisperModel

    resolved_device, resolved_ct = _resolve_device(device, compute_type)
    key = (model_size, resolved_device, resolved_ct)
    if key in _model_cache:
        return _model_cache[key], resolved_device, resolved_ct

    model = WhisperModel(
        model_size,
        device=resolved_device,
        compute_type=resolved_ct,
        download_root=str(MODELS_DIR),
        cpu_threads=os.cpu_count() or 4,
        num_workers=1,
    )
    _model_cache[key] = model
    return model, resolved_device, resolved_ct


def _run_transcribe(model, audio_path: str, *, batch_size: int, common: dict, vad_filter: bool):
    """배치 파이프라인을 우선 시도하고, 안 되면 일반 transcribe 로 폴백."""
    if batch_size and batch_size > 1:
        try:
            from faster_whisper import BatchedInferencePipeline

            batched = BatchedInferencePipeline(model=model)
            return batched.transcribe(audio_path, batch_size=batch_size, **common)
        except Exception:
            pass
    return model.transcribe(audio_path, vad_filter=vad_filter, **common)


def transcribe_file(
    input_path: str | os.PathLike,
    *,
    model_size: str = "base",
    language: Optional[str] = None,
    task: str = "transcribe",
    beam_size: int = 1,
    batch_size: int = 8,
    formats: Iterable[str] = ("srt",),
    outdir: Optional[str | os.PathLike] = None,
    device: str = "auto",
    compute_type: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> list[Path]:
    """오디오/영상 파일 1개를 변환해 요청한 형식으로 저장. 저장 경로 리스트 반환."""

    def log(msg: str, progress: float = -1.0) -> None:
        if on_progress:
            on_progress(progress, msg)

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {input_path}")

    formats = [f.lower() for f in formats]
    for f in formats:
        if f not in WRITERS:
            raise ValueError(f"지원하지 않는 출력 형식: {f}")

    out_dir = Path(outdir) if outdir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if not is_model_downloaded(model_size):
        log(f"모델 '{model_size}' 다운로드 중… (최초 1회, 이후 재사용)")

    common = dict(language=language, task=task, beam_size=beam_size)

    def _collect(dev_req: str, ct_req: Optional[str]) -> list[Segment]:
        model, dev, ct = load_model(model_size, device=dev_req, compute_type=ct_req)
        log(f"엔진 준비 완료 · {dev}/{ct} · {os.cpu_count()}스레드")
        seg_iter, info = _run_transcribe(
            model, str(input_path), batch_size=batch_size, common=common, vad_filter=True
        )
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        detected = getattr(info, "language", None)
        prob = float(getattr(info, "language_probability", 0.0) or 0.0)
        if language is None and detected:
            log(f"감지된 언어: {detected} ({prob:.0%})")

        log("음성 인식 중…")
        out: list[Segment] = []
        last_pct = -1
        for s in seg_iter:
            if should_cancel and should_cancel():
                raise KeyboardInterrupt
            text = (s.text or "").strip()
            if not text:
                continue
            out.append(Segment(len(out) + 1, s.start, s.end, text))
            if duration > 0:
                pct = int(min(s.end / duration, 0.999) * 100)
                if pct != last_pct:
                    last_pct = pct
                    log(f"음성 인식 {int(s.end)}s / {int(duration)}s", pct / 100)
        return out

    resolved_device, _ = _resolve_device(device, compute_type)
    try:
        segments = _collect(device, compute_type)
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001
        low = str(e).lower()
        gpu_err = any(k in low for k in ("cublas", "cudnn", "cuda", "libcu", "gpu"))
        if resolved_device == "cuda" and gpu_err:
            log("GPU(CUDA) 라이브러리를 불러오지 못했습니다 → CPU로 다시 시도합니다.")
            _model_cache.pop((model_size, "cuda", "float16"), None)
            segments = _collect("cpu", "int8")
        else:
            raise

    if not segments:
        raise RuntimeError("인식된 음성이 없습니다. 파일에 말소리가 있는지 확인하세요.")

    stem = input_path.stem
    written: list[Path] = []
    for f in formats:
        out_p = output_path(out_dir, stem, f)
        WRITERS[f](segments, out_p)
        written.append(out_p)

    log("완료!", 1.0)
    return written


# ── 모델 관리 ────────────────────────────────────────────────────────
def _model_repo_dirname(size: str) -> str:
    # huggingface_hub 캐시 규칙: models--<org>--<name>
    return f"models--Systran--faster-whisper-{size}"


def is_model_downloaded(size: str) -> bool:
    d = MODELS_DIR / _model_repo_dirname(size)
    if not d.is_dir():
        return False
    snap = d / "snapshots"
    return snap.is_dir() and any(snap.iterdir())


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def downloaded_models() -> list[dict]:
    out = []
    for size in SUPPORTED_MODELS:
        d = MODELS_DIR / _model_repo_dirname(size)
        if d.is_dir():
            out.append({"size": size, "bytes": _dir_size(d)})
    return out


def delete_model(size: str) -> bool:
    d = MODELS_DIR / _model_repo_dirname(size)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False
