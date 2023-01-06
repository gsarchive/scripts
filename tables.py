# Find all files where a table is inside another table.
# When tables are used for formatting, this is very common; when they're used for
# actual tabular data, it is quite rare.
# For each nested table, show the row and column count for both outer and inner.
# In some cases, the outer table should be replaced with a <main> (as its sole purpose is
# a curved border); in others, it's the inner table which is the pure-formatting element.

import os
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

stats = collections.Counter()

def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	changed = False
	for elem in soup.find_all("table"):
		with ExceptionContext("Table", elem):
			parent = elem.find_parent("table")
			if not parent: continue # Table not in a table, nothing to fix
			with ExceptionContext("Contained in", parent):
				# This is inefficient; for every table-in-table, it fully
				# recalculates the dimensions of both tables. It should be
				# possible to recall the outer table's dimensions if we've
				# already seen it. Whatever.
				container = []; child = []
				for tr in parent.find_all("tr"):
					tb = tr.find_parent("table")
					# Attempt to count the cells in this row by assuming that they are
					# its immediate children, and are TDs and/or THs.
					cells = len(tr.find_all("td", recursive=False)) + len(tr.find_all("th", recursive=False))
					if tb is parent: container.append(cells)
					elif tb is elem: child.append(cells)
					# Else it's a triple-nested table and we'll get to it later.
				# So, what's worth reporting?
				# A table containing a single row is notable.
				if len(container) == 1:
					print(fn, "Container table has only one row", container[0], child)
				# Though all nested tables should be reported.
				else:
					print(fn, "Table inside table - cell counts:", container, child)
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
