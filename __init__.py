# check compatibility
import py4web, threading

assert py4web.check_compatible("0.1.20190709.1")

# by importing db you expose it to the _dashboard/dbadmin
from .models import db

from .settings import THREAD_SUPPORT

# by importing controllers you expose the actions defined in it
from . import controllers, pay_processors, tools, website, session, email_daemon, daily_maintenance
from .email_daemon import email_daemon

# optional parameters
__version__ = "0.0.0"
__author__ = "dgmanns@gmail.com"
__license__ = "BSDv3"

if THREAD_SUPPORT:      #run the email daemon in it's own thread 
    # NOTE Pythonanywhere doesn't support threading
    thread = threading.Thread(target=email_daemon, daemon=True)
    thread.start()