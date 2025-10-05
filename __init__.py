# check compatibility
import py4web

assert py4web.check_compatible("0.1.20190709.1")

# by importing db you expose it to the _dashboard/dbadmin
from .models import db

# by importing controllers you expose the actions defined in it
from . import pay_processors, daily_maintenance, email_daemon, session, tools, website, controllers

# optional parameters
__version__ = "1.1.8"
__author__ = "dgmanns@gmail.com"
__license__ = "BSDv3"
