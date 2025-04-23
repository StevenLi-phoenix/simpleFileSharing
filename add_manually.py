from uuid import uuid4
from sys import argv
from os import path, getcwd, makedirs
import shutil
from json import load, dump

if len(argv) != 2:
    print("Warn: Usage: python add_manually.py <path_to_file>")
    fp = input("Or Enter to <path_to_file> now:")
    exit(1)
else:
    fp = argv[1]
fid = str(uuid4())
fn = path.basename(fp)
cwd = getcwd()
makedirs(path.join(cwd, "resources"), exist_ok=True)
shutil.copy(fp, path.join(cwd, "resources", fid))
with open(path.join(cwd, "mapping.json"), "r") as f:
    mapping = load(f)
mapping[fid] = fn
with open(path.join(cwd, "mapping.json"), "w") as f:
    dump(mapping, f)
print(f"File {fid} added successfully")