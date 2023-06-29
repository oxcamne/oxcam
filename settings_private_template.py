"""
This file is a prototype for settings_private.py.
The first section contains sensitive settings, which may include sign-in codes
for database (if using, e.g., MySql), the email server for sending out notices etc.,
and account specific information for the Stripe payment processor
"""
from py4web import URL
import datetime
from dateutil import tz

DB_URI = "sqlite://storage.db"
DB_POOL_SIZE = 10

# email settings -development (uses Mailgun Sandbox, limited addressees)
SMTP_SSL = False
SMTP_SERVER = "smtp.mailgun.com:587"    #or other SMTP provider
SMTP_SENDER = "descriptive_name <reply_to_email>" 
SMTP_LOGIN = "sending_email_address:password"
SMTP_TLS = True

#Stripe settings development keys and id's
STRIPE_PKEY = "public_key"
STRIPE_SKEY = "secret_key"
#the following will depend on defined membership classes
STRIPE_FULL = "price_code"  #in our case, an auto-renewing subscription
STRIPE_STUDENT = "price_code"
#Stripe Product for charging event tickets (price variable)
STRIPE_EVENT = "product_code"

#----------------------------------------------------------------------
#remaining items shared across all environments for OxCamNE,
#would need to customized for other groups

SOCIETY_NAME = 'Oxford & Cambridge Society of New England'
SOCIETY_DOMAIN = 'OxCamNE'
SERVER_URL = "https://oxcamne.pythonanywhere.com/oxcam" #use production server, gmail can't handle local server
SUPPORT_EMAIL = 'dgmanns@gmail.com'
HOME_URL = 'https://www.oxcamne.org'
VISIT_WEBSITE_INSTRUCTIONS = "<br><br>Visit us at www.oxcamne.org or https://www.instagram.com/oxcamne/ or www.facebook.com/oxcamne"
MEMBER_CATEGORIES = ['Full', 'Student']
MEMBERSHIP = "Membership is open to all matriculated alumni and members of the \
Universities of Oxford and Cambridge.<br><br>\
Annual dues are $30 payable by subscription. In future years, you'll receive a \
reminder a week before the next auto-payment is made. \
Full time students, or those graduated within the last 12 months, qualify for student \
membership at $10 (please note your course and graduation date).<br><br>"
GRACE_PERIOD = 45 #Renewal within this number of days after expiration extends from \
                    #the expiration date. Also, member can renew this number of days \
                    # prior to expiration. Renewal notices are sent at expiration \
                    # plus -9, 0, 9, 18 days. Then auto renewal will be attempted \
                    # multiple times at the anniversary of payment and during \
                    # following 3 weeks. So we set the grace period to cover 18+21 \
                    # days
ACCESS_LEVELS = ['read', 'write', 'accounting', 'admin']

LETTERHEAD = f'<h2><span style="color: blue"><em>Oxford and Cambridge Society of New England</em></span> <img src="{SERVER_URL}/static/images/oxcamne_no_pad.png" alt="logo" style="float:left;width:100px" /></h2><h3><span style="color: blue"><em>&lt;subject&gt;</em></span></h3>'
MAIL_LISTS = "The <b>Member Events</b> list is used for notices of all Society in-person events \
except <b>Pub Nights</b> and <b>Online</b> (only) Events. This includes formal dinners, \
talk/receptions, and outdoor events. Some are for members only, others are open to all alumni.<br>\
<b>Other Events</b> includes such things as concerts by College Choirs, visiting College or \
University sports team events, and events organized by Cambridge in America or Oxford North America.<br>\
<b>OxCam10</b> includes informal events organized by OxCam10 for alumni within 10 years of graduation."
IS_PRODUCTION = False
#within the database, time and datetime will use local time specified here
TIME_ZONE = tz.gettz('America/New_York') #see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
LOCAL_NOW = None                        #filled in by @checkaccess decorator
