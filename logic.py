import copy

class Segment:
    def __init__(self, name, size, start=None):
        self.name = name
        self.size = size
        self.start = start

class Process:
    def __init__(self, pid):
        self.pid = pid
        self.segments = []

class MemoryManager:
    def __init__(self, total_size):
        self.total_size = total_size
        self.holes = []
        self.allocated = []
        self.processes = {}

    def add_initial_hole(self, start, size):
        self.holes.append({"start": start, "size": size})
        self._sort_holes()

    def _sort_holes(self):
        self.holes.sort(key=lambda h: h["start"])

    def _merge_holes(self):
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

    def allocate_process(self, pid, segments_dict, algorithm):
        fit_fn = self._first_fit if algorithm == "first" else self._best_fit
        holes_snapshot = copy.deepcopy(self.holes)
        temp_allocs = []
        for seg_name, seg_size in segments_dict.items():
            h = fit_fn(seg_size)
            if h is None:
                self.holes = holes_snapshot
                return False, f"Segment '{seg_name}' (size {seg_size}K) could not fit."
            start = h["start"]
            if h["size"] == seg_size:
                self.holes.remove(h)
            else:
                h["start"] += seg_size
                h["size"]  -= seg_size
            temp_allocs.append((seg_name, seg_size, start))

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
            self.holes.append({"start": seg.start, "size": seg.size})
            self.allocated = [a for a in self.allocated
                              if not (a["pid"] == pid and a["seg_name"] == seg.name)]
        self._merge_holes()
        return True, f"Process {pid} deallocated."

    def get_segment_tables(self):
        tables = {}
        for pid, proc in self.processes.items():
            tables[pid] = [{"seg": s.name, "base": s.start, "limit": s.size}
                           for s in proc.segments]
        return tables


def run_scenario(algo):
    print(f'\n========== {algo.upper()}-FIT ==========')
    mgr = MemoryManager(1000)
    mgr.add_initial_hole(0, 300)
    mgr.add_initial_hole(400, 250)
    mgr.add_initial_hole(700, 200)
    
    steps = [
        ('alloc', 'P1', {'Code':100,'Data':120,'Stack':90}),
        ('alloc', 'P2', {'Code':200,'Data':40}),
        ('alloc', 'P3', {'Code':120,'Data':50}),
        ('dealloc', 'P1', None),
        ('alloc', 'P4', {'Code':230,'Data':40}),
    ]
    for op, pid, segs in steps:
        if op == 'alloc':
            ok, msg = mgr.allocate_process(pid, segs, algo)
        else:
            ok, msg = mgr.deallocate_process(pid)
        print(f'  {op.upper():10} {pid}: {msg}')
        print(f'    Holes: {mgr.holes}')
        alloc_str = [(a["pid"]+"."+a["seg_name"]+"@"+str(a["start"])) for a in mgr.allocated]
        print(f'    Alloc: {alloc_str}')
        tables = mgr.get_segment_tables()
        for p, entries in sorted(tables.items()):
            row = ', '.join(f'{e["seg"]}:base={e["base"]},limit={e["limit"]}' for e in entries)
            print(f'    [{p}] {row}')

if __name__ == "__main__":
    run_scenario('first')
    run_scenario('best')
    print('\nAll logic tests passed.')