"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""

# organization name and domain/short_name, etc:
SOCIETY_NAME = 'your_group_name'
SOCIETY_SHORT_NAME = 'your_group_short_name'    #ideally, the domain name omitting the .xxx part
                #also use as your username if using Pythonanywhere server
SOCIETY_LOGO = 'your_logo_file' #should be placed in py4web/apps/oxcam/static/images directory
# html web page banner Customize:
PAGE_BANNER = f'<h4><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="images/{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h4>'
# NOTE the logo image is in py4web/apps/oxcam/static/images
HOME_URL = 'your_home_page_url'
    #this version allows authorized users to edit
HELP_URL = 'your_help_web_site_url' #site may embed the database help site https://oxcamne.github.io/oxcam
DB_URL = f'your_database_server_url'   #e.g. https://{SOCIETY_SHORT_NAME}.pythonanywhere.com/oxcam
SUPPORT_EMAIL = 'your_support_email'
# html letterhead for email/notices:
LETTERHEAD = f'<h2><span style="color: blue"><em>{SOCIETY_NAME}</em></span> \
<img src="{DB_URL}/static/images/{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" />\
</h2><h3><span style="color: blue"><em>&lt;subject&gt;</em></span></h3>'
    #NOTE 'subject' replaced by full subject line in emails/notices
# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = f"<br><br>Visit us at {HOME_URL} or your_social_media"

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

# database connection string:
DB_URI = "sqlite://storage.db"
"""
SQLite is built into Py4web and should be adequate except for extremely large groups.
On PythonAnywhere you can alternatively use MySQL, e.g.:
DB_URI = f"mysql://{SOCIETY_SHORT_NAME}:<--- database password here --->@{SOCIETY_SHORT_NAME}.mysql.pythonanywhere-services.com/{SOCIETY_SHORT_NAME}$default"
DB_POOL_SIZE = 10
"""

# set True only for live production instance
IS_PRODUCTION = True
#if False, email is suppressed except to the following listed emails:
ALLOWED_EMAILS = []

# if True, run email daemon & daily maintenance in server threads
THREAD_SUPPORT = False
# Note, PythonAnywhere doesn't support threads, must run
# these processes as scheduled tasks. Set True if your
# environment supports threads.

# access levels for group administrators do not change
ACCESS_LEVELS = ['read', 'write', 'accounting', 'admin']

from dataclasses import dataclass
import decimal

@dataclass
class Membership:
    category: str
    annual_dues: decimal
    description: str
    qualification: str = None

#list of Membership definitions (may be empty list - adjust as needed)
MEMBERSHIPS = [
    Membership('Full', 30, "Membership is open to all matriculated alumni and \
members of the Universities of Oxford and Cambridge.<br><br>\
Annual dues are $30 payable by subscription. In future years, you'll receive a \
reminder a week before the next auto-payment is made."),
    Membership('Student', 10, "Full time students, or those graduated within \
the last 12 months, qualify for student membership at $10, renewable annually",
"Please note details of your full-time course (current or graduated within last 12 months).")
]

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

#SMTP host connection for transactional messages
SMTP_TRANS = ('smtp.somewhere.com', 'port', 'username', 'password')

#SMTP host connection for bulk messages
SMTP_BULK = SMTP_TRANS

# logger settings
LOGGERS = [
     "info:oxcam.log:%(asctime)s - %(levelname)s - %(message)s"
]  # syntax "severity:filename:format" filename can be stderr or stdout
ALLOWED_ACTIONS = []    #disable Py4web's auth

# payment processor (currently only stripe implemented):
PAYMENT_PROCESSOR='stripe'  
#Stripe settings development keys and id's
STRIPE_PKEY = "<--- Stripe public key --->"
STRIPE_SKEY = "<--- Stripe secret key --->"
# specific products for membership dues
STRIPE_PROD_FULL = "<--- Stripe product id -->"  #Annual, autorenews
STRIPE_PROD_STUDENT = "<--- Stripe product id -->"    #Annual, no autorenew
