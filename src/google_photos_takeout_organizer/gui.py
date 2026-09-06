from __future__ import annotations
import queue, threading, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .service import analyze
from .exporter import export
from .verifier import verify

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__(); self.title("Google Photos Takeout Organizer"); self.geometry("760x500")
        self.sources: list[str] = []; self.work = Path("work"); self.output = tk.StringVar(); self.status = tk.StringVar(value="IDLE")
        self.listbox = tk.Listbox(self); self.listbox.pack(fill="both", expand=True, padx=12, pady=8)
        actions = ttk.Frame(self); actions.pack(fill="x", padx=12)
        ttk.Button(actions, text="Add ZIP", command=lambda: self.add(filedialog.askopenfilenames(filetypes=[("ZIP", "*.zip")]))).pack(side="left")
        ttk.Button(actions, text="Add Folder", command=lambda: self.add([filedialog.askdirectory()])).pack(side="left")
        ttk.Button(actions, text="Remove", command=self.remove).pack(side="left")
        ttk.Button(actions, text="Output", command=self.choose_output).pack(side="left")
        self.analyze_button = ttk.Button(actions, text="1. Analyze", command=self.run_analyze); self.analyze_button.pack(side="left")
        self.report_button = ttk.Button(actions, text="2. Open HTML Report", command=self.open_report, state="disabled"); self.report_button.pack(side="left")
        self.export_button = ttk.Button(actions, text="3. Export", command=self.run_export, state="disabled"); self.export_button.pack(side="left")
        self.verify_button = ttk.Button(actions, text="4. Verify", command=self.run_verify, state="disabled"); self.verify_button.pack(side="left")
        ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=12, pady=8); self.progress = ttk.Progressbar(self, mode="indeterminate"); self.progress.pack(fill="x", padx=12)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue(); self.after(100, self.poll); self.protocol("WM_DELETE_WINDOW", self.close)
    def add(self, paths: object) -> None:
        for path in paths or []:
            if path and path not in self.sources: self.sources.append(path); self.listbox.insert("end", path)
    def remove(self) -> None:
        for i in reversed(self.listbox.curselection()): self.sources.pop(i); self.listbox.delete(i)
    def choose_output(self) -> None:
        value = filedialog.askdirectory(); self.output.set(value or self.output.get())
    def run(self, label: str, task) -> None:
        self.status.set(label); self.progress.start(); self.analyze_button.configure(state="disabled")
        threading.Thread(target=lambda: self._worker(task), daemon=True).start()
    def _worker(self, task) -> None:
        try: self.events.put(("done", task()))
        except Exception as exc: self.events.put(("error", exc))
    def poll(self) -> None:
        try:
            kind, payload = self.events.get_nowait(); self.progress.stop(); self.analyze_button.configure(state="normal")
            if kind == "error": self.status.set("FAILED"); messagebox.showerror("Organizer", str(payload))
            else: self.status.set("Complete"); self.report_button.configure(state="normal"); self.export_button.configure(state="normal"); self.verify_button.configure(state="normal")
        except queue.Empty: pass
        self.after(100, self.poll)
    def run_analyze(self) -> None:
        if not self.sources: return messagebox.showwarning("Organizer", "Add at least one ZIP or folder.")
        self.run("ANALYZING", lambda: analyze([Path(x) for x in self.sources], self.work))
    def run_export(self) -> None:
        if not self.output.get(): return self.choose_output()
        self.run("EXPORTING", lambda: export(self.work / "manifest.json", Path(self.output.get())))
    def run_verify(self) -> None:
        if not self.output.get(): return self.choose_output()
        self.run("VERIFYING", lambda: verify(Path(self.output.get()) / "manifest.json", Path(self.output.get())))
    def open_report(self) -> None: webbrowser.open((self.work / "report.html").resolve().as_uri())
    def close(self) -> None:
        if self.progress["value"] and not messagebox.askyesno("Organizer", "A task is still running. Close after it completes instead?"): return
        self.destroy()
def main() -> None: App().mainloop()
if __name__ == "__main__": main()
