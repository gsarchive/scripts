G&S Archive Scripts
===================

The code in this repository automates various improvements to the Gilbert and
Sullivan Archive at https://gsarchive.net/ to reduce the manual workload.

Some template content can also be found here, including this which enables the
standard styling and popup images:

    <link href="/styles/gsarchive.css" rel="stylesheet" type="text/css">
    <script src="/gsarchive.js" type=module></script>

If any page does not have an integrated copyright footer, add this:

    <footer class="standalone">
    <p class="copyright"><a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/88x31.png"></a>
    This work is licensed under a <BR> <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.</p>
    </footer>

To recreate the clone directory:

    On the server:
    $ cd public_html
    $ find -type f -name \*.htm* | grep -v '^./backups/' >backups/htmlfiles.txt
    On the client:
    $ mount live
    $ rm -r clone; rsync -Pav gsarchiv:public_html/ --files-from live/backups/htmlfiles.txt clone/
    To patch back files that got changed:
    $ sed 's_/home/rosuav/gsarchive/clone_._' <scripts/change.log | rsync -Pav gsarchiv:public_html/ --files-from - clone/

TODO:

* If you iframe an image, the image's native size is ignored and the iframe has
  a default size. This is unideal, ergo we stick to an IMG element when the popup
  is a simple image. Would be nice to unify and to have some sort of user zoom.
