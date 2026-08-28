"""ReclipSubs 데스크톱 GUI (Tkinter)."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import core

AUDIO_VIDEO_TYPES = [
    (
        "오디오/영상 파일",
        "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma "
        "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.flv",
    ),
    ("모든 파일", "*.*"),
]
DONE = "__DONE__"


def _fmt_size(n: int) -> str:
    mb = n / (1024 * 1024)
    return f"{mb/1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title("ReclipSubs — 음성 → 자막 변환기")
        root.geometry("820x660")
        root.minsize(720, 600)

        self.files: list[str] = []
        self.msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.transcribe_max = 0.0

        self._build_ui()
        self.root.after(100, self._drain_queue)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True)

        note = ttk.Label(
            frm,
            text="파일은 이 컴퓨터 안에서만 처리됩니다. 모델은 최초 1회만 내려받고 이후 재사용합니다.",
            foreground="#666",
        )
        note.pack(anchor="w", padx=10, pady=(8, 0))

        # 1. 파일
        ff = ttk.LabelFrame(frm, text="1. 변환할 파일 (여러 개 가능)")
        ff.pack(fill="x", **pad)
        self.file_list = ttk.Treeview(ff, columns=("path",), show="tree", height=5)
        self.file_list.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        bb = ttk.Frame(ff)
        bb.pack(side="right", fill="y", padx=6, pady=6)
        ttk.Button(bb, text="파일 추가", command=self._add_files).pack(fill="x", pady=2)
        ttk.Button(bb, text="선택 제거", command=self._remove_selected).pack(fill="x", pady=2)
        ttk.Button(bb, text="전체 비우기", command=self._clear_files).pack(fill="x", pady=2)

        # 2. 옵션
        opt = ttk.LabelFrame(frm, text="2. 옵션")
        opt.pack(fill="x", **pad)

        ttk.Label(opt, text="속도/정확도").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.preset_var = StringVar(value="균형")
        for i, name in enumerate(core.PRESETS):
            ttk.Radiobutton(opt, text=name, value=name, variable=self.preset_var).grid(
                row=0, column=1 + i, sticky="w", padx=4
            )
        ttk.Label(
            opt, text="(빠름=tiny · 균형=base · 정확=small)", foreground="#888"
        ).grid(row=1, column=1, columnspan=4, sticky="w", padx=4)

        ttk.Label(opt, text="언어").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.lang_var = StringVar(value="자동 감지")
        ttk.Combobox(
            opt, textvariable=self.lang_var, values=list(core.LANGUAGES),
            state="readonly", width=12,
        ).grid(row=2, column=1, sticky="w", padx=4)

        ttk.Label(opt, text="작업").grid(row=2, column=2, sticky="w", padx=6)
        self.task_var = StringVar(value="transcribe")
        ttk.Combobox(
            opt, textvariable=self.task_var, values=["transcribe", "translate"],
            state="readonly", width=12,
        ).grid(row=2, column=3, sticky="w", padx=4)

        ttk.Label(opt, text="출력 형식").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.fmt_srt = BooleanVar(value=True)
        self.fmt_vtt = BooleanVar(value=False)
        self.fmt_txt = BooleanVar(value=False)
        ttk.Checkbutton(opt, text="SRT", variable=self.fmt_srt).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(opt, text="VTT", variable=self.fmt_vtt).grid(row=3, column=2, sticky="w")
        ttk.Checkbutton(opt, text="TXT", variable=self.fmt_txt).grid(row=3, column=3, sticky="w")

        ttk.Button(opt, text="모델 관리…", command=self._manage_models).grid(
            row=0, column=5, rowspan=2, sticky="e", padx=8
        )

        # 3. 저장 위치
        out = ttk.LabelFrame(frm, text="3. 저장 위치 (비우면 원본 파일과 같은 폴더)")
        out.pack(fill="x", **pad)
        self.outdir_var = StringVar(value="")
        ttk.Entry(out, textvariable=self.outdir_var).pack(
            side="left", fill="x", expand=True, padx=6, pady=6
        )
        ttk.Button(out, text="찾아보기", command=self._choose_outdir).pack(side="right", padx=6, pady=6)

        # 실행
        run = ttk.Frame(frm)
        run.pack(fill="x", **pad)
        self.run_btn = ttk.Button(run, text="변환 시작", command=self._start)
        self.run_btn.pack(side="left")
        self.cancel_btn = ttk.Button(run, text="취소", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        self.bar = ttk.Progressbar(run, mode="determinate", maximum=1000)
        self.bar.pack(side="left", fill="x", expand=True, padx=6)
        self.pct = ttk.Label(run, text="", width=5)
        self.pct.pack(side="left")

        # 로그
        lf = ttk.LabelFrame(frm, text="진행 상황")
        lf.pack(fill="both", expand=True, **pad)
        self.log = ScrolledText(lf, height=12, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    # ---------- 파일 조작 ----------
    def _add_files(self) -> None:
        for p in filedialog.askopenfilenames(title="파일 선택", filetypes=AUDIO_VIDEO_TYPES):
            if p not in self.files:
                self.files.append(p)
                self.file_list.insert("", "end", text=p)

    def _remove_selected(self) -> None:
        for item in self.file_list.selection():
            path = self.file_list.item(item, "text")
            if path in self.files:
                self.files.remove(path)
            self.file_list.delete(item)

    def _clear_files(self) -> None:
        self.files.clear()
        for item in self.file_list.get_children():
            self.file_list.delete(item)

    def _choose_outdir(self) -> None:
        d = filedialog.askdirectory(title="저장 폴더 선택")
        if d:
            self.outdir_var.set(d)

    # ---------- 모델 관리 ----------
    def _manage_models(self) -> None:
        dlg = _ModelDialog(self.root)
        self.root.wait_window(dlg.win)

    # ---------- 실행 ----------
    def _selected_formats(self) -> list[str]:
        f = []
        if self.fmt_srt.get():
            f.append("srt")
        if self.fmt_vtt.get():
            f.append("vtt")
        if self.fmt_txt.get():
            f.append("txt")
        return f

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

        self.worker = threading.Thread(
            target=self._run_worker,
            kwargs=dict(
                files=list(self.files),
                model_size=preset["model"],
                beam_size=preset["beam_size"],
                batch_size=preset["batch_size"],
                language=core.LANGUAGES.get(self.lang_var.get()),
                task=self.task_var.get(),
                formats=formats,
                outdir=self.outdir_var.get().strip() or None,
            ),
            daemon=True,
        )
        self.worker.start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self._enqueue(-1, "취소 요청됨… 현재 구간까지 마치고 중단합니다.")

    def _run_worker(self, files, model_size, beam_size, batch_size, language, task, formats, outdir):
        total = len(files)
        try:
            for idx, path in enumerate(files, start=1):
                if self.cancel_event.is_set():
                    break
                self._enqueue(-1, f"\n=== ({idx}/{total}) {Path(path).name} ===")
                self.transcribe_max = 0.0

                def on_progress(prog: float, message: str, _i=idx) -> None:
                    if prog >= 0:
                        overall = ((_i - 1) + prog) / total
                        self._enqueue(overall, message)
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
                    self.pct.config(text=f"{int(v*100)}%")
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
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _log_write(self, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")


class _ModelDialog:
    """다운로드된 모델 목록/삭제."""

    def __init__(self, parent) -> None:
        self.win = Toplevel(parent)
        self.win.title("모델 관리")
        self.win.geometry("420x300")
        self.win.transient(parent)

        ttk.Label(
            self.win,
            text=f"저장 위치: {core.MODELS_DIR}",
            foreground="#666",
            wraplength=390,
        ).pack(anchor="w", padx=10, pady=(10, 4))

        self.tree = ttk.Treeview(self.win, columns=("size",), show="headings", height=7)
        self.tree.heading("size", text="모델 / 용량")
        self.tree.column("size", width=380)
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
            self.tree.insert("", "end", values=("(다운로드된 모델 없음 — 변환 시 자동으로 받습니다)",))
            return
        for m in models:
            self.tree.insert(
                "", "end", iid=m["size"], values=(f"{m['size']}   ·   {_fmt_size(m['bytes'])}",)
            )

    def _delete(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        size = sel[0]
        if size not in core.SUPPORTED_MODELS:
            return
        if messagebox.askyesno("삭제", f"'{size}' 모델을 삭제할까요? (다음 사용 시 다시 받습니다)"):
            core.delete_model(size)
            self._refresh()


def main() -> None:
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
