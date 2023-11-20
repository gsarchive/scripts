# Classify all HTML files by their copyright notices
# - None (no "Copyright" or "©" etc)
# - CC-BY-SA 4.0
# - All Rights Reserved
# - Other/Unknown
# As much as possible, find the exact beginning and end of the copyright
# notice, thus allowing them to be replaced as needed. But for now, just
# classify the files.
# Fixes to be done:
# * If copyright is "All Rights Reserved", simply remove that text. It is
#   now copyright="None".
# * If copyright is "Unknown", the page is talking ABOUT copyright, or is
#   referring to the copyright status of ancillary material, so treat it as
#   equivalent to None.
# * If copyright is "None", add a <footer> at the end of document.body.main
#   or document.body, as per _layouts/default.html in the Markdown files.
#   It is now copyright="CC-BY-SA 4.0".
# * Add a standard CSS file to every page modified.
import os
import re
import sys
import collections
from bs4 import BeautifulSoup, Comment, Tag

root = "/home/rosuav/gsarchive/live"
# Faster and safer, not touching the original files
# On the server: find -type f -name \*.htm* >backups/htmlfiles.txt
# Locally: rsync -Pav gsarchiv:public_html/ --files-from live/backups/htmlfiles.txt clone/
# root = "/home/rosuav/gsarchive/clone"

copyright = re.compile(r"""
	(C?opyright|©).*
	(
		Gilber[e]?t\s*(and|&)\s*Sulliv[ae]n\s*Arch[i]?ve
		| Paul\s*Howarth
		| Colin\s*Johnson
	)
	.*(All\s*R[io]ghts\s*Reserved)?
""", re.IGNORECASE | re.VERBOSE | re.DOTALL)

just_a_date = re.compile(r"""^
\s*(Date\s*)?(Page\s*)?(modified|cr[ea]{2}ted|u[p]?dated)?
\s*(?P<day>[0-9]{1,2})			# Day
\s*(?P<mon>[A-Z][a-z]+)\.?\s*,?		# Month
\s*(?P<year>[0-9]{,4})			# Year (optional, and may be two-digit)
\s*\.?,?\s*				# Punctuation
(All\s*Rights\s*Reserved\s*)?		# In case it wasn't caught by the other search
$""", re.IGNORECASE | re.VERBOSE | re.DOTALL)

midi_files = re.compile(r"^\s*MIDI\s*files\s*$", re.IGNORECASE)

blank = re.compile(r"^\s*$")

footer = """<footer class="standalone">
<p class="copyright"><a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png"></a>
 This work is licensed under a <BR> <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.</p>
</footer>"""
def write_back(fn, soup):
	#print("WRITEBACK:", fn); return # bail
	if not soup.find("footer"):
		soup.body.append(BeautifulSoup(footer, "html.parser"))
		if not soup.find("link", href="/styles/gsarchive.css"):
			soup.head.append(BeautifulSoup('<link href="/styles/gsarchive.css" rel="stylesheet" type="text/css">', "html.parser"))
	data = soup.encode(formatter="html5")
	with open(fn, "wb") as f: f.write(data)

def classify_residue(cr, m, info):
	par = cr.parent
	cr.replace_with(cr.text[:m.start()], cr.text[m.end():])
	text = par.text
	# Figure out what else is in this blob.
	if m := just_a_date.match(text):
		# Reconstruct the content as "Page modified <day> <mon> <year>"
		# Would be nice to fix two-digit years, and maybe even the ones
		# where the year was omitted, but it'd be tough.
		par.clear()
		par.append("Page modified {day} {mon} {year}".format_map(m.groupdict()))
		return "Date"
	if midi_files.match(text): return "MIDI files"
	if blank.match(text): return "Blank"
	info["text"] = text
	return "UNKNOWN"

def classify(fn):
	info = { }
	with open(fn, "rb") as f: blob = f.read()
	soup = BeautifulSoup(blob, "html5lib")
	if soup.noframes: return {"copyright": "Skip"} # Can't fix, and not worth trying to fix, frames/noframes splits
	if soup.find(text=lambda text: isinstance(text, Comment) and "autogenerated" in text.lower()):
		info["generated"] = 1
	# Okay. So, what are we looking for, exactly?
	# 1) Easy mode: an anchor rel="license".
	for tag in soup.findAll(rel="license"):
		if tag["href"] == "https://creativecommons.org/licenses/by-sa/4.0/":
			return info | {"copyright": "CC-BY-SA 4.0"}
		if tag["href"] == "http://creativecommons.org/licenses/by-sa/4.0/":
			return info | {"copyright": "CC-BY-SA 4.0"} # Maybe fix protocol? Or not bother.
		info.setdefault("links", []).append(tag["href"])
	if "links" in info:
		return info | {"copyright": "Unknown"}
	text = []
	for cr in soup.findAll(text=True):
		if m := copyright.search(cr.text):
			residue = classify_residue(cr, m, info)
			if residue != "UNKNOWN":
				# Page content has been fixed. Let's tidy this up.
				write_back(fn, soup)
				return info | {"copyright": "Corrected"}
			return info | {"copyright": "All Rights Reserved", "residue": residue}
		# Look for any copyright marker, including a miswritten HTML entity
		if "copyright" in cr.text or "©" in cr.text or "&copy" in cr.text:
			# Maybe there's a full copyright notice in the parent's text,
			# but it's split up by HTML tags.
			if cr.parent("a", href="mailto:dstone4@cox.net"):
				# The WhoWasWho pages have a different copyright marker.
				# They probably should all get synchronized too, but maybe
				# not to the same value. Would be nice to use the same
				# format and CSS everywhere at least.
				return info | {"copyright": "David Stone"}
			if m := copyright.search(cr.parent.text):
				# Fixing this is going to be harder. But it's still an ARR
				# copyright notice.
				# "residue": classify_residue(cr.parent, m, info)
				return info | {"copyright": "All Rights Reserved", "fix": "if possible", "residue": "UNKNOWN"}
			text.append(cr.text)
	if text: return info | {"copyright": "Unknown", "text": text}
	write_back(fn, soup)
	return info | {"copyright": "Added"}

for fn in sys.argv[1:]:
	if os.path.exists(fn):
		print(classify(fn))
		sys.exit(0)

stats = collections.Counter()
residues = collections.Counter()
known_types = ["All Rights Reserved", "None", "CC-BY-SA 4.0", "David Stone", "Unknown"]
with open("copywrong.log", "w") as log:
	for root, dirs, files in os.walk(root):
		if "whowaswho" in dirs: dirs.remove("whowaswho")
		if "backups" in dirs: dirs.remove("backups")
		for file in files:
			if not file.endswith(".html") and not file.endswith(".htm"): continue
			fn = os.path.join(root, file)
			try: info = classify(fn)
			except: print(fn); raise
			stats[info["copyright"]] += 1
			if not stats.total() % 1000: print(stats.total(), stats)
			if info["copyright"] == "All Rights Reserved":
				if info["residue"] == "UNKNOWN": print(fn, info, file=log)
				residues[info["residue"]] += 1
			elif info["copyright"] not in known_types:
				print(fn, info)
				known_types.append(info["copyright"])
print(stats.total(), stats)
print(residues.total(), residues)

""" For manual testing:
def get(fn):
    global soup, cr
    soup = BeautifulSoup(open(fn).read(), "html5lib")
    cr = soup.find(text=lambda t: "Copyright" in t.text)


link = Tag(name="a", attrs={"rel": "license", "data-fixme": "please"})
link.insert(0, m.group(0))
cr.replace_with(cr.text[:m.start()], link, cr.text[m.end():])
"""
