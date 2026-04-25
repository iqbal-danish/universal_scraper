import os, subprocess
import sys
os.makedirs("logs/runs", exist_ok=True)
os.makedirs("output", exist_ok=True)
print("Starting Advanced Scraper...")
subprocess.call([sys.executable, "-m", "dashboard.app"])
