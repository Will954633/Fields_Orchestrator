import os, time, importlib.util
spec=importlib.util.spec_from_file_location("lmc","launch_messenger_carousel.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
orig=m._call
def patched(method, path, **fields):
    for attempt in range(9):
        try: return orig(method, path, **fields)
        except RuntimeError as e:
            if '"code": 17' in str(e):
                w=(attempt+1)*60; print(f"  rate-limited, backoff {w}s", flush=True); time.sleep(w); continue
            raise
    raise RuntimeError("gave up after backoff")
m._call=patched
m.build()   # reuses A & B (have ad_id), builds only C
