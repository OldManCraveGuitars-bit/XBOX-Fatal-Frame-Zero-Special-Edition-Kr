"""Windows GUI / command-line launcher for the V0.8 release patch."""
from pathlib import Path
import argparse
import json
import queue
import sys
import threading
from core import apply_patch, inspect_bundle


def resources():
    if getattr(sys, 'frozen', False):
        folder = Path(sys._MEIPASS) / 'release'
        config = json.loads((folder / 'release-config.json').read_text(encoding='utf-8'))
        return config, folder / config['bundle'], folder / 'xdelta3.exe'
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / 'patcher/release-config.json').read_text(encoding='utf-8'))
    return config, root / 'patches' / config['bundle'], root / 'vendor/xdelta3/xdelta3.exe'


def main():
    parser = argparse.ArgumentParser(description='령 스페셜 에디션 한국어 패치 V0.8')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--ui-smoke', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    config, bundle, xdelta = resources()
    if args.inspect or args.source or args.output:
        try:
            if args.inspect:
                data = inspect_bundle(bundle, xdelta, config['bundle_sha256'], config['xdelta_sha256'])
                result = dict(version=data['version'], files=len(data['files']),
                              modified_files=sum(bool(x.get('delta')) for x in data['files']),
                              source=data['source'], target=data['target'], bundle_verified=True)
            else:
                if not args.source or not args.output:
                    raise ValueError('--source와 --output을 함께 지정하십시오.')
                result = apply_patch(args.source, args.output, bundle, xdelta,
                                     config['bundle_sha256'], config['xdelta_sha256'])
            if args.report:
                args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            return 0
        except Exception as error:
            if args.report:
                args.report.write_text(json.dumps(dict(error=str(error)), ensure_ascii=False, indent=2), encoding='utf-8')
            return 1
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    window = tk.Tk()
    window.title('령 스페셜 에디션 한국어 패치 V0.8')
    window.geometry('820x760')
    window.minsize(760, 720)
    window.option_add('*Font', ('맑은 고딕', 10))
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(0, weight=1)
    title_path = (bundle.parent/'title.png' if getattr(sys, 'frozen', False)
                  else Path(__file__).resolve().parents[1]/'docs/images/title.png')
    hero = tk.PhotoImage(file=str(title_path)).subsample(2, 2)
    window.hero_image = hero
    ttk.Label(frame, image=hero).grid(row=0, column=0, columnspan=2, pady=(0, 10))
    ttk.Label(frame, text='령 스페셜 에디션 · 한국어 패치 V0.8', font=('맑은 고딕', 17, 'bold')).grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 12))
    source = tk.StringVar()
    destination = tk.StringVar()
    busy = False
    events = queue.Queue()
    status = tk.StringVar(value='일본판 원본 ISO를 선택하십시오.')
    amount = tk.DoubleVar()

    def choose_source():
        if busy:
            return
        path = filedialog.askopenfilename(title='일본판 원본 ISO', filetypes=[('ISO 파일', '*.iso'), ('모든 파일', '*.*')])
        if path:
            source.set(path)
            destination.set(str(Path(path).parent / 'Fatal-Frame-Zero-Special-Edition-Kr-V0.8.xiso.iso'))

    def choose_destination():
        if busy:
            return
        path = filedialog.asksaveasfilename(title='한국어 XISO 저장 위치', initialfile='Fatal-Frame-Zero-Special-Edition-Kr-V0.8.xiso.iso', defaultextension='.iso', filetypes=[('ISO 파일', '*.iso')])
        if path:
            destination.set(path)

    ttk.Label(frame, text='일본판 원본 ISO').grid(row=2, column=0, sticky='w', pady=(16, 4))
    ttk.Entry(frame, textvariable=source).grid(row=3, column=0, sticky='ew', padx=(0, 8))
    ttk.Button(frame, text='찾아보기', command=choose_source).grid(row=3, column=1)
    ttk.Label(frame, text='한국어 XISO 저장 경로').grid(row=4, column=0, sticky='w', pady=(12, 4))
    ttk.Entry(frame, textvariable=destination).grid(row=5, column=0, sticky='ew', padx=(0, 8))
    ttk.Button(frame, text='저장 위치', command=choose_destination).grid(row=5, column=1)
    ttk.Label(frame, textvariable=status).grid(row=6, column=0, columnspan=2, sticky='w', pady=(16, 6))
    ttk.Progressbar(frame, variable=amount, maximum=100).grid(row=7, column=0, columnspan=2, sticky='ew')
    output = tk.Text(frame, height=9, wrap='word', state='disabled', font=('맑은 고딕', 9))
    output.grid(row=8, column=0, columnspan=2, sticky='nsew', pady=12)
    frame.rowconfigure(8, weight=1)

    def start():
        nonlocal busy
        if busy:
            return
        if not source.get() or not destination.get():
            messagebox.showinfo('ISO 선택', '원본 ISO와 출력 경로를 지정하십시오.')
            return
        selected_source, selected_output = source.get(), destination.get()
        busy = True
        button.configure(state='disabled')
        amount.set(0)
        status.set('패치 중...')

        def worker():
            try:
                result = apply_patch(selected_source, selected_output, bundle, xdelta,
                                     config['bundle_sha256'], config['xdelta_sha256'],
                                     log=lambda value: events.put(('log', value)),
                                     progress=lambda value: events.put(('progress', value)))
                events.put(('done', result))
            except Exception as error:
                events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    button = ttk.Button(frame, text='한국어 ISO 만들기', command=start)
    button.grid(row=9, column=0, columnspan=2, sticky='e')

    def poll():
        nonlocal busy
        for _ in range(400):
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                status.set(value if len(value) < 85 else '리소스를 반영합니다...')
                output.configure(state='normal')
                output.insert('end', value + '\n')
                output.see('end')
                output.configure(state='disabled')
            elif kind == 'progress':
                amount.set(value)
            else:
                busy = False
                button.configure(state='normal')
                if kind == 'done':
                    status.set('완료 · 전체 ISO 해시 대조 통과')
                    messagebox.showinfo('완료', value['output'] + '\n\nSHA-256\n' + value['target_sha256'])
                else:
                    status.set('패치를 완료하지 못했습니다.')
                    messagebox.showerror('패치 오류', value)
        window.after(100, poll)

    def close():
        if busy:
            messagebox.showinfo('패치 진행 중', '패치가 끝난 뒤 창을 닫으십시오.')
            return
        window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(100, poll)
    if args.ui_smoke:
        window.update_idletasks()
        window.update()
        assert hero.width() == 320 and hero.height() == 256
        assert button.winfo_ismapped() and output.winfo_ismapped()
        assert button.winfo_y() + button.winfo_height() <= frame.winfo_height()
        if args.report:
            args.report.write_text(json.dumps(dict(version='V0.8', title_image=[hero.width(), hero.height()],
                gui_widgets_visible=True, patch_button_inside_window=True,
                client_size=[window.winfo_width(), window.winfo_height()]), indent=2), encoding='utf-8')
        window.after(300, window.destroy)
    window.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
