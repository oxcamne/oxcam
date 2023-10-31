# oxcam

## Introduction

OxCam is a web based database app designed to support Oxford and/or Cambridge Alumni groups and Societies.
It can be deployed on low cost cloud services such as PythonAnywhere or Linode (Akamai) at very low cost.

At it's simplest it can be used to maintain a mailing list and send out notices.

One or more paid membership categories can be implemented, either sending renewal reminders
or using autopay subscriptions, and collecting dues payments through a payment processor such as
Stripe. Members will have access to an online directory.

It can track events and provide registration capabilities including payment collection, maintaining a wait
list, etc.

By uploading transaction files (in .csv format) from banks and payment processors it can maintain
comprehensive accounts.

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
    git clone https://github.com/oxcamne-secretary/oxcam.git
```

This clones the software into a new directory apps/oxcam. You next need to create a 'settings_private.py' file in apps/oxcam. Customize the contents from:

```python
"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""
import datetime
from dateutil import tz

SOCIETY_NAME = 'Oxford & Cambridge Society of New England'
SOCIETY_DOMAIN = 'OxCamNE'  #short name, ideally internet domain
LETTERHEAD = '<h2><span style="color: blue">\
<em>Oxford and Cambridge Society of New England</em></span> \
<img src="https://oxcamne.pythonanywhere.com/oxcam/static/images/oxcamne_no_pad.png" \
alt="logo" style="float:left;width:100px" /></h2>\
<h3><span style="color: blue"><em>&lt;subject&gt;</em></span></h3>'
        #NOTE 'subject' replaced by subject line in emails/notices

DB_URL = "http://127.0.0.1:8000/oxcam"  #URL for this instance, development local server in this case
SUPPORT_EMAIL = 'dgmanns@gmail.com'
HOME_URL = 'https://www.oxcamne.org'    #the group's web site
VISIT_WEBSITE_INSTRUCTIONS = "<br><br>Visit us at www.oxcamne.org or \
https://www.instagram.com/oxcamne/ or www.facebook.com/oxcamne"
IS_PRODUCTION = False   #if False, various email notifications are suppressed
#within the database, time and datetime will use local time specified here
TIME_ZONE = tz.gettz('America/New_York') #see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
MEMBERSHIP = "Membership is open to all matriculated alumni and members of the \
Universities of Oxford and Cambridge.<br><br>\
Annual dues are $30 payable by subscription. In future years, you'll receive a \
reminder a week before the next auto-payment is made. \
Full time students, or those graduated within the last 12 months, qualify for student \
membership at $10 (please note your course and graduation date).<br><br>"
ACCESS_LEVELS = ['read', 'write', 'accounting', 'admin']

MEMBER_CATEGORIES = ['Full', 'Student'] #empty list if no paid membership
GRACE_PERIOD = 45
"""
Renewal within this number of days after expiration extends membership
continuously from the expiration date.
Also, member can renew this number of days prior to expiration. 
Renewal notices are sent at expiration plus -9, 0, 9, 18 days.
Auto renewal will be attempted multiple times at the anniversary of payment
and during following 3 weeks. So we set the grace period to cover 18+21 \
days.

Database connector. SQLite is built into Py4web and should be 
adequate except for very large groups.
on PythonAnywhere you can use MySQL, e.g.:
DB_URI = f"mysql://oxcamne:{MYSQL_PASSWORD}@oxcamne.mysql.pythonanywhere-services.com/oxcamne$default"
"""
DB_URI = "sqlite://storage.db"
DB_POOL_SIZE = 10

#Documents the mailing lists defined in Table Email_Lists:
MAIL_LISTS = "The <b>Member Events</b> list is used for notices of all Society in-person events \
except <b>Pub Nights</b> and <b>Online</b> (only) Events. This includes formal dinners, \
talk/receptions, and outdoor events. Some are for members only, others are open to all alumni.<br>\
<b>Other Events</b> includes such things as concerts by College Choirs, visiting College or \
University sports team events, and events organized by Cambridge in America or Oxford North America.<br>\
<b>OxCam10</b> includes informal events organized by OxCam10 for alumni within 10 years of graduation."
# email settings:
SMTP_SSL = False
SMTP_SERVER = "smtp.mailgun.com:587"    #or other SMTP provider
SMTP_SENDER = "descriptive_name <reply_to_email>" 
SMTP_LOGIN = "sending_email_address:password"
SMTP_TLS = True

PAYMENT_PROCESSOR='stripe'  #default pp for new members
#Stripe settings development keys and id's
STRIPE_PKEY = "public_key"
STRIPE_SKEY = "secret_key"
#the following will depend on defined membership classes
STRIPE_PROD_FULL = "product_code"   #subscription
STRIPE_PROD_STUDENT = "product_code"    #non-recurring, re-validate each year
#Stripe Product for charging event tickets (price variable)
STRIPE_EVENT = "product_code"

```
