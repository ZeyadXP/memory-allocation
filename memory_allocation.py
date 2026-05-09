import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkfont
import copy

# ─────────────────────────────────────────────
#  Data structures
# ─────────────────────────────────────────────
class Segment:
    def __init__(self, name, size, start=None):
        self.name = name
        self.size = size
        self.start = start          # None → not yet allocated

class Process:
    def __init__(self, pid):
        self.pid = pid
        self.segments = []          # list of Segment

class MemoryManager:
    def __init__(self, total_size):
        self.total_size = total_size
        self.holes = []             # list of dict {start, size}
        self.allocated = []         # list of dict {start, size, pid, seg_name}
        self.processes = {}         # pid → Process
        self.log = []               # list of strings describing each step

    # ── Hole management ──────────────────────
    def add_initial_hole(self, start, size):
        self.holes.append({"start": start, "size": size})
        self._sort_holes()

    def _sort_holes(self):
        self.holes.sort(key=lambda h: h["start"])

    def _merge_holes(self):
        """Merge adjacent / overlapping holes."""
        self.holes.sort(key=lambda h: h["start"])
        merged = []
        for h in self.holes:
            if merged and merged[-1]["start"] + merged[-1]["size"] >= h["start"]:
                merged[-1]["size"] = max(
                    merged[-1]["start"] + merged[-1]["size"],
                    h["start"] + h["size"]
                ) - merged[-1]["start"]
            else:
                merged.append(dict(h))
        self.holes = merged

    # ── Allocation algorithms ─────────────────
    def _first_fit(self, size):
        for h in self.holes:
            if h["size"] >= size:
                return h
        return None

    def _best_fit(self, size):
        candidates = [h for h in self.holes if h["size"] >= size]
        if not candidates:
            return None
        return min(candidates, key=lambda h: h["size"])

    def _allocate_from_hole(self, hole, size, pid, seg_name):
        start = hole["start"]
        if hole["size"] == size:
            self.holes.remove(hole)
        else:
            hole["start"] += size
            hole["size"]  -= size
        self.allocated.append({"start": start, "size": size,
                                "pid": pid, "seg_name": seg_name})
        self._sort_holes()
        return start

    # ── Public API ────────────────────────────
    def allocate_process(self, pid, segments_dict, algorithm):
        """
        segments_dict: {seg_name: size}
        algorithm: 'first' | 'best'
        Returns (success:bool, message:str)
        """
        fit_fn = self._first_fit if algorithm == "first" else self._best_fit
        # Check all segments fit BEFORE committing
        holes_snapshot = copy.deepcopy(self.holes)
        temp_allocs = []
        for seg_name, seg_size in segments_dict.items():
            h = fit_fn(seg_size)
            if h is None:
                self.holes = holes_snapshot   # rollback
                return False, f"Segment '{seg_name}' (size {seg_size}K) could not fit."
            # Simulate allocation on holes
            start = h["start"]
            if h["size"] == seg_size:
                self.holes.remove(h)
            else:
                h["start"] += seg_size
                h["size"]  -= seg_size
            temp_allocs.append((seg_name, seg_size, start))

        # Commit
        proc = Process(pid)
        for seg_name, seg_size, start in temp_allocs:
            proc.segments.append(Segment(seg_name, seg_size, start))
            self.allocated.append({"start": start, "size": seg_size,
                                   "pid": pid, "seg_name": seg_name})
        self.processes[pid] = proc
        self._sort_holes()
        return True, f"Process {pid} allocated successfully."

    def deallocate_process(self, pid):
        if pid not in self.processes:
            return False, f"Process {pid} not found."
        proc = self.processes.pop(pid)
        for seg in proc.segments:
            # Return segment space to holes
            self.holes.append({"start": seg.start, "size": seg.size})
            # Remove from allocated list
            self.allocated = [a for a in self.allocated
                              if not (a["pid"] == pid and a["seg_name"] == seg.name)]
        self._merge_holes()
        return True, f"Process {pid} deallocated."

    # ── Snapshot helpers ─────────────────────
    def get_memory_snapshot(self):
        """Returns sorted list of blocks covering 0..total_size."""
        blocks = []
        for a in self.allocated:
            blocks.append({"start": a["start"], "size": a["size"],
                           "type": "alloc", "label": f"{a['pid']}\n{a['seg_name']}"})
        for h in self.holes:
            blocks.append({"start": h["start"], "size": h["size"],
                           "type": "hole", "label": "FREE"})
        # Occupied regions
        occupied = set()
        for b in blocks:
            for i in range(b["start"], b["start"] + b["size"]):
                occupied.add(i)
        # Find implicit used regions (between holes+allocs) — the initially occupied parts
        return sorted(blocks, key=lambda b: b["start"])

    def get_segment_tables(self):
        """Returns dict pid → list of {seg_name, base, limit}"""
        tables = {}
        for pid, proc in self.processes.items():
            tables[pid] = [{"seg": s.name, "base": s.start, "limit": s.size}
                           for s in proc.segments]
        return tables


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
COLORS = {
    "bg":       "#1e1e2e",
    "panel":    "#2a2a3e",
    "accent":   "#7c3aed",
    "accent2":  "#06b6d4",
    "success":  "#10b981",
    "warn":     "#f59e0b",
    "error":    "#ef4444",
    "text":     "#e2e8f0",
    "sub":      "#94a3b8",
    "hole":     "#334155",
    "border":   "#3f3f5f",
}

PROC_PALETTE = [
    "#7c3aed","#06b6d4","#10b981","#f59e0b",
    "#ec4899","#f97316","#6366f1","#14b8a6",
]

def proc_color(pid):
    idx = int(pid[1:]) - 1 if pid[1:].isdigit() else hash(pid)
    return PROC_PALETTE[idx % len(PROC_PALETTE)]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Memory Management – Segmentation Simulator")
        self.configure(bg=COLORS["bg"])
        self.resizable(True, True)
        self.geometry("1200x780")

        self.mgr = None
        self.algorithm = tk.StringVar(value="first")
        self._build_ui()

    # ─── Layout ──────────────────────────────
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=COLORS["accent"], height=50)
        top.pack(fill="x")
        tk.Label(top, text="  🧠  Memory Management Simulator — Segmentation",
                 bg=COLORS["accent"], fg="white",
                 font=("Segoe UI", 13, "bold")).pack(side="left", pady=10)

        # Main split
        main = tk.Frame(self, bg=COLORS["bg"])
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel – controls
        left = tk.Frame(main, bg=COLORS["panel"], width=360, relief="flat")
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        self._build_controls(left)

        # Right side – memory map + log
        right = tk.Frame(main, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True)
        self._build_right(right)

    def _section(self, parent, title):
        f = tk.LabelFrame(parent, text=f"  {title}  ",
                          bg=COLORS["panel"], fg=COLORS["accent2"],
                          font=("Segoe UI", 9, "bold"),
                          relief="groove", bd=1,
                          labelanchor="nw")
        f.pack(fill="x", padx=10, pady=(8, 0))
        return f

    def _label(self, parent, text):
        tk.Label(parent, text=text, bg=COLORS["panel"],
                 fg=COLORS["sub"], font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=(4,0))

    def _entry(self, parent, var=None):
        e = tk.Entry(parent, textvariable=var,
                     bg=COLORS["bg"], fg=COLORS["text"],
                     insertbackground=COLORS["text"],
                     relief="flat", font=("Segoe UI", 10),
                     highlightthickness=1,
                     highlightbackground=COLORS["border"],
                     highlightcolor=COLORS["accent"])
        e.pack(fill="x", padx=6, pady=2)
        return e

    def _btn(self, parent, text, cmd, color=None):
        c = color or COLORS["accent"]
        b = tk.Button(parent, text=text, command=cmd,
                      bg=c, fg="white", font=("Segoe UI", 9, "bold"),
                      relief="flat", cursor="hand2",
                      activebackground=COLORS["accent2"],
                      activeforeground="white", pady=5)
        b.pack(fill="x", padx=6, pady=3)
        return b

    def _build_controls(self, parent):
        tk.Label(parent, text="Controls", bg=COLORS["panel"],
                 fg=COLORS["text"], font=("Segoe UI", 11, "bold")).pack(pady=(10,0))

        # ── Init memory
        s = self._section(parent, "1. Initialize Memory")
        self._label(s, "Total Memory Size (K):")
        self.v_total = tk.StringVar(value="1000")
        self._entry(s, self.v_total)

        self._label(s, "Holes  (start,size  per line):")
        self.txt_holes = tk.Text(s, height=4, bg=COLORS["bg"], fg=COLORS["text"],
                                 font=("Consolas", 9), relief="flat",
                                 insertbackground=COLORS["text"])
        self.txt_holes.pack(fill="x", padx=6, pady=4)
        self.txt_holes.insert("1.0", "0,300\n400,250\n700,200")
        self._btn(s, "Initialize Memory", self._init_memory, COLORS["success"])

        # ── Algorithm
        s2 = self._section(parent, "2. Algorithm")
        for val, lbl in [("first","First-Fit"), ("best","Best-Fit")]:
            tk.Radiobutton(s2, text=lbl, variable=self.algorithm, value=val,
                           bg=COLORS["panel"], fg=COLORS["text"],
                           selectcolor=COLORS["accent"],
                           font=("Segoe UI", 9),
                           activebackground=COLORS["panel"],
                           activeforeground=COLORS["text"]).pack(anchor="w", padx=10)

        # ── Allocate
        s3 = self._section(parent, "3. Allocate Process")
        self._label(s3, "Process ID (e.g. P1):")
        self.v_pid = tk.StringVar(value="P1")
        self._entry(s3, self.v_pid)
        self._label(s3, "Segments  (name,size  per line):")
        self.txt_segs = tk.Text(s3, height=4, bg=COLORS["bg"], fg=COLORS["text"],
                                font=("Consolas", 9), relief="flat",
                                insertbackground=COLORS["text"])
        self.txt_segs.pack(fill="x", padx=6, pady=4)
        self.txt_segs.insert("1.0", "Code,100\nData,120\nStack,90")
        self._btn(s3, "Allocate", self._allocate)

        # ── Deallocate
        s4 = self._section(parent, "4. Deallocate Process")
        self._label(s4, "Process ID:")
        self.v_dpid = tk.StringVar(value="P1")
        self._entry(s4, self.v_dpid)
        self._btn(s4, "Deallocate", self._deallocate, COLORS["error"])

        # ── Reset
        tk.Frame(parent, bg=COLORS["panel"], height=10).pack()
        self._btn(parent, "⟳  Reset Everything", self._reset, COLORS["warn"])

    def _build_right(self, parent):
        # Memory map canvas
        map_frame = tk.LabelFrame(parent, text="  Memory Layout  ",
                                  bg=COLORS["bg"], fg=COLORS["accent2"],
                                  font=("Segoe UI", 9, "bold"), relief="groove")
        map_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.canvas = tk.Canvas(map_frame, bg=COLORS["bg"],
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", lambda e: self._draw_memory())

        # Segment tables + log
        bot = tk.Frame(parent, bg=COLORS["bg"])
        bot.pack(fill="both", expand=False)

        tbl_frame = tk.LabelFrame(bot, text="  Segment Tables  ",
                                  bg=COLORS["bg"], fg=COLORS["accent2"],
                                  font=("Segoe UI", 9, "bold"), relief="groove")
        tbl_frame.pack(side="left", fill="both", expand=True, padx=(0,4))

        cols = ("Process","Segment","Base","Limit")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=7)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=COLORS["panel"],
                        foreground=COLORS["text"],
                        fieldbackground=COLORS["panel"],
                        rowheight=22)
        style.configure("Treeview.Heading",
                        background=COLORS["accent"],
                        foreground="white",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLORS["accent2"])])
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=80, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)

        log_frame = tk.LabelFrame(bot, text="  Operation Log  ",
                                  bg=COLORS["bg"], fg=COLORS["accent2"],
                                  font=("Segoe UI", 9, "bold"), relief="groove",
                                  width=300)
        log_frame.pack(side="left", fill="both", expand=True)
        log_frame.pack_propagate(False)

        self.log_txt = scrolledtext.ScrolledText(log_frame,
                                                 bg=COLORS["bg"], fg=COLORS["text"],
                                                 font=("Consolas", 8),
                                                 state="disabled", relief="flat")
        self.log_txt.pack(fill="both", expand=True, padx=4, pady=4)

    # ─── Actions ─────────────────────────────
    def _init_memory(self):
        try:
            total = int(self.v_total.get())
        except ValueError:
            messagebox.showerror("Error", "Total memory must be an integer."); return
        self.mgr = MemoryManager(total)
        for line in self.txt_holes.get("1.0","end").strip().splitlines():
            line = line.strip()
            if not line: continue
            try:
                s, z = line.split(",")
                self.mgr.add_initial_hole(int(s.strip()), int(z.strip()))
            except Exception:
                messagebox.showerror("Error", f"Bad hole line: '{line}'"); return
        self._log(f"✅ Memory initialized: {total}K | Holes: {[str(h) for h in self.mgr.holes]}")
        self._refresh()

    def _allocate(self):
        if not self.mgr:
            messagebox.showwarning("Warning","Initialize memory first."); return
        pid = self.v_pid.get().strip()
        if not pid:
            messagebox.showerror("Error","Enter a process ID."); return
        if pid in self.mgr.processes:
            messagebox.showerror("Error",f"Process {pid} already exists."); return
        segs = {}
        for line in self.txt_segs.get("1.0","end").strip().splitlines():
            line = line.strip()
            if not line: continue
            try:
                name, size = line.split(",")
                segs[name.strip()] = int(size.strip())
            except Exception:
                messagebox.showerror("Error", f"Bad segment line: '{line}'"); return
        algo = self.algorithm.get()
        ok, msg = self.mgr.allocate_process(pid, segs, algo)
        self._log(f"{'✅' if ok else '❌'} [{algo.upper()}-FIT] Allocate {pid}: {msg}")
        if not ok:
            messagebox.showerror("Allocation Failed", msg)
        self._refresh()

    def _deallocate(self):
        if not self.mgr:
            messagebox.showwarning("Warning","Initialize memory first."); return
        pid = self.v_dpid.get().strip()
        ok, msg = self.mgr.deallocate_process(pid)
        self._log(f"{'✅' if ok else '❌'} Deallocate {pid}: {msg}")
        if not ok:
            messagebox.showerror("Error", msg)
        self._refresh()

    def _reset(self):
        self.mgr = None
        self.canvas.delete("all")
        self.tree.delete(*self.tree.get_children())
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0","end")
        self.log_txt.configure(state="disabled")
        self._log("⟳ Reset.")

    # ─── Display helpers ──────────────────────
    def _log(self, msg):
        self.log_txt.configure(state="normal")
        self.log_txt.insert("end", msg + "\n")
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")

    def _refresh(self):
        self._draw_memory()
        self._update_table()

    def _draw_memory(self):
        self.canvas.delete("all")
        if not self.mgr:
            return
        W = self.canvas.winfo_width()  or 600
        H = self.canvas.winfo_height() or 300
        total = self.mgr.total_size

        bar_x   = 80
        bar_w   = W - bar_x - 60
        bar_y   = 30
        bar_h   = H - 60
        if bar_w < 10 or bar_h < 10:
            return

        blocks = self.mgr.get_memory_snapshot()

        # Draw each block
        for blk in blocks:
            frac_start = blk["start"] / total
            frac_end   = (blk["start"] + blk["size"]) / total
            x1 = bar_x + frac_start * bar_w
            x2 = bar_x + frac_end   * bar_w
            y1 = bar_y
            y2 = bar_y + bar_h

            if blk["type"] == "hole":
                fill = COLORS["hole"]
                outline = COLORS["border"]
                txt_color = COLORS["sub"]
            else:
                pid = blk["label"].split("\n")[0]
                fill = proc_color(pid)
                outline = "white"
                txt_color = "white"

            self.canvas.create_rectangle(x1, y1, x2, y2,
                                         fill=fill, outline=outline, width=1)
            # Label
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            label = blk["label"] if blk["type"] == "hole" else blk["label"].replace("\n", " / ")
            if x2 - x1 > 30:
                self.canvas.create_text(cx, cy, text=label,
                                        fill=txt_color, font=("Segoe UI", 7, "bold"),
                                        width=x2-x1-4)
            # Address labels on left
            addr_y = y1 + (frac_start + (blk["size"]/total)/2) * bar_h
            self.canvas.create_text(bar_x - 5, y1 + frac_start * bar_h,
                                    text=str(blk["start"]),
                                    fill=COLORS["sub"], font=("Consolas", 7),
                                    anchor="e")

        # Top and bottom address
        self.canvas.create_text(bar_x - 5, bar_y,
                                text="0", fill=COLORS["sub"],
                                font=("Consolas", 7), anchor="e")
        self.canvas.create_text(bar_x - 5, bar_y + bar_h,
                                text=str(total), fill=COLORS["sub"],
                                font=("Consolas", 7), anchor="e")

        # Border around full bar
        self.canvas.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                                     outline=COLORS["border"], width=2, fill="")

        # Legend
        legend_x = bar_x + bar_w + 10
        self.canvas.create_text(legend_x, bar_y,
                                text="FREE", fill=COLORS["sub"],
                                font=("Segoe UI", 7), anchor="nw")
        self.canvas.create_rectangle(legend_x, bar_y + 14,
                                     legend_x + 14, bar_y + 28,
                                     fill=COLORS["hole"], outline=COLORS["border"])
        row = bar_y + 35
        seen = set()
        for blk in blocks:
            if blk["type"] == "alloc":
                pid = blk["label"].split("\n")[0]
                if pid not in seen:
                    seen.add(pid)
                    self.canvas.create_rectangle(legend_x, row,
                                                 legend_x + 14, row + 14,
                                                 fill=proc_color(pid), outline="white")
                    self.canvas.create_text(legend_x + 18, row + 7,
                                            text=pid, fill=COLORS["text"],
                                            font=("Segoe UI", 7), anchor="w")
                    row += 18

    def _update_table(self):
        self.tree.delete(*self.tree.get_children())
        if not self.mgr:
            return
        tables = self.mgr.get_segment_tables()
        for pid, entries in sorted(tables.items()):
            for e in entries:
                self.tree.insert("", "end",
                                 values=(pid, e["seg"], e["base"],
                                         f"{e['limit']}K"))


if __name__ == "__main__":
    app = App()
    app.mainloop()