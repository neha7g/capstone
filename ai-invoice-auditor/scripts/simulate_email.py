"""Simulate invoice emails arriving: copies data/samples -> data/incoming one by one (run on the host)."""
import os
import shutil
import time

SOURCE, TARGET = "data/samples/", "data/incoming/"
for f in sorted(os.listdir(SOURCE)):
    if f.endswith((".pdf", ".docx", ".png", ".meta.json")):
        shutil.copy(os.path.join(SOURCE, f), TARGET)
        print(f"Simulated email arrival: {f}")
        time.sleep(15)
