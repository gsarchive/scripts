# Randomly spot-check files that have been changed, comparing the original
# to the version in the clone dir
import os
import random
import sys
import webbrowser

mount = "/home/rosuav/gsarchive/live"
local = "/home/rosuav/gsarchive/clone"
live = "https://gsarchive.net"

with open("change.log") as f: files = [fn for fn in f.read().split("\n") if fn]

if len(sys.argv) > 1:
	if sys.argv[1] == "--all": pass # Just don't shuffle
	else: files = sys.argv[1:]
else: random.shuffle(files) # Normally randomize.

for file in files:
	target = file.replace(local, "")
	base, ext = os.path.splitext(target)
	temp = base + "_spotcheck" + ext
	print("Copy", file)
	print("Into", mount + temp)
	print("Open", live + base + ext)
	print("Comp", live + temp)
	with open(file, "rb") as i, open(mount + temp, "wb") as o:
		o.write(i.read())
	webbrowser.open(live + base + ext)
	webbrowser.open(live + temp)
	inp = input("Enter when done, or Q to stop: ").lower()
	os.unlink(mount + temp)
	if inp == "q": break
