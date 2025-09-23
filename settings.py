"""
This is an optional file that defined app level settings such as:
- database settings
- session settings
- i18n settings
This file is provided as an example:
"""
import os
from py4web.core import required_folder

# mode (default or development)
MODE = os.environ.get("PY4WEB_MODE")

# db settings
APP_FOLDER = os.path.dirname(__file__)
APP_NAME = os.path.split(APP_FOLDER)[-1]

# DB_FOLDER:    Sets the place where migration files will be created
#               and is the store location for SQLite databases
DB_FOLDER = required_folder(APP_FOLDER, "databases")
DB_URI = "sqlite://storage.db"
DB_POOL_SIZE = 1
DB_MIGRATE = True
DB_FAKE_MIGRATE = False

# location where static files are stored:
STATIC_FOLDER = required_folder(APP_FOLDER, "static")

# location where to store uploaded files:
UPLOAD_FOLDER = required_folder(APP_FOLDER, "uploads")

# send verification email on registration
VERIFY_EMAIL = MODE != "development"

# complexity of the password 0: no constraints, 50: safe!
PASSWORD_ENTROPY = 0 if MODE == "development" else 50

# account requires to be approved ?
REQUIRES_APPROVAL = False

# auto login after registration
# requires False VERIFY_EMAIL & REQUIRES_APPROVAL
LOGIN_AFTER_REGISTRATION = False

# ALLOWED_ACTIONS in API / default Forms:
# ["all"]
# ["login", "logout", "request_reset_password", "reset_password", \
#  "change_password", "change_email", "profile", "config", "register",
#  "verify_email", "unsubscribe"]
# Note: if you add "login", add also "logout"
ALLOWED_ACTIONS = ["all"]

# email settings
SMTP_SSL = False
SMTP_SERVER = None
SMTP_SENDER = "you@example.com"
SMTP_LOGIN = "username:password"
SMTP_TLS = False

# session settings
SESSION_TYPE = "cookies"
SESSION_SECRET_KEY = None  # or replace with your own secret
MEMCACHE_CLIENTS = ["127.0.0.1:11211"]
REDIS_SERVER = "localhost:6379"

# logger settings
LOGGERS = [
    "warning:stdout"
]  # syntax "severity:filename:format" filename can be stderr or stdout

# Disable default login when using OAuth
DEFAULT_LOGIN_ENABLED = True

# single sign on Google (will be used if provided)
OAUTH2GOOGLE_CLIENT_ID = None
OAUTH2GOOGLE_CLIENT_SECRET = None

# Single sign on Google, with stored credentials for scopes (will be used if provided).
# set it to something like os.path.join(APP_FOLDER, "private/credentials.json"
OAUTH2GOOGLE_SCOPED_CREDENTIALS_FILE = None

# single sign on Okta (will be used if provided. Please also add your tenant
# name to py4web/utils/auth_plugins/oauth2okta.py. You can replace the XXX
# instances with your tenant name.)
OAUTH2OKTA_CLIENT_ID = None
OAUTH2OKTA_CLIENT_SECRET = None

# single sign on Google (will be used if provided)
OAUTH2FACEBOOK_CLIENT_ID = None
OAUTH2FACEBOOK_CLIENT_SECRET = None

# single sign on GitHub (will be used if provided)
OAUTH2GITHUB_CLIENT_ID = None
OAUTH2GITHUB_CLIENT_SECRET = None

# enable PAM
USE_PAM = False

# enable LDAP
USE_LDAP = False
LDAP_SETTINGS = {
    "mode": "ad",  # Microsoft Active Directory
    "server": "mydc.domain.com",  # FQDN or IP of one Domain Controller
    "base_dn": "cn=Users,dc=domain,dc=com",  # base dn, i.e. where the users are located
}

# i18n settings
T_FOLDER = required_folder(APP_FOLDER, "translations")

# Scheduler settings
USE_SCHEDULER = False
SCHEDULER_MAX_CONCURRENT_RUNS = 1

# Celery settings (alternative to the build-in scheduler)
USE_CELERY = False
CELERY_BROKER = "redis://localhost:6379/0"

"""
The settings below allow oxcam to run before settings_private.py is created.

Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""

# organization name and domain/short_name, etc:
SOCIETY_NAME = 'your_group_name'
SOCIETY_SHORT_NAME = 'your_group_short_name'    #ideally, the domain name omitting the .xxx part
				#also use as your username if using Pythonanywhere server
SOCIETY_LOGO = 'oxcamne_no_pad.png' 		#should be placed in py4web/apps/oxcam/static directory
				#Your favicon.ico should also be placed in py4web/apps/oxcam/static directory
				#note, oxcamne_no_pad.png and favicon.ico are part of the distribution and have both university arms

WEB_URL = f'your_database_server_url'   #e.g. https://{SOCIETY_SHORT_NAME}.pythonanywhere.com/oxcam

SUPPORT_EMAIL = 'your_support_email'

# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = f"<br><br>Visit us at 'your_web_site_url' or 'your_social_media'"
				#your_web_site_url might be www.{SOCIETY_SHORT_NAME}.org or similar, or {WEB_URL}/web/home

#SMTP server for sending transactional messages (e.g. a gmail account)
SMTP_TRANS = None #indicates that setttings_private.py does not exist yet!

#SMTP server for sending bulk messages (e.g. a mailing service such as mailgun)
#for small groups, this can be the same as SMTP_TRANS
SMTP_BULK = None

#localization settings
import locale
from dateutil import tz
locale.setlocale(locale.LC_ALL, '')
"""
as above, takes the default settings for the server. You can check what this is using a 
command line terminal on the server using the "locale" command.
Use "locale -a" to see list of supported locale's.
You can specify by replacing the empty '' above with the preferred locale
"""
TIME_ZONE = tz.gettz('America/New_York')
#see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

#on Test/Development instance, email is suppressed except to the following listed emails:
ALLOWED_EMAILS = []

MEMBERSHIPS = []

class PaymentProcessor:
	def __init__(self, name, public_key, secret_key, dues_products):
		self.name = name	#should be lower case, single word (underscore allowed)
		self.public_key = public_key
		self.secret_key = secret_key
		self.dues_products = dues_products

PAYMENTPROCESSORS = []
RECAPTCHA_KEY = None
RECAPTCHA_SECRET = None
VERIFY_TIMEOUT = 3	#minutes enforced between verification emails

"""
Review the following settings and adjust as needed, but no changes are likely to be needed
"""

# html web page banner Customize:
PAGE_BANNER = f'<h4><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h4>'

# html letterhead for email/notices:
LETTERHEAD = f'<h2><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="https://oxcamne.pythonanywhere.com/oxcam/static/{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h2><br><br>'

# if True, run email daemon & daily maintenance in server threads
THREAD_SUPPORT = False
# Note, PythonAnywhere doesn't support threads, must run
# these processes as scheduled tasks. Set True if your
# environment supports threads, e.g. in development environment.

# access levels for group administrators DO NOT CHANGE, used in @checkaccess(None|any)
ACCESS_LEVELS = ['read', 'write', 'accounting', 'admin']

GRACE_PERIOD = 45

# logger settings
LOGGERS = [
	"warning:stdout",
	"info:oxcam.log:%(asctime)s - %(levelname)s - %(message)s"
]  # syntax "severity:filename:format" filename can be stderr or stdout

ALLOWED_ACTIONS = []    #disable Py4web's auth

# try import the real private settings
try:
    from .settings_private import *
except (ImportError, ModuleNotFoundError):
    pass
