import subprocess

subprocess.run(
    "python3 TBG.py & python3 merchant.py & python3 karl.py", shell=True)
