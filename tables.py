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

footer = """<footer>
<hr align="center" width="95%" noshade>
<p class="copyright"><a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png"></a>
 This work is licensed under a <BR> <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.</p>
</footer>
"""

def next_element_sibling(basis):
	for elem in basis.next_siblings:
		if elem.name: return elem

def get_child_nodes(node):
	return [child for child in node.children if not isinstance(child, str) or child.strip()]

def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	changed = need_gsa_css = False
	# When we're done, the left/right corner GIFs shouldn't ever be needed. Note that
	# this is pre-edit stats, so if any files are edited in this pass, they may show
	# spuriously here.
	if "/left.gif" in str(blob) or "/right.gif" in str(blob):
		if soup.main:
			# This normally shouldn't happen; it implies that a page has been edited,
			# but still makes use of one of the corner GIFs.
			report(fn, "Has main, still uses left/right GIF")
			stats["Has main, still uses left/right GIF"] += 1
		else:
			#report(fn, "No main, left/right GIF used")
			stats["No main, left/right GIF used"] += 1
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
					# It could be the G&S Archive masthead; it could be a show-specific emblem;
					# any others? List them here.
					childnodes = get_child_nodes(data)
					if len(childnodes) == 1:
						if data.text.strip() == "Gilbert and Sullivan Archive":
							if isinstance(childnodes[0], str):
								stats["Archive masthead"] += 1
								report(fn, "Archive masthead")
							elif childnodes[0].name in ("a", "div"):
								c = get_child_nodes(childnodes[0])
								if len(c) == 1 and isinstance(c[0], str):
									# Treat this the same as the regular masthead, but
									# if there are any CSS classes on c[0], add them
									# to the result. Note that this may need to be
									# spot-checked separately.
									stats["Archive masthead:" + childnodes[0].name] += 1
									report(fn, "Archive masthead")
								else:
									children = ",".join(c.name for c in c)
									stats["Archive masthead, wrapped:%s:%s" % (childnodes[0].name, children)] += 1
									report(fn, "Archive masthead, multi-level", childnodes[0].name, children)
							else:
								stats["Archive masthead, wrapped:%s" % childnodes[0].name] += 1
								report(fn, "Probable unrecognized masthead", childnodes[0].name)
						elif "Gilbert and Sullivan Archive" in data.text:
							stats["Combined masthead"] += 1
							report(fn, "Possible combined masthead")
						elif childnodes[0].name == "img":
							stats["Image masthead"] += 1
							report(fn, "Image masthead")
						else:
							stats["Unknown single-element single-cell"] += 1
							report(fn, "Unknown single-el")
					else:
						stats["Single-cell:%s" % table.get("align")] += 1
						report(fn, "Table has only one cell", table.get("align"), len(childnodes)) # "".join(str(c) for c in data.children)
			elif caption:
				stats["Caption"] += 1
				# report(fn, "Table caption:", "".join(str(c) for c in table.caption.children))
			elif rows == [3, 1, 5] or rows == [3, 5]:
				# This might be a <main> in disguise.
				# Ignoring any NavigableStrings that are just whitespace, there should be
				# a tbody (always) containing three rows. The first row has a cell with
				# an image whose name is "left.gif", etc, etc, etc. Match VERY strictly.
				stats["3-1-5"] += 1
				# report(fn, "3-1-5 table")
				children = ""
				for tr in table.tbody.children:
					if tr.name != "tr": continue
					desc = []
					for td in tr.children:
						if isinstance(td, str) and td.strip() == "": continue
						# Find all non-empty children
						childnodes = [child.name for child in td.children if not isinstance(child, str) or child.strip()]
						# For each cell, categorize it.
						if (td.img and "left.gif" in td.img["src"] and
							td["colspan"] == "2" and (rows == [3, 5] or td["rowspan"] == "2")):
								desc.append("TL") # Top-Left
						elif (td.img and "right.gif" in td.img["src"] and
							td["colspan"] == "2" and (rows == [3, 5] or td["rowspan"] == "2")):
								desc.append("TR") # Top-Right
						elif not childnodes:
							# Empty cells, some of which can be further sub-categorized
							if (
								"gold.gif" in td.get("background", "")
								or "top.gif" in td.get("background", "")
								or td.get("bgcolor") in ("#cece99", "#cece9c")
							):
								desc.append("B") # Border
							elif "cream.gif" in td.get("background", "") or td.get("bgcolor") == "#feffe6":
								desc.append("G") # Gap, cream
							elif td.get("bgcolor") == "#000000":
								desc.append("G") # Gap, black (not functionally different but may require logging)
							else:
								desc.append("0") # Empty
								report(fn, "Empty cell, bg %r bgcol %r" % (td.get("background"), td.get("bgcolor")))
						else:
							desc.append("Other")
							other_td = td # Don't reference this unless you've checked that there's an Other
					children += ":" + "-".join(desc)
				stats["3-1-5-child" + children] += 1
				if children in (":TL-B-TR:G:B-G-Other-G-B", ":TL-B-TR:B-G-Other-G-B", ":TL-B-TR:G:B-G-G-G-B"):
					# Sometimes, the 3-1-5 table is actually just the topmost section, and it is
					# followed by an outset table containing a heading banner, which is itself
					# followed by the main content, in another table. (And it'll most likely have
					# a standalone footer.)
					next = next_element_sibling(table)
					nextnext = next and next_element_sibling(next)
					if next and nextnext and next.name == "table" and nextnext.name == "table":
						# So.... three adjacent tables. What can we learn from them?
						widths = table.get("width"), next.get("width"), nextnext.get("width")
						if widths != ("700", "750", "700"):
							# Unknown widths (possibly absent) - log it for later
							report(fn, "Three tables, unknown", *widths)
							stats["Three-%s-%s-%s" % widths] += 1
							continue
						# Otherwise: It's an outset table with matching tables above/below.
						# The third table should have one row containing three cells.
						more_content = maybe_content = None
						for tr in nextnext.tbody.children:
							if tr.name != "tr": continue
							if maybe_content:
								# Sometimes there's an extra row with no content.
								no_content = True
								for td in tr.children:
									# If any of the TR's children isn't empty,
									# the entire row isn't empty.
									if isinstance(td, str) and not td.strip(): continue # Ignore random whitespace
									for child in td.children:
										if not isinstance(child, str) or child.strip():
											no_content = False
								if no_content: continue # All good, probably no issues here
								report(fn, "Three tables, last has extra row")
								stats["Extra row"] += 1
								break # Nope nope nope! Doesn't match.
							nodes = [td for td in tr.children if not isinstance(td, str)]
							if len(nodes) == 4:
								b1, maybe_content, gap, b2 = nodes
								gap = [td for td in gap.children if not isinstance(td, str) or td.strip()]
								if gap: break # The gap isn't empty, so it's not a gap
							elif len(nodes) == 3:
								b1, maybe_content, b2 = nodes
							else:
								stats["ThreeTB no-match: %d" % len(nodes)] += 1
								break
							b1 = [td for td in b1.children if not isinstance(td, str) or td.strip()]
							b2 = [td for td in b2.children if not isinstance(td, str) or td.strip()]
							if b1 or b2:
								# One of the borders isn't empty, so it's not a border.
								break
						else:
							more_content = maybe_content
						if not more_content:
							report(fn, "Three tables, last doesn't match")
							stats["ThreeTB no-match"] += 1
							continue
					else:
						# The thanks page is like the landing page, and needs a manual "width: 100%" added.
						# Other than that, it is just like a 3-1-5 table despite being inside another table.
						if not fn.endswith("/thanks.html") and \
								table is not max(soup.find_all("table"), key=lambda elem: len(str(elem))):
							report(fn, "Ignoring not-largest table")
							continue # Guard against editing ones we're not looking at
						next = None
					# Okay, we got what we need. Let's do this!
					changed = need_gsa_css = True
					if soup.footer: soup.footer.replace_with("") # We'll have a new footer inside main.
					main = soup.new_tag("main")
					if next:
						# Merge in the other two tables; also, since this should be narrowed,
						# stick a CSS class on the main and its banner.
						main["class"] = "narrow"
						if "Other" in children:
							# Wrap the top section in a div to give it a bit of padding
							top = soup.new_tag("div")
							top["class"] = "topmatter"
							top.extend(other_td)
							main.append(top)
						# The second table is the outset one; keep it as a table.
						next["class"] = "banner"
						main.append(next)
						# And the third table is the majority of the content.
						if more_content:
							main.extend(more_content)
							if "btext" in more_content.get("class", []):
								# stats["class=btext"] += 1
								main["class"] = "narrow padded"
							#else: stats["not btext"] += 1
						nextnext.replace_with("")
					elif "Other" in children: main.extend(other_td)
					main.append(BeautifulSoup(footer, "html5lib").footer)
					table.replace_with(main)
					report(fn, "Replaced table with main")
			else:
				if "/left.gif" in str(table) or "/right.gif" in str(table):
					report(fn, "Left/Right:" + "-".join(str(r) for r in rows))
					stats["Left/Right:" + "-".join(str(r) for r in rows)] += 1
				if "/corner_1_trans.gif" in str(table):
					report(fn, "Transparent corner:" + "-".join(str(r) for r in rows))
					stats["Transparent corner:" + "-".join(str(r) for r in rows)] += 1
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
