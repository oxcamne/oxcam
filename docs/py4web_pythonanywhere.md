# [Oxford/Cambridge Alumni Group Application - Support Guide](support.md)

## Installation of py4web on Pythonanywhere

The py4web documentation has a [section describing how to do this](https://py4web.com/_documentation/static/en/chapter-03.html#deployment-on-pythonanywhere-com) using a tutorial, however I suggest a modified workflow which installs py4web using pip, which will install the latest formally released version. This is described below.

Create a Pythonanywhere account, which will leave you at the Pythonanywhere dashboard.

### Specify the System Image and Python Version to be used

Click on 'Account' at top right and then select the System Image tab.

Edit 'Current system image' selecting the lowest (newest) entry in the dropdown.

Edit all three python version selections using the dropdowns to select and save as 3.13 (or the highest available python version).

Then return to the *Dashboard* tab of the Pythonanywhere console.

```bash
14:27 ~ $
```

Confirm that the correct version of python is running by typing the command **`python --version`**

Next create a py4web directory using the command **`mkdir py4web`** and switch to it using the command **`cd py4web`**.

### Create Virtual Environment

This section is optional. In general a PA account will be used solely to support a single Py4web instance, and I see little benefit in having a venv.

Open a bash terminal session by clicking the blue button at bottom left. You should see a terminal prompt like:

Next create a virtual environment, a newly built python environment for your webapp using the commands:

**`python3.13 -m venv venv`**
**`source venv/bin/activate`**

Note that, once again, you specify the python version to be used. Your bash prompt should now look like:

**`(venv) 12:34 ~/py4web $`**

### Install the Py4web Software

Enter the command **`pip install --upgrade py4web`**

This installs the latest released version of py4web and all its dependencies.

Complete the installation by running the command **`py4web setup apps`**. Answer 'Y' to create the `apps` folder, then answer the questions relating to each py4web app. You can answer 'N' to most of them, but be sure to answer 'Y' to **_dashboard, _default, _documentation, _minimal, and _scaffold**.

Provide a secure password for the py4web dashboard, making sure to keep track of it for future use! You need to enter the password twice to have it confirmed and stored. You can use the command **`py4web set_password`** to create or change the password at any time.

After the password is stored, you will be prompted:

`Type "/home/your_username/.local/bin/py4web run apps" "to start the py4web server.`

***DO NOT DO THIS!!*** Your environment is not yet ready to run.

### Create your Py4web Website

Switch to the *Web* tab in a new browser tab by clicking on 'web' in the menu at top right. The web page should show that you have no web apps. Click the blue button to start the process of creating a new app. This will display a box showing what the URL of you site will be. You will see that it uses your Pythonanywhere username. You will append `'/oxcam'` to form the base URL that you will actually use for the public website, or `'/_dashboard'` to access the py4web dashboard.

Click next, and at the following screens select **Manual Configuration** and next the latest version of Python 3, then next again past the Manual Configuration notice to return to the *Web* tab.

Clicking next returns you to the *Web* tab. Scroll down to the 'Code' section. Edit the source code and working directories (by clicking on them) so that they are ***both '/home/your_username/py4web'*** (fill in your Pythonanywhere username).

If you created a venv, in the Virtualenv section edit the link to `home/your_username/py4web/venv`. For future reference, note the useful link for starting a bash console in the virtual environment. Use this in preference to most other ways of starting a bash console, where you would need to activate the environment using `source ~/py4web/venv/bin/activate`.

### Edit the WSGI configuration file

Click the link for WSGI configuration file and your WSGI configuration file appears in an editor. Click on the link to open the editor and replace the entire contents with:

```python
import os
import sys

# Add your py4web apps directory to the path
project_home = '/home/dgmanns/py4web/apps'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import the py4web application
from bottle_app import application
```

Be sure to **Save** the edited file using the button at the top of the screen!

Make sure the Python version shows the latest version, edit if necessary.

### Update the bottle_app.py File

Switch to *Files* tab using the menu at top right, and click on 'py4web' on the left side to open that directory. You should find bottle_app.py in the contentse. Click on the small edit (pencil) icon beside it to open it in the editor. If necessary create a new file with that name. Select and delete any existing content and copy and paste the following:

```python
import os
from py4web.core import wsgi

# BEGIN CONFIGURATION
PASSWORD_FILENAME = 'password.txt'
DASHBOARD_MODE = 'full' or 'demo' or 'none'
APPS_FOLDER = 'apps'
# END CONFIGURATION

password_file = os.path.abspath(os.path.join(os.path.dirname(__file__), PASSWORD_FILENAME))
application = wsgi(password_file=password_file, 
                   dashboard_mode=DASHBOARD_MODE,
                   apps_folder=APPS_FOLDER)
```

Be sure to **Save** the edited file using the button at the top of the screen!

Return to the *Web* tab.

### Other Settings

In the Static files section, add the two items:

|URL|Directory|
|---|---|
|/robots.txt|/home/your_username/py4web/apps/oxcam/static/robots.txt|
|/oxcam/static/|/home/your_username/py4web/apps/oxcam/static/|

Under Security, Force HTTPS: should be enabled.

### Start the Webapp

Click the big green button to load the application.

Open a new browser tab to check you have a working py4web installation.

Browse to [https://your_username/pythonanywhere.com/_dashboard](https://your_username/pythonanywhere.com/_dashboard) (as usual you need to replace your_username with your Pythonanywhere username), and you should be prompted for the password you selected earlier. You are now (hopefully) looking at the py4web dashboard. You will be using this to install the oxcam app.

Continue to [install the oxcam app in your new py4web site](install#download-the-latest-version-of-the-oxcam-software).
