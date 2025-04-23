from uuid import uuid4
from sys import argv
from os import path
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
shutil.copy(fp, path.join(path.dirname(fp), "resources", f"{fid}"))
with open(path.join(path.dirname(fp), "mapping.json"), "r") as f:
    mapping = load(f)
mapping[fn] = fid
with open(path.join(path.dirname(argv[1]), "mapping.json"), "w") as f:
    dump(mapping, f)
print(f"File {fid} added successfully")