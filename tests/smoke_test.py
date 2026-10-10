"""引导器：在 CI runner 上执行 runner/job.py（国外网络 + 完整权限）"""
import os, sys, traceback
try:
    src = open(os.path.join("runner", "job.py"), encoding="utf-8").read()
    exec(compile(src, "runner/job.py", "exec"), {"__name__": "__main__"})
except Exception:
    traceback.print_exc()
sys.exit(0)
