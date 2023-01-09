# Find all files where a table is used purely for formatting.
# For every table, identify its contents, and match against some known patterns.
# 1) Single row with single cell, containing an image or text: should become boxed text
# 1a) As above but has a <caption>: should become <figure> with <figcaption>
# 2) Three rows:
#    a) Corner left + Background + Corner Right
#    b) Empty with background
#    c) Gold, cream, CONTENT, cream, gold
#    Should become <main>
# 3) "Other"

import json
import os
import pprint
import sys
import re
import hashlib
import collections
from bs4 import BeautifulSoup, Comment
from urllib.parse import urlparse, urljoin, unquote, ParseResult

# root = "/home/rosuav/gsarchive/live"
root = "/home/rosuav/gsarchive/clone"

class ExceptionContext:
	def __init__(self, label, ctx):
		self.label = label; self.ctx = ctx
	def __enter__(self): return self
	def __exit__(self, t, v, c):
		if not t: return
		try: v.context
		except AttributeError: v.context = { }
		v.context[self.label] = self.ctx

_old_excepthook = sys.excepthook
def report_with_context(t, v, c):
	try:
		for lbl, ctx in reversed(v.context.items()):
			print(lbl + ":", ctx)
	except AttributeError: pass
	_old_excepthook(t, v, c)
sys.excepthook = report_with_context

logfile = open("tables.log", "w")
def report(*msg):
	print(json.dumps(msg), file=logfile)
	print(*msg)

stats = collections.Counter()

def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	changed = False
	for table in soup.find_all("table"):
		with ExceptionContext("Table", table):
			rows = []
			for tr in table.find_all("tr"):
				tb = tr.find_parent("table")
				if tb is not table: continue # Probably nested tables
				# Attempt to count the cells in this row by assuming that they are
				# its immediate children, and are TDs and/or THs.
				cells = list(tr.find_all("td", recursive=False)) + list(tr.find_all("th", recursive=False))
				# Note that this ignores colspan/rowspan
				rows.append(len(cells))
				if len(cells) == 1:
					data = cells[0]
			# Does the table contain a caption? If one exists, it is supposed to be
			# the first child of the <table> element itself, but we're being a bit
			# more flexible, and just making sure it isn't a child of an inner table.
			caption = table.caption
			if caption and caption.find_parent("table") is not table: caption = None
			# So, what's worth reporting?
			# A table containing a single row with a single cell in it is notable.
			if rows == [1]:
				if caption:
					last = caption.get("align") == "bottom" # figcaption should be last instead of first
					# Check whether it's left or right floated (or neither)
					side = table.get("align", "").lower()
					if side not in ("left", "right"): side = ""
					# Check cellpadding (needs to become pixel padding on the pictureframe)
					# The default is 1px, but for consistency, we'll just have either
					# none or 5px. Since there's currently a big mess, we take any padding
					# of at least 3px and make it 5px (even if it was 8px), otherwise none.
					padding = int(table.get("cellpadding", "1")) >= 3
					# Retain CSS classes on table (becomes div) and caption (becomes figcaption)
					tbcls = table.get("class", [])
					capcls = caption.get("class", [])
					# Retain any element styles on the table (becomes figure)
					tbsty = table.get("style")
					report(fn, "Figure table:",
						last, side, padding, tbcls, capcls,
						tbsty,
						#repr("".join(str(c) for c in data.children)),
						#repr("".join(str(c) for c in caption.children)),
					)
					stats["FigLast %s" % last] += 1
					stats["FigSide %s" % side] += 1
					stats["FigPadding %s" % padding] += 1
				#else: print(fn, "Table has only one cell:", repr("".join(str(c) for c in data.children)))
			#elif caption:
			#	print(fn, "Table caption:", repr("".join(str(c) for c in table.caption.children)))
	if changed:
		data = soup.encode(formatter="html5")
		with open(fn, "wb") as f: f.write(data)
		stats["Changed"] += 1

for fn in sys.argv[1:]:
	if os.path.exists(fn):
		with ExceptionContext("File name", fn): classify(fn)
		break
else:
	for root, dirs, files in os.walk(root):
		if "backups" in dirs: dirs.remove("backups")
		for file in files:
			if not file.endswith(".html") and not file.endswith(".htm"): continue
			fn = os.path.join(root, file)
			with ExceptionContext("File name", fn):
				classify(fn)

print(stats.total(), stats)
pprint.pprint(stats)
