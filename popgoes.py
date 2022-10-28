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

stats = collections.Counter()
def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	for elem in soup.find_all("a"):
		p = urlparse(elem["href"])
		if p.scheme.lower() == "javascript":
			print(elem["href"])

for fn in sys.argv[1:]:
	if os.path.exists(fn):
		classify(fn)
		sys.exit(0)

with open("weasels.log", "w") as log:
	for root, dirs, files in os.walk(root):
		if "backups" in dirs: dirs.remove("backups")
		for file in files:
			if not file.endswith(".html") and not file.endswith(".htm"): continue
			fn = os.path.join(root, file)
			try: classify(fn)
			except: print(fn); raise
print(stats.total(), stats)
