# ... the weasel (WEISEL!)
# Locate all JS links and categorize them
# - Empty <a href="JAVASCRIPT:">
# - Void <a ...></a>
# - openPopImg(image, title, width, height)
# - Other/Unknown
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

def find_popup_args(expr):
	"""Recursively scan an expression for an openPop* call"""
	match expr:
		case esprima.nodes.ExpressionStatement(expression=e):
			return find_popup_args(e)
		case esprima.nodes.CallExpression(callee=callee, arguments=args):
			if callee.type == "Identifier" and callee.name.startswith("openPop"):
				return callee.name, [
					# TODO: Understand other types of arg
					# For now assumes type == "Literal"
					a.value
					for a in args
				]
		case esprima.nodes.Node(body=[*body]):
			# Anything that has a body, scan for any matching things
			for elem in body:
				if a := find_popup_args(elem): return a
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
	fn, args = find_popup_args(expr)
	if fn:
		return info | {"type": fn + ", %d args" % len(args)}
	return info | {"type": "Unknown"}

stats = collections.Counter()
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
