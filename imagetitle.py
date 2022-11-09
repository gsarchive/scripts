# Add titles and alt text to images
import sys
from bs4 import BeautifulSoup

titles = {
	"purple.gif": "Purple",
	"blue.gif": "Blue",
	"cyan.gif": "Cyan",
	"green.gif": "Green",
	"orange.gif": "Orange",
	"red.gif": "Red",
	"flags/auflag.gif": "Australian flag",
	"flags/canflag.gif": "Canadian flag",
	"flags/gbflag.gif": "British flag",
	"flags/usflag.gif": "Flag of USA",
	"flags/ireflag.png": "Irish flag",
	"flags/deflag.gif": "German flag",
}

def process(fn):
	with open(fn) as f: soup = BeautifulSoup(f, "html5lib")
	for img in soup.find_all("img"):
		src = img.get("src", "")
		if src not in titles:
			titles[src] = "" # Report only once per reference
			print(img)
			continue
		if not (tit := titles[src]): continue
		for attr in "title", "alt":
			if attr not in img.attrs:
				img[attr] = tit
				changed = True
	data = soup.encode(formatter="html5")
	with open(fn, "wb") as f: f.write(data)

for fn in sys.argv[1:]:
	print(fn)
	process(fn)
