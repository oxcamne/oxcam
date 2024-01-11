"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""
import datetime
from dateutil import tz
from py4web.utils.mailer import Mailer

# database connection string:
DB_URI = "sqlite://storage.db"
"""
SQLite is built into Py4web and should be adequate except for large groups.
On PythonAnywhere you can alternatively use MySQL, e.g.:
DB_URI = "mysql://oxcamne:<--- database password here --->@oxcamne.mysql.pythonanywhere-services.com/oxcamne$default"
DB_POOL_SIZE = 10
"""

# set True only for live production instance
IS_PRODUCTION = True
#if False, email is suppressed except to the following:
ALLOWED_EMAILS = ['dgmanns@gmail.com', 'secretary@oxcamne.org', 'david.manns@trinity.cantab.net']

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
DB_URL = "https://oxcamne.pythonanywhere.com/oxcam"
# organization name and domain/short_name, etc:
SOCIETY_NAME = 'Oxford & Cambridge Society of New England'
SOCIETY_SHORT_NAME = 'OxCamNE'
# html web page banner Customize:
PAGE_BANNER = '<h4><span style="color: blue"><em>\
Oxford and Cambridge Society of New England</em> <img src="images/oxcamne_no_pad.png" \
alt="logo" style="float:left;width:100px" /></span></h4>'
# NOTE the logo image is in py4web/apps/oxcam/static/images
HOME_URL = 'https://sites.google.com/oxcamne.org/home/?authuser=1'
	#this version allows authorized users to edit
HELP_URL = "https://sites.google.com/oxcamne.org/help-new/home?authuser=1"
PUBLIC_URL = 'www.oxcamne.org'
	#domain service re-routes to sites.google
SUPPORT_EMAIL = 'secretary@oxcamne.org'
# html letterhead for email/notices:
LETTERHEAD = '<h2><span style="color: blue">\
<em>Oxford and Cambridge Society of New England</em></span> \
<img src="https://oxcamne.pythonanywhere.com/oxcam/static/images/oxcamne_no_pad.png" \
alt="logo" style="float:left;width:100px" /></h2>\
<h3><span style="color: blue"><em>&lt;subject&gt;</em></span></h3>'
	#NOTE 'subject' replaced by full subject line in emails/notices
# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = "<br><br>Visit us at www.oxcamne.org or \
https://www.instagram.com/oxcamne/ or www.facebook.com/oxcamne"

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

# email settings use in common.py to construct auth.sender which is used for all
# transactional messages (low volume of messages)
SMTP_SSL = False
SMTP_SERVER = "smtp.gmail.com:587"
SMTP_SENDER = "Oxford & Cambridge Society <oxcamne@oxcamne.org>"
SMTP_LOGIN = "<--- gmail login with app password --->"
SMTP_TLS = True

#define the bulk email sender for mailing list use etc.
# smaller organizations (up to a few hundred on mailing list) could even
# use the same account as above
BULK_SENDER =  Mailer(
	server="smtp.mailgun.com:587",
	sender="Oxford & Cambridge Society <oxcamne@oxcamne.org>",
	login="postmaster@<---- domain SMTP login ---->",
	tls=SMTP_TLS,
	ssl=SMTP_SSL,
)

# payment processor (currently only stripe implemented):
PAYMENT_PROCESSOR='stripe'  
#Stripe settings development keys and id's
STRIPE_PKEY = "<--- Stripe public key --->"
STRIPE_SKEY = "<--- Stripe secret key --->"
# specific products for membership dues
STRIPE_PROD_FULL = "<--- Stripe product id -->"  #Annual, autorenews
STRIPE_PROD_STUDENT = "<--- Stripe product id -->"    #Annual, no autorenew
