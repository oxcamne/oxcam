# oxcam

## Introduction

OxCam is a web based database app designed to support Oxford and/or Cambridge Alumni groups and Societies.
It can be deployed on low cost cloud services such as PythonAnywhere or Linode (Akamai) at very low cost.

- At it's simplest it can be used to maintain mailing lists and send out notices.
- It can track events and provide registration capabilities including payment collection, maintaining a wait
list, etc.
- One or more paid membership categories can be implemented, either sending renewal reminders
or using autopay subscriptions, and collecting dues payments through a payment processor such as
Stripe. Members will have access to an online directory.
- By uploading transaction files (in .csv format) from banks and payment processors it can maintain
comprehensive accounts.

A group can choose how many of the above to implement and can expand it's use over time.

## Prerequisites

- Python 3.8+ must be installed
- [Py4web](https://py4web.com/_documentation) must also be installed.
- You will need to use the Py4web Dashboard for certain operations, so will need that password, set up
during Py4web installation.
- git must be installed; you will use it in a terminal session to clone this software from the github repositary, and to pull future updates. (Git is preinstalled on PythonAnywhere)

## License

This software is released under the [BSD-3-Clause License](LICENSE)

## Installation

To install OxCam once the prerequisites have been satisfied:

In a bash or other terminal session at the py4web 'apps' directory, issue the command:

```bash
    git clone https://github.com/oxcamne/oxcam.git
```

This clones the software into a new directory apps/oxcam. You next need to create a 'settings_private.py' file in apps/oxcam. Customize the contents from the code below, which is taken from the OxCamNE development environment (with sensitive keys removed):

```python
"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""
import datetime
from dateutil import tz

# database connection string:
DB_URI = "sqlite://storage.db"
DB_POOL_SIZE = 10
"""
SQLite is built into Py4web and should be adequate except for large groups.
On PythonAnywhere you can alternatively use MySQL, e.g.:
DB_URI = "mysql://oxcamne:<--- database password here --->@oxcamne.mysql.pythonanywhere-services.com/oxcamne$default"
"""

# set True only for live production instance
IS_PRODUCTION = False
#if False, email notifications are suppressed

# if True, run email daemon & daily maintenance in server threads
THREAD_SUPPORT = True
# Note, PythonAnywhere doesn't support threads, must run
# these processes as scheduled tasks

# html web page banner:
PAGE_BANNER = '<h4><span style="color: blue"><em>\
Oxford and Cambridge Society of New England</em> <img src="images/oxcamne_no_pad.png" \
alt="logo" style="float:left;width:100px" /></span></h4>'
# NOTE the logo image is in py4web/apps/oxcam/static/images

# access levels for group administrators
ACCESS_LEVELS = ['read', 'write', 'accounting', 'admin']

# URL for this oxcam database instance, development local server in this case
DB_URL = "http://127.0.0.1:8000/oxcam"

#see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIME_ZONE = tz.gettz('America/New_York')

# organization name and domain/short_name, etc:
SOCIETY_NAME = 'Oxford & Cambridge Society of New England'
SOCIETY_SHORT_NAME = 'OxCamNE'
HOME_URL = 'https://sites.google.com/oxcamne.org/home/?authuser=1'
        #this version allows authorized users to edit
PUBLIC_URL = 'www.oxcamne.org'
        #domain service re-routes to sites.google
SUPPORT_EMAIL = 'dgmanns@gmail.com'

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

# html description for mailing list selection:
MAIL_LISTS = "The <b>Member Events</b> list is used for notices of all Society in-person events \
except <b>Pub Nights</b> and <b>Online</b> (only) Events. This includes formal dinners, \
talk/receptions, and outdoor events. Some are for members only, others are open to all alumni.<br>\
<b>Other Events</b> includes such things as concerts by College Choirs, visiting College or \
University sports team events, and events organized by Cambridge in America or Oxford North America.<br>\
<b>OxCam10</b> includes informal events organized by OxCam10 for alumni within 10 years of graduation."

# Paid membership categories, else empty list:
MEMBER_CATEGORIES = ['Full', 'Student']

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

# email settings -development (uses Mailgun Sandbox, limited addressees)
SMTP_SSL = False
SMTP_SERVER = "smtp.mailgun.com:587"
SMTP_SENDER = "OxCamNE Development <test@oxcamne.org>"
SMTP_LOGIN = "postmaster@<--- sandbox account key --->"
SMTP_TLS = True
# smaller organizations (up to a few hundred on mailing list) could even
# use a free gmail account.

# payment processor (currently only stripe implemented):
PAYMENT_PROCESSOR='stripe'  
#Stripe settings development keys and id's
STRIPE_PKEY = "<--- test public key --->"
STRIPE_SKEY = "<--- test secret key --->"
# generic product for event registration:
STRIPE_EVENT = "<--- test product id --->"
# specific products for membership dues
#STRIPE_PROD_FULL = "<--- test product id -->"  #Annual, autorenews
STRIPE_PROD_FULL = "<--- test product id -->"   #Weekly, autorenews
STRIPE_PROD_STUDENT = "<--- test product id -->"    #Annual, no autorenew
```

## Contributors and Collaborators

The software was developed by David Manns for use in running the Oxford & Cambridge Society of New England. It is Oxford & Cambridge centric in that it is designed for matriculated alumni, who must provide their Oxbridge
College and matriculation list in order to subscribe to mailing lists, register for events, etc.

As noted in the [Installation](#installation) section, it is easily configured for different groups, though it is still somewhat US centric.

For support, questions, or if you wish to collaborate on improving the software please contact <secretary@oxcamne.org>.
