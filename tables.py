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
					][caption.get("align", "").lower() == "bottom"]
					figure = BeautifulSoup(figure, "html.parser").figure
					# Check whether it's left or right floated (or neither)
					side = table.get("align", "").lower()
					if side in ("left", "right", "center"): figure["class"] += [side]
					# Check cellpadding (needs to become pixel padding on the pictureframe)
					# The default is 1px, but for consistency, we'll just have either
					# none or 5px. Since there's currently a big mess, we take any padding
					# of at least 3px and make it 5px (even if it was 8px), otherwise none.
					padding = int(table.get("cellpadding", "1"))
					if padding >= 3: figure["class"] += ["padded"]
					# Retain any element styles from the table
					if tbsty := table.get("style"):
						# Most of these styles go on the figure (eg margin), but a border
						# belongs on the div instead.
						if tbsty.startswith("border:"):
							# Any time there's a border with something else, the border
							# is listed first. So we cheat a bit on the parsing.
							figure.div["style"], _, tbsty = tbsty.partition(";")
						figure["style"] = tbsty.strip()
					# Retain CSS classes from table on the inner div, and caption similarly
					if cls := table.get("class", []) + table.td.get("class", []):
						figure.div["class"] = cls
					if cls := caption.get("class", []): figure.figcaption["class"] = cls
					# If the table had a big fat border on it, that now belongs on the div.
					if border := int(table.get("border", "0")):
						if "pictureframe" not in figure.div.get("class", []):
							# The pictureframe class adds its own border
							figure.div["style"] = "border: %dpx outset grey; padding: 2px" % border
						stats["FiguresBorders"] += 1
					# Not sure whether these should be transformed in this way, but let's try it.
					# Is there a better way to combine arbitrary CSS blocks? Probably not, since
					# this really isn't something you should be doing a lot of... Also, very few
					# of these actually need to be edited, so there's a specific list.
					if width := table.get("width"):
						if fn.replace(root, "") in (
							"/carte/savoy/theatre.html",
							"/newsletters/trumpet_bray/html/tb22_8.html",
							"/newsletters/trumpet_bray/html/tb22_9.html",
							"/newsletters/trumpet_bray/html/tb23_1.html",
						):
							sty = figure.get("style")
							if sty: sty += "; width: " + width
							else: sty = "width: " + width
							figure["style"] = sty
							stats["FiguresWidth"] += 1
					# What was in the table cell now goes in the div; caption is still caption.
					figure.div.extend(data)
					figure.figcaption.extend(caption)
					# Perfect. Let's swap that in!
					table.replace_with(figure)
					stats["FiguresChanged"] += 1
				else:
					# Possibly just adding a border to one element
					stats["Single-cell"] += 1
					# report(fn, "Table has only one cell") # "".join(str(c) for c in data.children)
			elif caption:
				stats["Caption"] += 1
				# report(fn, "Table caption:", "".join(str(c) for c in table.caption.children))
			elif rows == [3, 1, 5]:
				# This might be a <main> in disguise.
				# Ignoring any NavigableStrings that are just whitespace, there should be
				# a tbody (always) containing three rows. The first row has a cell with
				# an image whose name is "left.gif", etc, etc, etc. Match VERY strictly.
				stats["3-1-5"] += 1
				# report(fn, "3-1-5 table")
				children = ""
				for child in table.tbody.children:
					if isinstance(child, str) and child.strip() == "": continue
					children += ":" + child.name
				stats["3-1-5-child" + children] += 1
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
	for base, dirs, files in os.walk(root):
		if "backups" in dirs: dirs.remove("backups")
		for file in files:
			if not file.endswith(".html") and not file.endswith(".htm"): continue
			fn = os.path.join(base, file)
			with ExceptionContext("File name", fn):
				classify(fn)

print(stats.total(), stats)
pprint.pprint(stats)
