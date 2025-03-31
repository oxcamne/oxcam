"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""

# organization name and domain/short_name, etc:
SOCIETY_NAME = 'your_group_name'
SOCIETY_SHORT_NAME = 'your_group_short_name'    #ideally, the domain name omitting the .xxx part
				#also use as your username if using Pythonanywhere server
SOCIETY_LOGO = 'your_logo_file_name' 		#should be placed in py4web/apps/oxcam/static directory
				#Your favicon.ico should also be placed in py4web/apps/oxcam/static directory

DB_URL = f'your_database_server_url'   #e.g. https://{SOCIETY_SHORT_NAME}.pythonanywhere.com/oxcam

SUPPORT_EMAIL = 'your_support_email'

# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = f"<br><br>Visit us at 'your_web_site_url' or your_social_media"
				#your_web_site_url might be www.{SOCIETY_SHORT_NAME}.org or similar, or {DB_URL}/web/home

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
DATE_FORMAT = locale.nl_langinfo(locale.D_FMT)
CURRENCY_SYMBOL = locale.nl_langinfo(locale.CRNCYSTR)[1:]
#don't currently deal with currency symbols that follow the amount
TIME_ZONE = tz.gettz('America/New_York')
#see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

# set True only for live production instance, False for development/testing
IS_PRODUCTION = True
#if False, email is suppressed except to the following listed emails:
ALLOWED_EMAILS = []

from dataclasses import dataclass
import decimal

@dataclass
class Membership:
	category: str
	description: str
	qualification: str = None

"""
list of Membership definitions (may be empty list)
NOTE <dues> in description will be replaced by the figure in e.g. Stripe's dues products.
"""
MEMBERSHIPS = [
	Membership('Full', "all matriculated alumni and members of the Universities of \
Oxford and Cambridge. Annual dues are <dues> payable by subscription. In future years, you'll \
receive a reminder a week before the next auto-payment is made."),
	Membership('Student', "full time students (current or graduated within \
the last 12 months). Annual dues are <dues>, renewable annually",
"Please note details of your full-time course (current or graduated within last 12 months).")
]

@dataclass
class Email_Account:
	server: str
	port: int
	username: str
	password: str

#SMTP host connection for transactional messages (e.g. a gmail account)
SMTP_TRANS = Email_Account('smtp.somewhere.com', 'port', 'username', 'password')

#SMTP host connection for bulk messages (e.g. a mailing service such as mailgun)
SMTP_BULK = Email_Account('smtp.somewhere.com', 'port', 'username', 'password')

class PaymentProcessor:
	def __init__(self, name, public_key, secret_key, dues_products):
		self.name = name	#should be lower case, single word (underscore allowed)
		self.public_key = public_key
		self.secret_key = secret_key
		self.dues_products = dues_products

""" available processors, first is defaault: 
NOTE the local copy in pay_processors module contains the full implementions.
Access using the functions paymentprocessor(name) in the pay_procesors module
"""
PAYMENTPROCESSORS = [
	PaymentProcessor(name = 'stripe',
		public_key = "<-- stripe production public key -->" if IS_PRODUCTION else "<-- stripe test public key -->",
		secret_key = "<-- stripe production secret key -->" if IS_PRODUCTION else "<-- stripe test secret key -->",
		dues_products = {
			'Full': "<-- stripe production product id -->" if IS_PRODUCTION else "<-- stripe test product id -->",
			'Student': "<-- stripe production product id -->" if IS_PRODUCTION else "<-- stripe test product id -->"
		}
	)
]

#Gooogle reCAPTCHA keys (set all to None if not using Captcha)
RECAPTCHA_KEY = "production_recaptcha_site_key" if IS_PRODUCTION else "develomemnt_recaptcha_site_key"
RECAPTCHA_SECRET = "production_recaptcha_secret" if IS_PRODUCTION else "develomemnt_recaptcha_secret"

VERIFY_TIMEOUT = 3	#minutes enforced between verification emails

"""
Review the following settings and adjust as needed, but no changes are likely to be needed
"""

# html web page banner Customize:
PAGE_BANNER = f'<h4><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h4>'

# html letterhead for email/notices:
LETTERHEAD = f'<h2><span style="color: blue"><em>{SOCIETY_NAME}</em></span> \
<img src="{DB_URL}/static/{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" />\
</h2><br><br>'

# database connection string:
DB_URI = "sqlite://storage.db"
"""
SQLite is built into Py4web and should be adequate except for extremely large groups.
On PythonAnywhere you can alternatively use MySQL, e.g.:
DB_URI = f"mysql://{SOCIETY_SHORT_NAME}:<--- database password here --->@{SOCIETY_SHORT_NAME}.mysql.pythonanywhere-services.com/{SOCIETY_SHORT_NAME}$default"
DB_POOL_SIZE = 10
"""

# if True, run email daemon & daily maintenance in server threads
THREAD_SUPPORT = False
# Note, PythonAnywhere doesn't support threads, must run
# these processes as scheduled tasks. Set True if your
# environment supports threads, e.g. in development environment.

# access levels for group administrators DO NOT CHANGE, used in @checkaccess(None|any)
ACCESS_LEVELS = ['read', 'write', 'accounting', 'admin']

GRACE_PERIOD = 45
"""
Renewal within this number of days after expiration extends membership
continuously from the expiration date.
Also, member can renew this number of days prior to expiration. 
Renewal notices are sent at expiration plus -9, 0, 9, 18 days.
Auto renewal will be attempted multiple times at the anniversary of payment
and during following 3 weeks. So we set the grace period to cover 18+21 \
days.
"""

# logger settings
LOGGERS = [
	"warning:stdout",
	"info:oxcam.log:%(asctime)s - %(levelname)s - %(message)s"
]  # syntax "severity:filename:format" filename can be stderr or stdout

ALLOWED_ACTIONS = []    #disable Py4web's auth
