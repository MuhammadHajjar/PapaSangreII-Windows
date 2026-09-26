"""PORT ADDITION: the port keeps itself up to date from its GitHub releases.

``version`` says which build this is, ``remotezip`` reads single files out of
a zip on a web server, ``updater`` finds, fetches and installs a new build,
and ``service`` runs the waiting-on-the-network parts on a worker thread for
the menus in ``apps/play.py``.
"""
