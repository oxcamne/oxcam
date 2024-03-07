# [Oxford/Cambridge Alumni Group Database - Support Guide](support.md)

## Installation

The oxcam software is held on Github at [https://github.com/oxcamne/oxcam](https://github.com/oxcamne/oxcam). This section assumes that you have read the README displayed there and satisfied the pre-requisites, so that you have a web server successfully running Py4web.

On your server open a bash terminal session at the py4web 'apps' directory, issue the commands:

```bash
    git clone https://github.com/oxcamne/oxcam.git
    pip install --upgrade -r oxcam/requirements.txt
```

This clones the software into a new directory apps/oxcam, and ensures that necessary Python packages are installed. You may need to precede 'pip' with 'python ' or 'python3 ' depending on your environment.

Note that if you are installing on Pythonanywhere, you can open a bash terminal session (they call this a console) from various places on their site, and that from the 'Files' tab you can edit files, such as the settings file described below.

### Configure the software for your organization

You next need to create a 'settings_private.py' file in apps/oxcam. Customize the contents from the code below, which is taken from the OxCamNE environment (with sensitive keys removed). A copy of this is included in the kit as settings_private_template.py which you can copy or rename:

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
```

Notes:

1. As shown here, the locale is set to the server default settings. It could be set to any supported locale. The  locales supported on the server can be listed using the 'locale' terminal command. Setting the locale determines the date format used and the currency symbol.

1. The database is configured to use SQLite - this probably provides adequate performance
for all but the largest groups.

1. Setting IS_PRODUCTION False only prevents the daily maintenance process from
sending out notices such as membership dues reminders. Any test environment can still send out email, but will suppress all email except to ALLOWED_EMAILS.

1. Set THREAD_SUPPORT True only if your environment supports threading. PythonAnywhere does not, but typically a desktop development environment does. If set True, then the email daemon is started in its own thread whenever py4web/oxcam is started, and in turn spawns the daily_maintenance job in its own thread at midnight.

1. There are various 'branding' elements such as logo, organization name,
web site addresses, help site address (for volunteers), support email, etc.
The help site might embed the [User Guide](https://oxcamne.github.io/oxcam) and
possible also this [support guide](https://oxcamne.github.io/oxcam/support) as
well as including organization specific information.

1. A single mailing list is assumed. An organization can operate multiple
mailing lists. MAIL_LISTS is simply an html description, the mailing lists
themselves are set up in the database Email_Lists table. A mailing list should be defined and present in the database even it is not going to be used.

1. In the prototype membership categories are included for full and student
members. If you do not have paid memberships MEMBER_CATEGORIES should be an empty list, '[]'.

1. The email settings configure two SMTP servers. One is used for transactional emails, such as login email verification, transaction confirms, and emails addressed explicitly, the other for bulk emails, sent to mailing list or filtered sets of members. OxCamNE uses an email service provider which, among other things, ensures that messages are authenticated by SPF and DKIM records. Small groups could use, e.g. a gmail address with an app password. In production, for transactional messages we use our google workspace account directly, whereas bulk messages are sent via our email service provider, mailgun. These settings should be present even if you are not using mailing list functionality.

1. There is a group of settings for the Stripe payment processor, which is currently the only supported payment processor. These include public and private account keys, and product identifiers corresponding to the membership categories. Go [here](stripe.md) for more information on setting up and using Stripe.

### Start the database

Once the app is installed and your settings_private.py file is configured you should restart py4web. If py4web is already running you can use the 'Reload Apps' button in the 'Installed Applications' section of the Py4web Dashboard. You should now see the oxcam app running
as an installed application.

When first started the app creates an empty database in a databases/ folder in the py4web/apps/oxcam directory.

### Load a Minimal Database

Browse to the database at \<your_py4web_url\>/oxcam. You will be asked to login using your email. Oxcam sends a one-time
link to your email. The link opens a new tab ready for you to upload a copy of database contents:

![db_restore form](images/db_restore.png)

The kit contains a file, db_oxcam_minimal.csv in the py4web/apps/oxcam directory. Csv files are used to backup and restore the contents of the database.
The minimal database defines the Colleges table including all the
Oxford and Cambridge Colleges, defines the default mailing list, a prototype chart of accounts, sample bank and payment processor records as well as some bank rules.

To use the minimal database file, copy it from the kit to your local device where you browser is running. Click Browse and find the .csv file, then click restore. You will then need to login once more, and will be taken to the index page:

![inital index](images/Initial_index.png)

### Add yourself to the database

The database does not contain any member records so can not do anything very interesting. If you do not have membership configured, you'll see only the
mailing list option. Either joining the mailing list or as a member creates a
member record. The form to join the mailing list looks like:

![mailing list](images/mailing_list.png)

Once you have created your own record, as it is first into the database it is automatically assigned 'admin' access and all the function links appear on the navigation bar:

![navigation bar](images/navigation_bar.png)

If your group is for alumni of only one of the Universities, you may wish to eliminate the irrelevant Colleges. You can use **db_tool** to do this.

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
