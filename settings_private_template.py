"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""

# organization name and domain/short_name, etc:
SOCIETY_NAME = 'your_group_name'
SOCIETY_SHORT_NAME = 'your_group_short_name'    # ideally, the domain name omitting the .xxx part
				# also use as your username if using Pythonanywhere server
WEB_URL = f'your_database_server_url'   #e.g. https://{SOCIETY_SHORT_NAME}.pythonanywhere.com/oxcam
"""
Your logo file should be placed in py4web/apps/oxcam/static directory and its name replacing oxcamne_no_pad.png
Your favicon.ico should also be placed in py4web/apps/oxcam/static directory. this appears on browser tabs
NOTE oxcamne_no_pad.png and favicon.ico are part of the distribution and have both university arms
"""
SOCIETY_LOGO = 'oxcamne_no_pad.png'

# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = f"<br><br>Visit us at 'your_web_site_url' or 'your_social_media'"
				# your_web_site_url might be www.{SOCIETY_SHORT_NAME}.org or similar, or {WEB_URL}/web/home

from dataclasses import dataclass
import decimal

@dataclass
class Email_Account:
	server: str
	port: int
	username: str
	password: str

"""
SMTP server for sending transactional messages such as email verification (login), confirmations, etc.
This will be configured from the form displayed on first call to oxcam, which will also set SUPPORT_EMAIL
to the corresponding email address.
Could be a gmail account or similar.
"""
SMTP_TRANS = Email_Account('smtp_server', 'smtp_port', 'email_username', 'email_password')
SUPPORT_EMAIL = 'your_support_email'	#will be used for sending out email verification, confirmations, etc.

"""
SMTP server for sending bulk messages )
for small groups, this can be the same as SMTP_TRANS
for larger groups, consider using a dedicated bulk email service such as mailgun
"""
SMTP_BULK = SMTP_TRANS

import locale
from dateutil import tz
"""
LOCALE settings for date format, currency symbol, and time zone.
The locale settings are set to the server default, which is usually appropriate.
You can check what this is using a command line terminal on the server using the "locale" command.
Use "locale -a" to see list of supported locale's.
You can specify a different localeby replacing the empty '' below with the preferred locale from the list.
"""
locale.setlocale(locale.LC_ALL, '')
DATE_FORMAT = "%x"	#format dates based on locale: US format mm/dd/yyyy UK format would be "%d/%m/%Y"
CURRENCY_SYMBOL = '$'	#US dollars TODO use locale.currency() to format amounts instead
# NOTE don't currently deal with currency symbols that follow the amount
TIME_ZONE = tz.gettz('America/New_York')
# see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

"""
On a Test/Development instance, specify an email whitelist in format ['email1@example.com', 'email2@example.com', ...]
Email to any other address will be suppressed.
NOTE Stripe and ReCaptcha keys should also be different on test instances.
"""
ALLOWED_EMAILS = []

class PaymentProcessor:
	def __init__(self, name, public_key, secret_key, dues_products):
		self.name = name	#should be lower case, single word (underscore allowed)
		self.public_key = public_key
		self.secret_key = secret_key
		self.dues_products = dues_products

""" To implement payment processing, define a list of PaymentProcessor objects, e.g. by uncommenting the definition
below and filling in the keys.
Include dues_products = {...} with the product ids for the dues categories in MEMBERSHIPS if you will have paid memberships.
Currently only Stripe is supported. 
NOTE all the keys and product ids have both production and test/development values. The dues_products dictionary
should contain the product ids for the dues categories in MEMBERSHIPS, which are used to create the payment links.
NOTE the local copy in pay_processors module contains the full implementions.
Access using the functions paymentprocessor(name) in the pay_procesors module

PAYMENTPROCESSORS = [
	PaymentProcessor(name = 'stripe',
		public_key = "<-- stripe public key -->"",
		secret_key = "<-- stripe secret key -->" ,
		dues_products = {
			'Full': "<-- stripe product id -->",	# these lines should correspond to MEMBERSHIPS
			'Student': "<-- stripe product id -->"	# and omitted if not using membership categories
		}
	)
]
"""

@dataclass
class Membership:
	category: str
	description: str
	qualification: str = None

"""
To implement membership categories, define a list of Membership objects, such as the list below, which
are the categories used by the Oxford & Cambridge Society of New England.

MEMBERSHIPS = [
	Membership('Full', "all matriculated alumni and members of the Universities of \
Oxford and Cambridge. Annual dues are <dues> payable by subscription. In future years, you'll \
receive a reminder a week before the next auto-payment is made."),
	Membership('Student', "full time students (current or graduated within \
the last 12 months). Annual dues are <dues>, renewable annually",
"Please note details of your full-time course (current or graduated within last 12 months).")
]
"""

#Gooogle reCAPTCHA keys (set all to empty string if not using Captcha)
RECAPTCHA_KEY = ""
RECAPTCHA_SECRET = ""

VERIFY_TIMEOUT = 3	#minutes enforced between verification emails. A non zero value is highly recommended
					#to avoid the site being used by spammers.

# html web page banner Customize:
PAGE_BANNER = f'<h4><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h4>'

# html letterhead for email/notices:
LETTERHEAD = f'<h2><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="{WEB_URL}/static/{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h2><br><br>'
# NOTE as this is html to be interpreted by the browser, all URLs must refer to the web, not a localhost

"""
To use a database other than SQLite, define the database URI and pool size.
SQLite is built into Py4web and should be adequate except for extremely large groups.
For example, if using PythonAnywhere, you can use MySQL (see the Pythonanywhere documentation for setup info)
DB_URI = f"mysql://{SOCIETY_SHORT_NAME}:<--- database password here --->@{SOCIETY_SHORT_NAME}.mysql.pythonanywhere-services.com/{SOCIETY_SHORT_NAME}$default"
DB_POOL_SIZE = 10
"""

# if True, run email daemon & daily maintenance in server threads
THREAD_SUPPORT = False
# Note, PythonAnywhere doesn't support threads, must run
# these processes as scheduled tasks. Set True if your
# environment supports threads, e.g. in development environment.

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
