# ... the weasel (WEISEL!)
# Locate all JS links and categorize them
# - Void <a ...></a>
# - Empty <a href="JAVASCRIPT:"> or Semicolon <a href="JAVASCRIPT:;">
# - window.close()
# - openPopImg(image, title, width, height)
# - openPopWin(url, width, height[, features[, width, height]])
# - Other/Unknown
#
# TODO: Classify the onmouseover and onmouseout attributes, if present
# - setStatus() - delete this, the HTML spec requires that it be useless
# - MM_nbGroup
# - Other/Unknown
#
# Eventually, write back with changes:
# - Void links get excised
# - onmouseover/onmouseout setStatus get dropped
# - openPopImg --> <a href=image title=title class=popup>
# - openPopWin --> ???
# - Otherwise retain as-is
# If adding any class=popup, ensure presence of both CSS and JS in head
# (see copywrong.py write_back())

import os
import sys
import collections
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote, ParseResult
import esprima # ImportError? pip install -r requirements.txt

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
	if not elem.contents and not elem.text: info["void"] = True # Unclickable as it has no content
	if not js: return info | {"type": "Blank"}
	if js == ";": return info | {"type": "Semicolon"} # Practically blank, but show it separately for stats
	if js == "window.close()": return info | {"type": "Close window"}
	with ExceptionContext("JS code", js):
		expr = esprima.parse(js)
	fn, args = find_func_args(expr, "openPop")
	if fn:
		return info | {"type": fn}
	return info | {"type": "Unknown"}

def classify_hover(elem, js):
	if js == "return setStatus('')": return {"type": "Status - clear"}
	# esprima doesn't like a bare return statement. I'm not entirely sure how this is meant
	# to be interpreted, but I'm wrapping it in a special function and then getting the body
	# of that function.
	with ExceptionContext("JS code", js):
		module = esprima.parse("function _probe() {" + js + "}")
		assert module.type == "Program"
		assert module.body[0].type == "FunctionDeclaration"
		expr = module.body[0].body # The body of the function we just defined
	fn, args = find_func_args(expr, "setStatus")
	if fn:
		if args[0] == "": return {"type": "Status - clear"}
		if args[0] == "Click to enlarge picture.": return {"type": "Status - enlarge"}
		return {"type": "Status - other"}
	return {"type": "Unknown"}

stats = collections.Counter()
hovers = collections.Counter()
def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	for elem in soup.find_all("a", href=True):
		with ExceptionContext("Element", elem):
			p = urlparse(elem["href"])
			if p.scheme.lower() == "javascript":
				# When a question mark appears in the JS, browsers actually interpret it
				# as the beginning of query parameters, as the apostrophe does not quote
				# it. For our purposes, though, it's cleaner to simply rejoin that.
				js = p.path
				if p.query: js += "?" + p.query
				info = classify_link(elem, js)
				ty = "Void" if "Void" in stats else info["type"] + " [" + info["attrs"] + "]"
				if ty not in stats:
					print(ty, fn)
				stats[ty] += 1
			for attr in ("onmouseover", "onmouseout"):
				if attr not in elem.attrs: continue
				info = classify_hover(elem, elem[attr])
				if info["type"] not in hovers:
					print("Hover:", info["type"], fn)
				hovers[info["type"]] += 1

for fn in sys.argv[1:]:
	if os.path.exists(fn):
		with ExceptionContext("File name", fn): classify(fn)
		print(stats.total(), stats)
		sys.exit(0)

next_report = 100
with open("weasels.log", "w") as log:
	for root, dirs, files in os.walk(root):
		if "backups" in dirs: dirs.remove("backups")
		for file in files:
			if not file.endswith(".html") and not file.endswith(".htm"): continue
			fn = os.path.join(root, file)
			with ExceptionContext("File name", fn):
				classify(fn)
			if stats.total() > next_report:
				print(stats.total(), stats)
				next_report = (stats.total() // 100 + 1) * 100
print(stats.total(), stats)
print(hovers.total(), hovers)
