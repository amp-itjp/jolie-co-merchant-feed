"""Structured run log shared by the feed scripts. Written for the future app UI (Runs screen).

Files written to $RUN_LOG_DIR (default ./logs):
  events.jsonl  one JSON object per line: time, step, level (info|warn|error), message, plus any extra fields
  run.json      run summary: run_id, shop, trigger, start/finish, status, and one entry per step with counts

Usage in a script:
    from runlog import Step
    with Step("build_primary", shop="jolie-je.myshopify.com") as s:
        s.info("reading catalog", file=path)
        s.warn("81 rows missing material", field="material", missing=81)
        s.count(variants=16193)
A SystemExit with a message, or any exception, marks the step failed and is re-raised.
`python3 tools/runlog.py finalize` (run it even after failures) sets the overall run status.
`python3 tools/runlog.py run <step name> <command...>` runs any script as a logged step: each output line becomes an
info event, and a non-zero exit marks the step failed.
"""
import datetime, json, os, sys

LOG_DIR = os.environ.get("RUN_LOG_DIR", "logs")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _read_summary():
    try:
        return json.load(open(os.path.join(LOG_DIR, "run.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {"run_id": os.environ.get("GITHUB_RUN_ID") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                "trigger": os.environ.get("GITHUB_EVENT_NAME", "manual"), "started_at": _now(), "status": "running", "steps": []}


def _write_summary(summary):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "run.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


class Step:
    def __init__(self, name, shop=""):
        self.name, self.shop, self.counts, self.warnings = name, shop, {}, 0

    def _emit(self, level, message, **extra):
        os.makedirs(LOG_DIR, exist_ok=True)
        rec = {"time": _now(), "step": self.name, "level": level, "message": message, **extra}
        with open(os.path.join(LOG_DIR, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{level}] {self.name}: {message}")

    def info(self, message, **extra): self._emit("info", message, **extra)

    def warn(self, message, **extra):
        self.warnings += 1
        self._emit("warn", message, **extra)

    def count(self, **kw): self.counts.update(kw)

    def __enter__(self):
        self.started = _now()
        s = _read_summary()
        if self.shop:
            s["shop"] = self.shop
        _write_summary(s)
        self._emit("info", "step started")
        return self

    def __exit__(self, exc_type, exc, tb):
        status, error = "success", ""
        if exc_type is SystemExit and exc.code in (0, None):
            pass
        elif exc_type is not None:
            status = "failed"
            error = str(exc.code) if exc_type is SystemExit else f"{exc_type.__name__}: {exc}"
            self._emit("error", error)
        s = _read_summary()
        start = datetime.datetime.fromisoformat(self.started)
        s["steps"].append({"name": self.name, "status": status, "started_at": self.started, "finished_at": _now(),
                           "duration_s": round((datetime.datetime.now(datetime.timezone.utc) - start).total_seconds(), 1),
                           "warnings": self.warnings, "counts": self.counts, "error": error})
        _write_summary(s)
        self._emit("info" if status == "success" else "error", f"step {status}", **self.counts)
        return False


def finalize():
    s = _read_summary()
    failed = any(x["status"] == "failed" for x in s["steps"])
    s["status"] = "failed" if failed or not s["steps"] else ("warning" if any(x["warnings"] for x in s["steps"]) else "success")
    s["finished_at"] = _now()
    _write_summary(s)
    print(f"run {s['run_id']}: {s['status']}")


def run(name, cmd):
    import subprocess
    with Step(name, shop=os.environ.get("SHOP", "jolie-je.myshopify.com")) as s:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in p.stdout:
            if line.strip():
                s.info(line.rstrip()[:500])
        if p.wait():
            raise SystemExit(f"command exited with code {p.returncode}")


if __name__ == "__main__":
    if sys.argv[1:] == ["finalize"]:
        finalize()
    elif len(sys.argv) > 3 and sys.argv[1] == "run":
        try:
            run(sys.argv[2], sys.argv[3:])
        except SystemExit as e:
            sys.exit(1 if e.code else 0)
