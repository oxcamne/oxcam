"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""
import locale, smtplib
from dateutil import tz

locale.setlocale(locale.LC_ALL, '')
DATE_FORMAT = locale.nl_langinfo(locale.D_FMT)
CURRENCY_SYMBOL = locale.nl_langinfo(locale.CRNCYSTR)[1:]

# database connection string:
DB_URI = "sqlite://storage.db"
"""
SQLite is built into Py4web and should be adequate except for large groups.
On PythonAnywhere you can alternatively use MySQL, e.g.:
DB_URI = "mysql://your_username:<--- database password here --->@your_username.mysql.pythonanywhere-services.com/oxcamne$default"
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

#see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIME_ZONE = tz.gettz('America/New_York')

# Customize the following group for your organization:
# URL for this oxcam database server:
DB_URL = "https://"
# organization name and domain/short_name, etc:
SOCIETY_NAME = 'your_group_name'
SOCIETY_SHORT_NAME = 'your_group_short_name'
# html web page banner Customize:
PAGE_BANNER = '<h4><span style="color: blue"><em>\
your_group_name</em> <img src="images/your_icon_file" \
alt="logo" style="float:left;width:100px" /></span></h4>'
# NOTE the logo image is in py4web/apps/oxcam/static/images
HOME_URL = 'https:/your_home_page'
    #this version allows authorized users to edit
HELP_URL = "https://your_help_site"
SUPPORT_EMAIL = 'your_support_email'
# html letterhead for email/notices:
LETTERHEAD = '<h2><span style="color: blue">\
<em>your_group_name</em></span> \
<img src="https://your_oxcam_server/oxcam/static/images/your_icon_file" \
alt="logo" style="float:left;width:100px" /></h2>\
<h3><span style="color: blue"><em>&lt;subject&gt;</em></span></h3>'
    #NOTE 'subject' replaced by full subject line in emails/notices
# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = "<br><br>Visit us at your_web_site or \
your_social_mediaåç"

# html description for mailing list selection
# must correspond to mail lists defined in database Email_Lists table.
MAIL_LISTS = f"The <b>Group Mailings</b> list is used for all {SOCIETY_SHORT_NAME} notices."

# Paid membership categories, else empty list:
MEMBER_CATEGORIES = ['Full', 'Student']
# set to '[]' if your organization doesn't have paid memberships

# html description of paid membership criteria:
MEMBERSHIP = "Membership is open to all matriculated alumni and members of the \
Universities of Oxford and Cambridge.<br><br>\
Annual dues are $30 payable by subscription. In future years, you'll receive a \
reminder a week before the next auto-payment is made. \
Full time students, or those graduated within the last 12 months, qualify for student \
membership at $10 (please note your course and graduation date).<br><br>"

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

# payment processor (currently only stripe implemented):
PAYMENT_PROCESSOR='stripe'  
#Stripe settings development keys and id's
STRIPE_PKEY = "<--- Stripe public key --->"
STRIPE_SKEY = "<--- Stripe secret key --->"
# specific products for membership dues
STRIPE_PROD_FULL = "<--- Stripe product id -->"  #Annual, autorenews
STRIPE_PROD_STUDENT = "<--- Stripe product id -->"    #Annual, no autorenew
