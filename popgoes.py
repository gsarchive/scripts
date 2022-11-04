# ... the weasel (WEISEL!)
# Locate all JS links and categorize them
# - Void <a ...></a>
# - Empty <a href="JAVASCRIPT:"> or Semicolon <a href="JAVASCRIPT:;">
# - window.close()
# - openPopImg(image, title, width, height)
# - openPopWin(url, width, height[, features[, width, height]])
# - Other/Unknown
#
# Also classifies the onmouseover and onmouseout attributes, if present
# - setStatus() - delete this, the HTML spec requires that it be useless
# - this.className = "on/off" - delete this as the CSS styles have now been
#   applied to the class instead
# - MM_nbGroup
# - Other/Unknown
#
# TODO: Also classify <script> elements. Most likely, there will be a small
# number of unique texts across the entire site. Enumerate them. Show their
# language attributes as extra clues to their uselessness.
#
# Eventually, write back with changes:
# - Void links get excised
# - onmouseover/onmouseout setStatus and className get dropped
# - If class="off", del elem["class"]
# - openPopImg --> <a href=image title=title class=popup>
# - openPopWin --> ???
# - Otherwise retain as-is
# If adding any class=popup, ensure presence of both CSS and JS in head
# (see copywrong.py write_back())

import os
import sys
import re
import collections
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote, ParseResult
import esprima # ImportError? pip install -r requirements.txt

# root = "/home/rosuav/gsarchive/live"
root = "/home/rosuav/gsarchive/clone"

JS_FORMATS = {
	"*Blank": "^$",
	"Close window": r"^window.close\(\)$",
	"*Status - clear": r"^(return)?\s*setStatus\(''\)$",
	"*Status - enlarge": r"^(return)?\s*setStatus\('Click\s*to\s*enlarge\s*picture.'\)$",
	"*Status - other": r"^(return)?\s*setStatus\(.*\)$",
	"*Hover CSS class": r"^this\.className\s*=\s*'(on|off)';?$",
}
for id, regex in JS_FORMATS.items():
	JS_FORMATS[id] = re.compile(regex, re.IGNORECASE | re.VERBOSE | re.DOTALL)

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

def find_func_args(expr, fnprefix):
	"""Recursively scan an expression for an openPop* call"""
	match expr:
		case esprima.nodes.ExpressionStatement(expression=e):
			return find_func_args(e, fnprefix)
		case esprima.nodes.CallExpression(callee=callee, arguments=args):
			if callee.type == "Identifier" and callee.name.startswith(fnprefix):
				return callee.name, [
					# TODO: Understand other types of arg
					# For now assumes type == "Literal"
					a.value
					for a in args
				]
		case esprima.nodes.Node(body=[*body]):
			# Anything that has a body, scan for any matching things
			for elem in body:
				if a := find_func_args(elem, fnprefix): return a
	# Otherwise, we got nuffin'.
	return None, None

def classify_link(elem, js):
	info = {"attrs": ",".join(sorted(elem.attrs))}
	for id, regex in JS_FORMATS.items():
		if regex.match(js): return info | {"type": id}
	with ExceptionContext("JS code", js):
		expr = esprima.parse(js)
	# TODO: Recognize if there's any other code here (unlikely but possible)
	fn, args = find_func_args(expr, "openPop")
	if fn: return info | {"type": fn}
	return info | {"type": "Unknown"}

def classify_hover(elem, js):
	for id, regex in JS_FORMATS.items():
		if regex.match(js): return {"type": id}
	# esprima doesn't like a bare return statement. I'm not entirely sure how this is meant
	# to be interpreted, but I'm wrapping it in a special function and then getting the body
	# of that function.
	with ExceptionContext("JS code", js):
		module = esprima.parse("function _probe() {" + js + "}")
		assert module.type == "Program"
		assert module.body[0].type == "FunctionDeclaration"
		expr = module.body[0].body # The body of the function we just defined
	fn, args = find_func_args(expr, "MM_nbGroup")
	if fn: return {"type": fn}
	fn, args = find_func_args(expr, "MM_swap")
	if fn: return {"type": fn}
	return {"type": "Unknown", "js": str(expr)}

stats = collections.Counter()
hovers = collections.Counter()
def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	changed = False
	for elem in soup.find_all("a", href=True):
		with ExceptionContext("Element", elem):
			if not elem.contents and not elem.text:
				# Unclickable as it has no content
				elem.replace_with("")
				changed = True
				stats["Void"] += 1
				continue
			p = urlparse(elem["href"])
			if p.scheme.lower() == "javascript":
				# When a question mark appears in the JS, browsers actually interpret it
				# as the beginning of query parameters, as the apostrophe does not quote
				# it. For our purposes, though, it's cleaner to simply rejoin that.
				js = p.path
				if p.query: js += "?" + p.query
				info = classify_link(elem, js)
				ty = info["type"] + " [" + info["attrs"] + "]"
				if ty not in stats:
					print(ty, fn)
				stats[ty] += 1
			for attr in ("onclick", "onmouseover", "onmouseout"):
				if attr not in elem.attrs: continue
				info = classify_hover(elem, elem[attr])
				if info["type"] == "Unknown":
					print("Unknown JS:", fn, elem[attr])
				elif info["type"] not in hovers:
					print("JS:", info["type"], fn)
				hovers[info["type"]] += 1
				if info["type"][0] == "*":
					# Unnecessary JavaScript - take it out.
					del elem[attr]
					changed = True
			if "class" in elem.attrs and elem["class"] in ("", "off", "on"):
				del elem["class"]
				changed = True
	if changed:
		data = soup.encode(formatter="html5")
		with open(fn, "wb") as f: f.write(data)
		stats["Changed"] += 1

for fn in sys.argv[1:]:
	if os.path.exists(fn):
		with ExceptionContext("File name", fn): classify(fn)
		print(stats.total(), stats)
		sys.exit(0)

with open("weasels.log", "w") as log:
	for root, dirs, files in os.walk(root):
		if "backups" in dirs: dirs.remove("backups")
		for file in files:
			if not file.endswith(".html") and not file.endswith(".htm"): continue
			fn = os.path.join(root, file)
			with ExceptionContext("File name", fn):
				classify(fn)
print(stats.total(), stats)
print(hovers.total(), hovers)
