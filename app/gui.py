"""ReclipSubs 데스크톱 GUI (Tkinter).

탭 1: 음성/영상 -> 자막 (Whisper)
탭 2: 자막 파일 -> 원하는 형식으로 변환 (Whisper 불필요, 즉시)
"""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import core
from .subtitles import WRITERS, output_path, parse_subtitle_file

MEDIA_TYPES = [
    (
        "오디오/영상 파일",
        "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma "
        "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.flv",
    ),
    ("모든 파일", "*.*"),
]
SUBTITLE_TYPES = [
    ("자막/텍스트 파일", "*.srt *.vtt *.txt"),
    ("모든 파일", "*.*"),
]
FORMATS = ["srt", "vtt", "txt", "타임코드"]
DONE = "__DONE__"


def _fmt_size(n: int) -> str:
    mb = n / (1024 * 1024)
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def _file_picker(parent, treeview_height=5):
    """파일 리스트 위젯 + 추가/제거 버튼. (frame, get_files) 반환."""
    files: list[str] = []
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=("p",), show="tree", height=treeview_height)
    tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
    btns = ttk.Frame(frame)
    btns.pack(side="right", fill="y", padx=6, pady=6)

    def add(types):
        for p in filedialog.askopenfilenames(title="파일 선택", filetypes=types):
            if p not in files:
                files.append(p)
                tree.insert("", "end", text=p)

    def remove_sel():
        for item in tree.selection():
            p = tree.item(item, "text")
            if p in files:
                files.remove(p)
            tree.delete(item)

    def clear():
        files.clear()
        for item in tree.get_children():
            tree.delete(item)

    frame._add = add
    frame._remove = remove_sel
    frame._clear = clear
    frame._btns = btns
    return frame, files


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title("ReclipSubs — 음성 → 자막 변환기")
        root.geometry("840x680")
        root.minsize(740, 620)

        self.msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.transcribe_max = 0.0

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        t1 = ttk.Frame(nb)
        t2 = ttk.Frame(nb)
        nb.add(t1, text="  음성 → 자막  ")
        nb.add(t2, text="  자막 형식 변환  ")
        self._build_transcribe_tab(t1)
        self._build_convert_tab(t2)

        self.root.after(100, self._drain_queue)

    # ══════════════════ 탭 1: 음성 → 자막 ══════════════════
    def _build_transcribe_tab(self, root) -> None:
        pad = {"padx": 8, "pady": 4}
        ttk.Label(
            root,
            text="파일은 이 컴퓨터 안에서만 처리됩니다. 모델은 최초 1회만 내려받고 이후 재사용합니다.",
            foreground="#666",
        ).pack(anchor="w", padx=10, pady=(8, 0))

        ff = ttk.LabelFrame(root, text="1. 변환할 파일 (여러 개 가능)")
        ff.pack(fill="x", **pad)
        picker, self.files = _file_picker(ff)
        picker.pack(fill="both", expand=True)
        ttk.Button(picker._btns, text="파일 추가",
                   command=lambda: picker._add(MEDIA_TYPES)).pack(fill="x", pady=2)
        ttk.Button(picker._btns, text="선택 제거", command=picker._remove).pack(fill="x", pady=2)
        ttk.Button(picker._btns, text="전체 비우기", command=picker._clear).pack(fill="x", pady=2)

        opt = ttk.LabelFrame(root, text="2. 옵션")
        opt.pack(fill="x", **pad)

        ttk.Label(opt, text="속도/정확도").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.preset_var = StringVar(value="균형")
        for i, name in enumerate(core.PRESETS):
            ttk.Radiobutton(opt, text=name, value=name,
                            variable=self.preset_var).grid(row=0, column=1 + i, sticky="w", padx=4)
        ttk.Label(opt, text="(빠름=tiny · 균형=base · 정확=small)",
                  foreground="#888").grid(row=1, column=1, columnspan=4, sticky="w", padx=4)

        ttk.Label(opt, text="언어").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.lang_var = StringVar(value="자동 감지")
        ttk.Combobox(opt, textvariable=self.lang_var, values=list(core.LANGUAGES),
                     state="readonly", width=12).grid(row=2, column=1, sticky="w", padx=4)
        ttk.Label(opt, text="작업").grid(row=2, column=2, sticky="w", padx=6)
        self.task_var = StringVar(value="transcribe")
        ttk.Combobox(opt, textvariable=self.task_var, values=["transcribe", "translate"],
                     state="readonly", width=12).grid(row=2, column=3, sticky="w", padx=4)

        ttk.Label(opt, text="장치").grid(row=2, column=4, sticky="w", padx=6)
        self.device_var = StringVar(value="자동(CPU)")
        ttk.Combobox(opt, textvariable=self.device_var,
                     values=["자동(CPU)", "GPU(NVIDIA)"],
                     state="readonly", width=12).grid(row=2, column=5, sticky="w", padx=4)

        ttk.Label(opt, text="출력 형식").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.fmt_vars = {}
        for i, f in enumerate(FORMATS):
            v = BooleanVar(value=(f == "srt"))
            self.fmt_vars[f] = v
            ttk.Checkbutton(opt, text=f.upper() if f != "타임코드" else "타임코드",
                            variable=v).grid(row=3, column=1 + i, sticky="w")

        ttk.Button(opt, text="모델 관리…", command=self._manage_models).grid(
            row=0, column=6, rowspan=2, sticky="e", padx=8)

        out = ttk.LabelFrame(root, text="3. 저장 위치 (비우면 원본 파일과 같은 폴더)")
        out.pack(fill="x", **pad)
        self.outdir_var = StringVar(value="")
        ttk.Entry(out, textvariable=self.outdir_var).pack(
            side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(out, text="찾아보기",
                   command=lambda: self._browse_dir(self.outdir_var)).pack(side="right", padx=6, pady=6)

        run = ttk.Frame(root)
        run.pack(fill="x", **pad)
        self.run_btn = ttk.Button(run, text="변환 시작", command=self._start)
        self.run_btn.pack(side="left")
        self.cancel_btn = ttk.Button(run, text="취소", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        self.bar = ttk.Progressbar(run, mode="determinate", maximum=1000)
        self.bar.pack(side="left", fill="x", expand=True, padx=6)
        self.pct = ttk.Label(run, text="", width=5)
        self.pct.pack(side="left")

        lf = ttk.LabelFrame(root, text="진행 상황")
        lf.pack(fill="both", expand=True, **pad)
        self.log = ScrolledText(lf, height=10, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    # ══════════════════ 탭 2: 자막 형식 변환 ══════════════════
    def _build_convert_tab(self, root) -> None:
        pad = {"padx": 8, "pady": 4}
        ttk.Label(
            root,
            text="이미 만들어진 자막(.srt/.vtt/.txt)을 다른 형식으로 다시 저장합니다. Whisper·인터넷 불필요, 즉시.",
            foreground="#666",
        ).pack(anchor="w", padx=10, pady=(8, 0))

        ff = ttk.LabelFrame(root, text="1. 변환할 자막 파일")
        ff.pack(fill="x", **pad)
        picker, self.conv_files = _file_picker(ff)
        picker.pack(fill="both", expand=True)
        ttk.Button(picker._btns, text="파일 추가",
                   command=lambda: picker._add(SUBTITLE_TYPES)).pack(fill="x", pady=2)
        ttk.Button(picker._btns, text="선택 제거", command=picker._remove).pack(fill="x", pady=2)
        ttk.Button(picker._btns, text="전체 비우기", command=picker._clear).pack(fill="x", pady=2)

        opt = ttk.LabelFrame(root, text="2. 변환할 형식 (원하는 것 선택)")
        opt.pack(fill="x", **pad)
        self.conv_fmt_vars = {}
        for i, f in enumerate(FORMATS):
            v = BooleanVar(value=(f == "vtt"))
            self.conv_fmt_vars[f] = v
            ttk.Checkbutton(opt, text=f.upper() if f != "타임코드" else "타임코드",
                            variable=v).grid(row=0, column=i, sticky="w", padx=8, pady=6)
        ttk.Label(
            opt,
            text="※ 타임코드가 없는 .txt 를 넣으면 시간 정보 없는 자막이 됩니다.",
            foreground="#888",
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=8)

        out = ttk.LabelFrame(root, text="3. 저장 위치 (비우면 원본과 같은 폴더)")
        out.pack(fill="x", **pad)
        self.conv_outdir_var = StringVar(value="")
        ttk.Entry(out, textvariable=self.conv_outdir_var).pack(
            side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(out, text="찾아보기",
                   command=lambda: self._browse_dir(self.conv_outdir_var)).pack(side="right", padx=6, pady=6)

        run = ttk.Frame(root)
        run.pack(fill="x", **pad)
        self.conv_btn = ttk.Button(run, text="변환", command=self._convert)
        self.conv_btn.pack(side="left")

        lf = ttk.LabelFrame(root, text="결과")
        lf.pack(fill="both", expand=True, **pad)
        self.conv_log = ScrolledText(lf, height=12, wrap="word", state="disabled")
        self.conv_log.pack(fill="both", expand=True, padx=6, pady=6)

    def _convert(self) -> None:
        files = list(self.conv_files)
        if not files:
            messagebox.showwarning("파일 없음", "변환할 자막 파일을 추가하세요.")
            return
        fmts = [f for f, v in self.conv_fmt_vars.items() if v.get()]
        if not fmts:
            messagebox.showwarning("형식 없음", "변환할 형식을 하나 이상 선택하세요.")
            return
        outdir = self.conv_outdir_var.get().strip()

        self._conv_log_clear()
        ok = 0
        for src in files:
            src_p = Path(src)
            try:
                segs = parse_subtitle_file(src_p)
                if not segs:
                    self._conv_log_write(f"건너뜀 (내용 없음): {src_p.name}")
                    continue
                target_dir = Path(outdir) if outdir else src_p.parent
                target_dir.mkdir(parents=True, exist_ok=True)
                for f in fmts:
                    dst = output_path(target_dir, src_p.stem, f)
                    if dst.resolve() == src_p.resolve():
                        self._conv_log_write(f"건너뜀 (원본과 동일): {dst.name}")
                        continue
                    WRITERS[f](segs, dst)
                    self._conv_log_write(f"저장됨: {dst}")
                    ok += 1
            except Exception as e:  # noqa: BLE001
                self._conv_log_write(f"오류 ({src_p.name}): {e}")
        self._conv_log_write(f"\n완료 — {ok}개 파일 생성")

    # ══════════════════ 공통 ══════════════════
    def _browse_dir(self, var: StringVar) -> None:
        d = filedialog.askdirectory(title="저장 폴더 선택")
        if d:
            var.set(d)

    def _manage_models(self) -> None:
        dlg = _ModelDialog(self.root)
        self.root.wait_window(dlg.win)

    def _selected_formats(self) -> list[str]:
        return [f for f, v in self.fmt_vars.items() if v.get()]

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showwarning("파일 없음", "변환할 파일을 먼저 추가하세요.")
            return
        formats = self._selected_formats()
        if not formats:
            messagebox.showwarning("형식 없음", "출력 형식을 하나 이상 선택하세요.")
            return

        preset = core.PRESETS[self.preset_var.get()]
        self.cancel_event.clear()
        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.bar.config(value=0)
        self.pct.config(text="")
        self._log_clear()

        device = "cuda" if self.device_var.get().startswith("GPU") else "auto"
        self.worker = threading.Thread(
            target=self._run_worker,
            kwargs=dict(
                files=list(self.files),
                model_size=preset["model"],
                beam_size=preset["beam_size"],
                batch_size=preset["batch_size"],
                language=core.LANGUAGES.get(self.lang_var.get()),
                task=self.task_var.get(),
                device=device,
                formats=formats,
                outdir=self.outdir_var.get().strip() or None,
            ),
            daemon=True,
        )
        self.worker.start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self._enqueue(-1, "취소 요청됨… 현재 구간까지 마치고 중단합니다.")

    def _run_worker(self, files, model_size, beam_size, batch_size, language, task, device, formats, outdir):
        total = len(files)
        try:
            for idx, path in enumerate(files, start=1):
                if self.cancel_event.is_set():
                    break
                self._enqueue(-1, f"\n=== ({idx}/{total}) {Path(path).name} ===")
                self.transcribe_max = 0.0

                def on_progress(prog: float, message: str, _i=idx) -> None:
                    if prog >= 0:
                        self._enqueue(((_i - 1) + prog) / total, message)
                    else:
                        self._enqueue(-1, message)

                try:
                    written = core.transcribe_file(
                        path,
                        model_size=model_size,
                        language=language,
                        task=task,
                        beam_size=beam_size,
                        batch_size=batch_size,
                        device=device,
                        formats=formats,
                        outdir=outdir,
                        on_progress=on_progress,
                        should_cancel=self.cancel_event.is_set,
                    )
                    for w in written:
                        self._enqueue(-1, f"저장됨: {w}")
                except KeyboardInterrupt:
                    self._enqueue(-1, "중단됨.")
                    break
                except Exception as e:  # noqa: BLE001
                    self._enqueue(-1, f"오류: {e}")
                    self._enqueue(-1, traceback.format_exc())
        finally:
            self._enqueue(DONE, None)

    # ---------- 큐/로그 ----------
    def _enqueue(self, progress, message) -> None:
        self.msg_queue.put((progress, message))

    def _drain_queue(self) -> None:
        try:
            while True:
                progress, message = self.msg_queue.get_nowait()
                if progress == DONE:
                    self._on_done()
                    continue
                if isinstance(progress, (int, float)) and progress >= 0:
                    v = max(self.transcribe_max, float(progress))
                    self.transcribe_max = v
                    self.bar.config(value=v * 1000)
                    self.pct.config(text=f"{int(v * 100)}%")
                if message:
                    self._log_write(message)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _on_done(self) -> None:
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        if not self.cancel_event.is_set():
            self.bar.config(value=1000)
            self.pct.config(text="100%")
        self._log_write("\n작업이 끝났습니다.")

    def _log_clear(self) -> None:
        self._st_clear(self.log)

    def _log_write(self, text: str) -> None:
        self._st_write(self.log, text)

    def _conv_log_clear(self) -> None:
        self._st_clear(self.conv_log)

    def _conv_log_write(self, text: str) -> None:
        self._st_write(self.conv_log, text)

    @staticmethod
    def _st_clear(widget: ScrolledText) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.config(state="disabled")

    @staticmethod
    def _st_write(widget: ScrolledText, text: str) -> None:
        widget.config(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.config(state="disabled")


class _ModelDialog:
    """다운로드된 모델 목록/삭제."""

    def __init__(self, parent) -> None:
        self.win = Toplevel(parent)
        self.win.title("모델 관리")
        self.win.geometry("440x300")
        self.win.transient(parent)

        ttk.Label(self.win, text=f"저장 위치: {core.MODELS_DIR}",
                  foreground="#666", wraplength=410).pack(anchor="w", padx=10, pady=(10, 4))

        self.tree = ttk.Treeview(self.win, columns=("s",), show="headings", height=7)
        self.tree.heading("s", text="모델 / 용량")
        self.tree.column("s", width=400)
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        row = ttk.Frame(self.win)
        row.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(row, text="선택 삭제", command=self._delete).pack(side="left")
        ttk.Button(row, text="닫기", command=self.win.destroy).pack(side="right")
        self._refresh()

    def _refresh(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        models = core.downloaded_models()
        if not models:
            self.tree.insert("", "end", values=("(받은 모델 없음 — 변환 시 자동으로 받습니다)",))
            return
        for m in models:
            self.tree.insert("", "end", iid=m["size"],
                             values=(f"{m['size']}   ·   {_fmt_size(m['bytes'])}",))

    def _delete(self) -> None:
        sel = self.tree.selection()
        if not sel or sel[0] not in core.SUPPORTED_MODELS:
            return
        size = sel[0]
        if messagebox.askyesno("삭제", f"'{size}' 모델을 삭제할까요? (다음 사용 시 다시 받습니다)"):
            core.delete_model(size)
            self._refresh()


def main() -> None:
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
