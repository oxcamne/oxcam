# check compatibility
import py4web

assert py4web.check_compatible("0.1.20190709.1")

# by importing db you expose it to the _dashboard/dbadmin
from .models import db

# by importing controllers you expose the actions defined in it
from . import controllers, stripe_interface, tools, website, session, email_daemon
from .email_daemon import email_daemon

# optional parameters
__version__ = "0.0.0"
__author__ = "dgmanns@gmail.com"
__license__ = "BSDv3"

#email daemon in it's own thread
from threading import Thread
t = Thread(target=email_daemon, daemon=True)
t.start()