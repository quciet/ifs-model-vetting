"""Native folder dialog opened only by the user's Browse action."""
import sys
import json
import pathlib
import tkinter as tk
from tkinter import filedialog

def select_folder(initial, output):
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(title='Select IFs installation folder', initialdir=initial, parent=root)
    root.destroy()
    pathlib.Path(output).write_text(json.dumps({'installation':folder or None}),encoding='utf-8')


if __name__ == '__main__':
    select_folder(sys.argv[1],sys.argv[2])
