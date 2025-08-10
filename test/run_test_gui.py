import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import subprocess
import threading
import os
import sys

class TestRunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Playwright Test Runner")
        self.root.geometry("800x600")

        # --- パスの設定 ---
        # このスクリプト(run_test_gui.py)があるディレクトリ (test/)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        # プロジェクトのルートディレクトリ (test/ の一つ上)
        self.project_root = os.path.dirname(self.script_dir)
        # 呼び出すスクリプトへの絶対パス
        self.target_script_path = os.path.join(self.project_root, "playwright_mainditect_v3.py")
        # 読み込むテストケースファイルへの絶対パス
        self.test_cases_path = os.path.join(self.script_dir, "test_cases.json")
        

        # これにより、playwright_mainditect_v3が依存する他のモジュールを正しく見つけられるようになります。
        if self.project_root not in sys.path:
            sys.path.insert(0, self.project_root)

        # スタイル
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # フレームの設定
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # テストケース選択
        list_frame = ttk.LabelFrame(main_frame, text="Test Cases", padding="10")
        list_frame.pack(fill=tk.X, pady=5)

        self.test_cases = self.load_test_cases()
        self.test_case_names = [case["name"] for case in self.test_cases]

        self.case_listbox = tk.Listbox(list_frame, height=8)
        for name in self.test_case_names:
            self.case_listbox.insert(tk.END, name)
        self.case_listbox.pack(fill=tk.X, expand=True)
        if self.test_case_names:
            self.case_listbox.select_set(0)

        # 実行ボタン
        self.run_button = ttk.Button(main_frame, text="Run Selected Test", command=self.run_test)
        self.run_button.pack(fill=tk.X, pady=10)

        # 出力表示エリア
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True)

    def load_test_cases(self):
        try:

            with open(self.test_cases_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return [{"name": f"{self.test_cases_path} not found", "url": "", "mode": "", "selector": ""}]

    def run_test(self):
        selected_indices = self.case_listbox.curselection()
        if not selected_indices:
            return

        selected_index = selected_indices[0]
        selected_case = self.test_cases[selected_index]

        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, f"Running test: {selected_case['name']}\n")
        self.output_text.insert(tk.END, "-"*50 + "\n")
        self.output_text.config(state=tk.DISABLED)
        self.run_button.config(state=tk.DISABLED)

        thread = threading.Thread(target=self._execute_subprocess, args=(selected_case,))
        thread.daemon = True
        thread.start()

    def _execute_subprocess(self, case):
        command = [
            sys.executable,  # 'python'の代わりに、現在実行中のPythonインタプリタの絶対パスを使用
            self.target_script_path,
            case["url"],
            "--mode",
            case["mode"]
        ]
        if case["mode"] == "quick" and case["selector"]:
            command.extend(["--selector", case["selector"]])

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=self.project_root,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        for line in iter(process.stdout.readline, ''):
            self.root.after(0, self.update_output, line)

        process.wait()
        self.root.after(0, self.on_test_complete)

    def update_output(self, line):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, line)
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)

    def on_test_complete(self):
        self.update_output("\n" + "-"*50 + "\nTest finished.\n")
        self.run_button.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = TestRunnerApp(root)
    root.mainloop()