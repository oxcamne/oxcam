# [Oxford/Cambridge Alumni Group Application - Support Guide](support.md)

## Installation

This documentation is intended for groups adopting oxcam to run it's website and database.

The oxcam software is held on Github at [https://github.com/oxcamne/oxcam](https://github.com/oxcamne/oxcam). This section assumes that you have read the [README](https://github.com/oxcamne/oxcam?tab=readme-ov-file) and that you have a web server ready to host py4web and, within that, the oxcam app.

The server might be an account on a cloud based hosting service such as [Pythonanywhere](https://www.pythonanywhere.com). The more technically adept could use a desktop Mac, Windows, or Linux machine.

For technical users contributing to the support/development of the oxcam app, see [development installation](development_install) for information on setting up your development environment.

### Install Py4web

If you are installing on Pythonanywhere, [please follow this process](py4web_pythonanywhere). You will use the Pythonanywhere console to start, stop and restart your py4web server.

Otherwise, follow the [Py4web Installing from pip, using a virtual environment](https://py4web.com/_documentation/static/en/chapter-03.html#installing-from-pip-using-a-virtual-environment) instructions to install and start py4web. If you are restarting your terminal to run py4web remember to re-enable your venv:

```bash
. venv/bin/activate
py4web run apps
```

Verify that you can open the Py4web dashboard (<your_py4web_url>/_dashboard) in a new browser tab, using the password you setup when installing py4web. When you expand the 'Installed Applications' section it should look something like this:

![py4web dashboard](images/py4web_dashboard.png)

Keep this dashboard open for use later!

### Find the latest version of the oxcam software

Browse to [https://github.com/oxcamne/oxcam](https://github.com/oxcamne/oxcam) and click on the latest version of OxCam on the releases section on the right of the page. You should see something like:

![oxcam_version](images/oxcam_version.png)

Right-click on the Source code (zip) link and select 'copy link'

### Install the oxcam software on your server

On your server open a bash terminal session (you may already have a bash session in a browser tab from installing py4web). Navigate to the parent of the py4web directory (cd ~ if you are on Pythonanywhere), then, pasting the copied link into the wget  or curl command:

on Linux:

```bash
    wget https://github.com/oxcamne/oxcam/archive/refs/tags/v1.1.0.zip
    unzip v1.1.0
    mv oxcam-1.1.0 py4web/apps/oxcam
    pip install --upgrade -r py4web/apps/oxcam/requirements.txt
```

on Mac:

```bash
    curl -LO https://github.com/oxcamne/oxcam/archive/refs/tags/v1.1.0.zip
    unzip v1.1.0
    mv oxcam-1.1.0 ~/apps/oxcam
    pip install --upgrade -r ~/apps/oxcam/requirements.txt
```

This copies the software into a new directory apps/oxcam, and ensures that necessary Python packages are installed. You may need to precede 'pip' with 'python ' or 'python3 ' depending on your environment.

### Restart Py4web, Check that Oxcam is running

Expand the top (Installed Applications) tab of the Py4web dashboard, and **click the Reload Apps button.** You should now see oxcam in the list of running apps. It will indicate in red if it did not load correctly.

### Start Oxcam and Initial Configuration

In a new browser tab, start the oxcam app (<your_py4web_url>/oxcam). You should see a screen like this:

![setup_oxcam](images/setup_oxcam.png)

Follow the on-screen instructions to define the email account to be used by oxcam. Normally you would also tick the 'load minimal database' checkbox.

After successfully submitting the form, return to the Py4web dashboard and **click the Reload Apps button again**.

### Complete the customization for your group

You need to edit the settings_private.py file just created. You can use the Py4web dashboard app to do this, restarting the running apps after saving all edits.

In the dashboard 'Installed Applications' section, click on the 'oxcam' app. Then find 'settings_private.py' in the 'Files in oxcam' section. This opens the file in an editor (scroll down if necessary).

This is a Python file, and the Dashboard's editor is python aware, so it will flag syntax errors. The file is self documented, go through it carefully to make the necessary customizations.

### Start Building Your Database

Open a new browser tab and browse to <your_py4web_url>/oxcam. Login using your personal email. The address you specified in the setup form will be used to send an email verification message to your personal account.

If you checked 'Load Minimal Database' in the setup form, the login will take you to the My Account menu which will include the option to join the mailing list. Joining the mailing list will create your 'member' account with full admin privileges. You now have a working Oxcam system that can manage a mailing list and free events, but without paid events, paid membership categories, online payments, or accounting.

The minimal database initializes the content copied from our OxCamNE database in the tables: Colleges, Email_Lists, Pages, CoA, Bank_Accounts, and Bank_Rules. Any and all of these tables you may wish to edit once your are up and running, for example many of the web pages may be inapplicable or need modification for your group, but having all these elements in the minimal database provides useful templates.

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

### How to update the oxcam app when a newer version is released

Start by finding the latest version of the oxcam app on Github as described earlier, and copying the .zip link.

On your web server open a bash terminal session. Navigate to the parent of the py4web directory (cd ~ if you are on Pythonanywhere), then, pasting in the copied link in the wget command and using the current latest version:

on Linux:

```bash
    wget https://github.com/oxcamne/oxcam/archive/refs/tags/v1.1.0.zip
    unzip v1.1.0
    cp -r --force oxcam-1.1.0/. py4web/apps/oxcam
    pip install --upgrade -r py4web/apps/oxcam/requirements.txt
```

on Mac:

```bash
    curl -LO https://github.com/oxcamne/oxcam/archive/refs/tags/v1.1.0.zip
    unzip v1.1.0
    cp -R oxcam-1.1.0/. ~/apps/oxcam
    pip install --upgrade -r ~/apps/oxcam/requirements.txt
```

You must restart Py4web, e.g. using the big green button on the Pythonanywhere Console Web tab or
clicking the Reload Apps button on the Py4web Dashboard.

### How to update to a new release of Py4web

With a system or bash terminal at your py4web directory run the command:

`python3 -m pip install --upgrade py4web`

This will not update the built in apps, most importantly the _dashboard. *To update these, first go the py4web/apps directly and delete all the apps **other than oxcam**.* Then return the terminal to py4web and run:

`py4web setup apps` or `python3 py4web setup apps`

Finally, you must restart py4web.
