#!/usr/bin/env python3
# GUI wrapper for teacher_sim .py
# Save as gui.py in the repo root (same dir as "teacher_sim .py").

import os
import sys
import threading
import subprocess
import time
import queue
import tkinter as tk
from tkinter import scrolledtext, messagebox

# Path to teacher script (supports the repo's filename with space)
SCRIPT_NAMES = ["teacher_sim .py", "teacher_sim.py", "teacher_sim.py".replace(" ", "")]

def find_teacher_script():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, name) for name in SCRIPT_NAMES]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # fallback: try any file starting with teacher_sim in folder
    for fname in os.listdir(here):
        if fname.startswith("teacher_sim") and fname.endswith(".py"):
            return os.path.join(here, fname)
    return None

DEFAULT_LOG_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "teacher_sim.log")

class TeacherGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Teacher GUI")
        self.proc = None
        self.proc_lock = threading.Lock()
        self.stdout_thread = None
        self.stderr_thread = None
        self.tail_thread = None
        self.stop_threads = threading.Event()
        self.stdout_q = queue.Queue()
        self.stderr_q = queue.Queue()
        self.log_path = DEFAULT_LOG_PATH
        self.log_pos = 0

        self.script_path = find_teacher_script()
        if not self.script_path:
            messagebox.showerror("错误", "未找到 teacher_sim 脚本（teacher_sim .py）。请把 gui.py 放在仓库根目录或手动指定脚本路径。")
        self._build_ui()
        # periodic pump for queued lines
        self.root.after(200, self._pump_queues)

    def _build_ui(self):
        frm_top = tk.Frame(self.root)
        frm_top.pack(fill="x", padx=6, pady=6)

        tk.Label(frm_top, text="Teacher 脚本:").grid(row=0, column=0, sticky="w")
        self.script_label = tk.Label(frm_top, text=self.script_path or "<未找到>", anchor="w")
        self.script_label.grid(row=0, column=1, columnspan=4, sticky="we", padx=(6,0))
        frm_top.grid_columnconfigure(1, weight=1)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=6)
        self.start_btn = tk.Button(btn_frame, text="Start Teacher", command=self.start_teacher)
        self.start_btn.pack(side="left")
        self.stop_btn = tk.Button(btn_frame, text="Stop Teacher", command=self.stop_teacher, state="disabled")
        self.stop_btn.pack(side="left", padx=(6,0))
        tk.Button(btn_frame, text="Clear Log", command=self.clear_log).pack(side="right")

        ctrl_frame = tk.LabelFrame(self.root, text="Controls")
        ctrl_frame.pack(fill="x", padx=6, pady=6)

        tk.Label(ctrl_frame, text="IP / Target:").grid(row=0, column=0, sticky="w")
        self.ip_entry = tk.Entry(ctrl_frame, width=20)
        self.ip_entry.grid(row=0, column=1, sticky="w", padx=(6,6))
        tk.Label(ctrl_frame, text="Args:").grid(row=0, column=2, sticky="w")
        self.args_entry = tk.Entry(ctrl_frame, width=40)
        self.args_entry.grid(row=0, column=3, sticky="we", padx=(6,6))
        ctrl_frame.grid_columnconfigure(3, weight=1)

        shortcut_frame = tk.Frame(ctrl_frame)
        shortcut_frame.grid(row=1, column=0, columnspan=4, pady=(6,0), sticky="we")

        def btn(cmd):
            return lambda: self._send_shortcut(cmd)

        tk.Button(shortcut_frame, text="list", width=8, command=btn("list")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="preview", width=10, command=btn("preview {ip}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="view", width=8, command=btn("view {ip}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="view_stop", width=10, command=btn("view_stop {ip}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="control", width=8, command=btn("control {ip}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="control_stop", width=12, command=btn("control_stop {ip}")).pack(side="left", padx=2)

        tk.Button(shortcut_frame, text="msg", width=6, command=btn("msg {ip} {args}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="bs", width=6, command=btn("bs {ip} {args}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="unlock", width=8, command=btn("unlock {ip}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="shutdown", width=10, command=btn("shutdown {ip} {args}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="reboot", width=8, command=btn("reboot {ip} {args}")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="debug on", width=10, command=btn("debug on")).pack(side="left", padx=2)
        tk.Button(shortcut_frame, text="debug off", width=10, command=btn("debug off")).pack(side="left", padx=2)

        # free command entry
        cmd_frame = tk.Frame(self.root)
        cmd_frame.pack(fill="x", padx=6, pady=(0,6))
        tk.Label(cmd_frame, text="Command:").pack(side="left")
        self.cmd_entry = tk.Entry(cmd_frame)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=(6,6))
        tk.Button(cmd_frame, text="Send", command=self.send_command_from_entry).pack(side="left")

        # log area
        self.log = scrolledtext.ScrolledText(self.root, height=20, state="disabled", wrap="none")
        self.log.pack(fill="both", expand=True, padx=6, pady=(0,6))

        # status bar
        self.status = tk.Label(self.root, text="Stopped", anchor="w")
        self.status.pack(fill="x", padx=6, pady=(0,6))

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def start_teacher(self):
        if not self.script_path or not os.path.isfile(self.script_path):
            messagebox.showerror("错误", "找不到 teacher_sim 脚本，无法启动。")
            return
        with self.proc_lock:
            if self.proc:
                messagebox.showinfo("提示", "Teacher 已在运行。")
                return
            try:
                # Use same python executable
                cmd = [sys.executable, self.script_path]
                # Start process with pipes, text mode
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, bufsize=1, universal_newlines=True)
            except Exception as e:
                messagebox.showerror("启动失败", f"无法启动 teacher 脚本：{e}")
                self.proc = None
                return

            self.stop_threads.clear()
            self.stdout_thread = threading.Thread(target=self._reader_thread, args=(self.proc.stdout, self.stdout_q), daemon=True)
            self.stderr_thread = threading.Thread(target=self._reader_thread, args=(self.proc.stderr, self.stderr_q), daemon=True)
            self.stdout_thread.start()
            self.stderr_thread.start()

            # start tail thread for log file
            self.log_pos = 0
            self.tail_thread = threading.Thread(target=self._tail_log_thread, daemon=True)
            self.tail_thread.start()

            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.status.config(text="Running")
            self.append_log(f"[GUI] 已启动 teacher 进程 pid={self.proc.pid}\n")

    def stop_teacher(self):
        with self.proc_lock:
            if not self.proc:
                return
            try:
                # try graceful exit by sending "exit" or "quit"
                try:
                    self._write_to_proc("exit")
                except Exception:
                    pass
                # give a short time to exit
                for _ in range(10):
                    if self.proc.poll() is not None:
                        break
                    time.sleep(0.2)
                if self.proc.poll() is None:
                    self.proc.terminate()
                    time.sleep(0.5)
                    if self.proc.poll() is None:
                        self.proc.kill()
            except Exception as e:
                self.append_log(f"[GUI] Stop error: {e}\n")
            finally:
                self.proc = None
                self.stop_threads.set()
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")
                self.status.config(text="Stopped")
                self.append_log("[GUI] Teacher 已停止。\n")

    def _write_to_proc(self, line):
        with self.proc_lock:
            if not self.proc or self.proc.stdin is None:
                raise RuntimeError("teacher 未运行")
            # Ensure newline
            self.proc.stdin.write(line.rstrip("\n") + "\n")
            try:
                self.proc.stdin.flush()
            except Exception:
                pass

    def send_command_from_entry(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        try:
            self._write_to_proc(cmd)
            self.append_log(f">>> {cmd}\n")
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def _send_shortcut(self, template):
        ip = self.ip_entry.get().strip()
        args = self.args_entry.get().strip()
        cmd = template.format(ip=ip, args=args).strip()
        # clean double spaces
        cmd = " ".join(cmd.split())
        if "{ip}" in template and not ip:
            messagebox.showwarning("缺少 IP", "请在 IP / Target 输入框填入目标 IP。")
            return
        try:
            self._write_to_proc(cmd)
            self.append_log(f">>> {cmd}\n")
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def _reader_thread(self, stream, q):
        try:
            for line in iter(stream.readline, ""):
                q.put(line)
                if self.stop_threads.is_set():
                    break
        except Exception:
            pass

    def _pump_queues(self):
        # pump stdout
        try:
            while True:
                line = self.stdout_q.get_nowait()
                self.append_log(line)
        except queue.Empty:
            pass
        try:
            while True:
                line = self.stderr_q.get_nowait()
                self.append_log(line)
        except queue.Empty:
            pass
        self.root.after(200, self._pump_queues)

    def _tail_log_thread(self):
        # continuously read the log file, append new content
        # we try the default path, but allow a few seconds for file creation
        for _ in range(30):
            if self.stop_threads.is_set():
                return
            if os.path.exists(self.log_path):
                break
            time.sleep(0.2)
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                self.log_pos = f.tell()
                while not self.stop_threads.is_set():
                    f.seek(self.log_pos)
                    new = f.read()
                    if new:
                        self.log_pos = f.tell()
                        # push into stdout queue for consistent handling
                        self.stdout_q.put(f"[log] {new}")
                    time.sleep(0.5)
        except Exception as e:
            self.stdout_q.put(f"[GUI] tail log 失败: {e}\n")

    def on_close(self):
        if messagebox.askokcancel("退出", "确定退出并停止 teacher 进程吗？"):
            self.stop_threads.set()
            self.stop_teacher()
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    gui = TeacherGui(root)
    root.protocol("WM_DELETE_WINDOW", gui.on_close)
    root.mainloop()