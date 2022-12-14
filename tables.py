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
changes = open("change.log", "w")
def report(*msg):
	print(json.dumps(msg), file=logfile)
	print(*msg)

stats = collections.Counter()

def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	changed = need_gsa_css = False
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
				# Particularly if it has a caption, implying that it is really a figure in disguise.
				if caption:
					changed = need_gsa_css = True
					# Generate some new HTML elements and patch in the necessary information.
					# If the table caption is aligned bottom, the figure caption goes at the end,
					# rather than at the beginning. (We're ignoring left/right captions, which
					# don't occur on the G&S Archive.)
					figure = [
						"""<figure class="inlinefig"><figcaption></figcaption><div></div></figure>""",
						"""<figure class="inlinefig"><div></div><figcaption></figcaption></figure>""",
					][caption.get("align") == "bottom"]
					figure = BeautifulSoup(figure, "html.parser").figure
					# Check whether it's left or right floated (or neither)
					side = table.get("align", "").lower()
					if side in ("left", "right"): figure["class"] += [side]
					# Check cellpadding (needs to become pixel padding on the pictureframe)
					# The default is 1px, but for consistency, we'll just have either
					# none or 5px. Since there's currently a big mess, we take any padding
					# of at least 3px and make it 5px (even if it was 8px), otherwise none.
					padding = int(table.get("cellpadding", "1"))
					if padding >= 3: figure["class"] += ["padded"]
					# Retain any element styles from the table on the figure
					if tbsty := table.get("style"): figure["style"] = tbsty
					# Retain CSS classes from table on the inner div, and caption similarly
					figure.div["class"] = table.get("class", [])
					figure.figcaption["class"] = caption.get("class", [])
					# What was in the table cell now goes in the div; caption is still caption.
					figure.div.extend(data)
					figure.figcaption.extend(caption)
					# Perfect. Let's swap that in!
					table.replace_with(figure)
					stats["FiguresChanged"] += 1
				else:
					stats["Single-cell"] += 1
					report(fn, "Table has only one cell") # "".join(str(c) for c in data.children)
			elif caption:
				stats["Caption"] += 1
				report(fn, "Table caption:", "".join(str(c) for c in table.caption.children))
	if changed:
		if need_gsa_css and not soup.find("link", href="/styles/gsarchive.css"):
			soup.head.append(BeautifulSoup('<link href="/styles/gsarchive.css" rel="stylesheet" type="text/css">', "html.parser"))
		data = soup.encode(formatter="html5")
		with open(fn, "wb") as f: f.write(data)
		stats["Changed"] += 1
		print(fn, file=changes)

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
