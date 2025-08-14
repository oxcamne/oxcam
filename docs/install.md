# [Oxford/Cambridge Alumni Group Application - Support Guide](support.md)

## Installation

The oxcam software is held on Github at [https://github.com/oxcamne/oxcam](https://github.com/oxcamne/oxcam). This section assumes that you have read the [README](https://github.com/oxcamne/oxcam?tab=readme-ov-file) displayed there and satisfied the pre-requisites, so that ***you have a web server successfully running Py4web***.

This documentation is intended for groups adopting oxcam to run it's website and database.

For technical users contributing to the support/development of the software, see [development installation](development_install).

### Find the latest version of the oxcam software

Browse to [https://github.com/oxcamne/oxcam](https://github.com/oxcamne/oxcam) and click on the latest version of OxCam on the releases section of the page. You should see something like:

![oxcam_version](images/oxcam_version.png)

Right-click on the Source code (zip) link and select 'copy link'

### Install the oxcam software on your server

On your server open a bash terminal session (you may already have a bash session in a browser tab from installing py4web). Navigate to the parent of the py4web directory (cd ~ if you are on Pythonanywhere), then, pasting in the copied link:

```bash
    wget https://github.com/oxcamne/oxcam/archive/refs/tags/v1.0.0.zip
    unzip v1.0.0
    mv oxcam-1.0.0 py4web/apps/oxcam
    pip install --upgrade -r py4web/apps/oxcam/requirements.txt
```

This copies the software into a new directory apps/oxcam, and ensures that necessary Python packages are installed. You may need to precede 'pip' with 'python ' or 'python3 ' depending on your environment.

You should also have the Py4web dashboard (<your_py4web_url>/_dashboard) running in a browser tab.

### Restart Py4web, Check that Oxcam is running

Expand the top (Installed Applications) tab of the Py4web dashboard, and **click the Reload Apps button.** You should now see oxcam in the list of running apps.

### Start Oxcam and Initial Configuration

In a new browser tab, start the oxcam app (<your_py4web_url>/oxcam). You should see a screen like this:

![setup_oxcam](images/setup_oxcam.png)

Follow the on-screen instructions to define the email account to be used by oxcam. Normally you would also tick the 'load minimal database' checkbox.

After successfully submitting the form, return to the Py4web dashboard and **click the Reload Apps button again**.

### Complete the customization for your group

You need to edit the settings_private.py file just created. You can use the Py4web dashboard app to do this, restarting the running apps after all edits.

In the dashboard 'Installed Applications' section, click on the 'oxcam' app. Then find 'settings_private.py' in the 'Files in oxcam' section. This opens the file in an editor, it will look like:

```python
"""
Configures the app for a particular alumni group/Society,
and for a particular running instance, e.g. production or development
Customize for your organization and instance
"""

# organization name and domain/short_name, etc:
SOCIETY_NAME = 'your_group_name'
SOCIETY_SHORT_NAME = 'your_group_short_name'    #ideally, the domain name omitting the .xxx part
                #also use as your username if using Pythonanywhere server
SOCIETY_LOGO = 'oxcamne_no_pad.png'             #should be placed in py4web/apps/oxcam/static directory
                #Your favicon.ico should also be placed in py4web/apps/oxcam/static directory
                #note, oxcamne_no_pad.png and favicon.ico are part of the distribution and have both university arms

DB_URL = f'your_database_server_url'   #e.g. https://{SOCIETY_SHORT_NAME}.pythonanywhere.com/oxcam

SUPPORT_EMAIL = 'oxcamne@oxcamne.org'

# html trailer for email notices:
VISIT_WEBSITE_INSTRUCTIONS = f"<br><br>Visit us at 'your_web_site_url' or 'your_social_media'"
                #your_web_site_url might be www.{SOCIETY_SHORT_NAME}.org or similar, or {DB_URL}/web/home

from dataclasses import dataclass
import decimal

@dataclass
class Email_Account:
    server: str
    port: int
    username: str
    password: str

#SMTP server for sending transactional messages (e.g. a gmail account)
SMTP_TRANS = Email_Account("smtp.gmail.com", 587, "oxcamne@oxcamne.org", "uajlvccbmkekakja")

#SMTP server for sending bulk messages (e.g. a mailing service such as mailgun)
#for small groups, this can be the same as SMTP_TRANS
SMTP_BULK = SMTP_TRANS

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

#on Test/Development instance, email is suppressed except to the following listed emails:
ALLOWED_EMAILS = []

class PaymentProcessor:
    def __init__(self, name, public_key, secret_key, dues_products):
        self.name = name    #should be lower case, single word (underscore allowed)
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
            'Full': "<-- stripe product id -->",
            'Student': "<-- stripe product id -->"
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

VERIFY_TIMEOUT = 3   #minutes enforced between verification emails

"""
Review the following settings and adjust as needed, but no changes are likely to be needed
"""

# html web page banner Customize:
PAGE_BANNER = f'<h4><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h4>'

# html letterhead for email/notices:
LETTERHEAD = f'<h2><span style="color: blue"><em>{SOCIETY_NAME}</em>\
<img src="https://oxcamne.pythonanywhere.com/oxcam/static/{SOCIETY_LOGO}" alt="logo" style="float:left;width:100px" /></span></h2><br><br>'
# note, on a development instance, this must refer to the production server, as email services don't
# have access to the local server.

"""
To use a database other than SQLite, define the database URI and pool size.
SQLite is built into Py4web and should be adequate except for extremely large groups.
For example, if using PythonAnywhere, you can use MySQL:
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
```

Notes:

1. As shown here, the locale is set to the server default settings. It could be set to any supported locale. The  locales supported on the server can be listed using the 'locale' terminal command. Setting the locale determines the date format used and the currency symbol.

1. The database is configured to use SQLite - this probably provides adequate performance
for all but the largest groups.

1. Adding email addresses to ALLOWED_EMAILS prevents email being sent to any other addresses. Note that in a test environment you can use test keys for Stripe and other services.

1. Set THREAD_SUPPORT True only if your environment supports threading. PythonAnywhere does not, but typically a desktop development environment does. If set True, then the email daemon is started in its own thread whenever py4web/oxcam is started, and in turn spawns the daily_maintenance job in its own thread at midnight.

1. There are various 'branding' elements such as logo, organization name,
web site addresses, help site address (for volunteers), support email, etc.
The help site might embed the [User Guide](https://oxcamne.github.io/oxcam) and
possible also this [support guide](https://oxcamne.github.io/oxcam/support) as
well as including organization specific information.

1. In the prototype membership categories are included for full and student
members, as used by OxCamNE, but are commented out. You can uncomment them by moving the enclosing """ line.

1. The email settings configure two SMTP servers. One is used for transactional emails, such as login email verification, transaction confirms, and emails addressed explicitly, the other for bulk emails, sent to mailing list or filtered sets of members. OxCamNE uses an email service provider which, among other things, ensures that messages are authenticated by SPF and DKIM records. Small groups could use, e.g. a gmail address with an [app password](https://support.google.com/accounts/answer/185833?hl=en). In production, for transactional messages we use our google workspace account directly, whereas bulk messages are sent via our email service provider, mailgun. These settings should be present even if you are not using mailing list functionality.

1. PaymentProcessor is a base class for all payment processors that might be supported. Each supported payment processor will be implemented as a subclass of PaymentProcessor. PAYMENTPROCESSORS is a list of payment processor instances, currently only Stripe has been written. The first one in the list is the default for new customers. The implementations are in pay_processors.py. Currently, oxcam supports [Stripe](stripe.md) as its payment processor.

1. You can set up Google reCaptcha for production and development. Once a user successfully signs in, the IP address will be trusted for 90 days and Captcha will not be enforced during that period.

1. Setting VERIFY_TIMEOUT to a non-zero value enforces a time-out between sending verification emails to a particular email address or IP address. Like reCaptcha, this is an anti-spammer tool.

### Start Building Your Database

Open a new browser tab and browse to <your_py4web_url>/oxcam. Login using your personal email. The address you specified in the setup form will be used to send an email verification message to your personal account.

If you checked 'Load Minimal Database' in the setup form, the login will take you to the My Account menu which will include the option to join the mailing list. Joining the mailing list will create your 'member' account with full admin privileges. You now have a working Oxcam system that can manage a mailing list and free events, but without paid events, paid membership categories, online payments, or accounting.

The minimal database initializes the content copied from our OxCamNE database in the tables: Colleges, Email_Lists, Pages, CoA, Bank_Accounts, and Bank_Rules. Any and all of these tables you may wish to edit once your are up and running, for example many of the web pages may be inapplicable or need modification for your group.

If your group is for alumni of only one of the Universities, you will wish to eliminate the irrelevant Colleges. You can do this by going to the 'Databases in Oxcam' section of the Py4web dashboard and clicking the button for the db.Colleges table. Type e.g. 'name contains oxford' to identify the colleges you **don't** want and then you can easily delete them.

If you did not load the Minimal Database, the login will take you to a database restore page:

![db_restore form](images/db_restore.png)

Use the 'browse' button to locate the backup database you wish to load. You do not need to click 'clear existing database'. After the database is loaded, you will need to log in again which will connect with your record in the restored database.

### Scheduled Tasks

Oxcam uses two additional tasks that run separately from the web server.
If your environment supports threads, and you configure 'THREAD_SUPPORT = True',
nothing more is needed:

- the email daemon runs all the time in its own thread. It's role is to spool
out notices to a mailing list or other selection of members. These emails may
be customized with a greeting or other information, such as registration details.

- the daily maintenance task is triggered at midnight local time each day. It's
role is to send out any necessary membership renewal reminders, and to generate
a database backup .csv file. It retains on the local drive the last month's daily files, and files from the 1st of each month for a year.

In the PythonAnywhere enviroment, the email daemon is configured as a 'run forever'
task, and the daily maintenance job is scheduled at a fixed UTC time daily. The commands to use are:

```bash
py4web/py4web.py call py4web/apps oxcam.email_daemon.email_daemon

py4web/py4web.py call py4web/apps oxcam.daily_maintenance.daily_maintenance
```
