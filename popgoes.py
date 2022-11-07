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
# Also classifies <script> elements. Those relating to the lightbox script
# are removed and replaced with <a class=popup>. Junk and broken scripts are
# simply deleted. So far, openPopImg and openPopWin are kept.
#
# Writes back with changes:
# - Void links get excised
# - onmouseover/onmouseout setStatus and className get dropped
# - If class="off", del elem["class"]
# - openPopImg --> <a href=image title=title class=popup>
# - openPopWin --> ??? not changed as yet
# - Otherwise retain as-is
# If adding any class=popup, ensure presence of both CSS and JS in head
# (see copywrong.py write_back())

import os
import sys
import re
import hashlib
import collections
from bs4 import BeautifulSoup, Comment
from urllib.parse import urlparse, urljoin, unquote, ParseResult
import esprima # ImportError? pip install -r requirements.txt

# root = "/home/rosuav/gsarchive/live"
root = "/home/rosuav/gsarchive/clone"

JS_FORMATS = {
	"*Blank": "^$",
	"Close window": r"^(window.close\(\)|closePopWin\(\))$",
	"Fabricate": r"^fabricatePage\(\)$", # Only on pimg.htm
	"Slideshow": r"^(rotate\(\)|runSlideShow\(\))$",
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
	if fn: return info | {"type": fn, "args": args}
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
	for findme in ("MM_nbGroup", "MM_swap", "*MM_preloadImages", "*closePopImg"):
		fn, args = find_func_args(expr, findme.lstrip("*"))
		if fn: return {"type": findme}
	return {"type": "Unknown", "js": str(expr)}

def make_popup(elem):
	classes = elem.get("class")
	if classes is None: elem["class"] = "popup"
	elif "popup" not in classes: classes.append("popup")

unique_scripts = open("popgoes.log", "w")
scripts_seen = collections.Counter()

stats = collections.Counter()
hovers = collections.Counter()
comments = collections.Counter()

def check_hover(elem, *attrs):
	for attr in attrs:
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
			return True

def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	changed = need_gsa_script = False
	if soup.body and check_hover(soup.body, "onload", "onunload"): changed = True
	for elem in soup.find_all("a", href=True):
		with ExceptionContext("Element", elem):
			if not elem.contents and not elem.text:
				# Unclickable as it has no content
				elem.replace_with("")
				changed = True
				stats["Void"] += 1
				continue
			if "data-lightbox" in elem.attrs or elem.get("rel") == "lightbox":
				if "data-lightbox" in elem.attrs:
					stats["data-lightbox"] += 1
					del elem["data-lightbox"]
				if elem.get("rel") == "lightbox":
					stats["rel=lightbox"] += 1
					del elem["rel"]
				make_popup(elem)
				changed = need_gsa_script = True
				continue
			p = urlparse(elem["href"])
			if p.scheme.lower() == "javascript":
				# When a question mark appears in the JS, browsers actually interpret it
				# as the beginning of query parameters, as the apostrophe does not quote
				# it. For our purposes, though, it's cleaner to simply rejoin that.
				js = p.path
				if p.query: js += "?" + p.query
				info = classify_link(elem, js)
				ty = info["type"]
				if ty not in stats:
					print(ty, fn)
				if ty == "openPopImg":
					# Rewrite this link as a class=popup
					changed = need_gsa_script = True
					elem["href"] = info["args"][0]
					if len(info["args"]) > 1:
						elem["title"] = info["args"][1]
					# There might be 4 arguments (adding a width and height), but
					# since class=popup doesn't use those, we can ignore them.
					make_popup(elem)
				stats[ty] += 1
			if check_hover(elem, "onclick", "onmouseover", "onmouseout"): changed = True
			if "class" in elem.attrs and elem["class"] in ("", "off", "on"):
				del elem["class"]
				changed = True
	have_gsa_script = False
	for elem in soup.find_all("script"):
		if elem.get("src") == "/gsarchive.js":
			have_gsa_script = True
			continue
		script = str(elem)
		leave = ("MM_reloadPage", "google-analytics",
			"AC_RunActiveContent", "AC_FL_RunContent", "PopUpWin") # All to do with Flash. It needs to go.
		logme = ("openPopWin", "getLocation", "window.opener.pic") # getLocation is a dep of openPopWin
		removeme = ("openPopImg", "MM_preloadImages", "barts1000", "lightbox")
		for kwd in leave + logme + removeme:
			if kwd in script: break
		else: continue
		if kwd in leave: continue # Uninteresting for now
		if kwd in removeme:
			elem.replace_with("")
			changed = True
			script = "removed" # Log the script group as a single unit
		hash = kwd + "-" + hashlib.sha1(script.encode()).hexdigest()
		if hash not in scripts_seen:
			print("=== %s === %s" % (hash, fn), file=unique_scripts)
			print(script, file=unique_scripts)
			print("=== ===\n", file=unique_scripts)
		scripts_seen[hash] += 1
	for elem in soup.find_all("link", {"rel": "stylesheet", "href": True}):
		if "lightbox" in elem["href"]:
			elem.replace_with("")
			changed = True
	# Clean up the bracketing comments from popup images and other junk
	for elem in soup.find_all(text=lambda text: isinstance(text, Comment)):
		if re.match("^\s*URL:", elem.string, re.I): elem.string = "diamond.idbsu.edu" # hack out the URLs
		for removeme in ("Pop-up Images Script", "diamond.idbsu.edu", "Fireworks MX 2004 Dreamweaver",
				"#EndDate"):
			if removeme in elem.string:
				elem.replace_with("")
				changed = True
				comments["(removed)"] += 1
				break
		else: comments[elem.string] += 1
	if need_gsa_script and not have_gsa_script:
		soup.head.append(BeautifulSoup('<script src="/gsarchive.js" type=module></script>', "html.parser"))
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
print(hovers.total(), hovers)
print(scripts_seen.total(), scripts_seen)
# Show all comments that get featured more than once; group the rest into "Other"
#for c in list(comments):
#	if comments[c] == 1:
#		comments["Other"] += 1
#		del comments[c]
#print(comments)
