# Reset all changed files from the live originals. Should be equivalent to
# recloning the entire directory, but if only a few files have changed, faster.
import sys

mount = "/home/rosuav/gsarchive/live"
local = "/home/rosuav/gsarchive/clone"

with open("change.log") as f: files = [fn for fn in f.read().split("\n") if fn]

if len(sys.argv) > 1: files = sys.argv[1:]

for file in files:
	print(file)
	with open(file.replace(local, mount), "rb") as i, open(file, "wb") as o:
		o.write(i.read())
