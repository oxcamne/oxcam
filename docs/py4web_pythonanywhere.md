# [Oxford/Cambridge Alumni Group Application - Support Guide](support.md)

## Installation of py4web on Pythonanywhere

The py4web documentation has a [section describing how to do this](https://py4web.com/_documentation/static/en/chapter-03.html#deployment-on-pythonanywhere-com) using a tutorial, however I suggest a modified workflow which installs py4web using pip, which will install the latest formally released version. This is described below.

Create a Pythonanywhere account, which will leave you at the Pythonanywhere dashboard.

### Specify the System Image and Python Version to be used

Click on 'Account' at top right and then select the System Image tab.

Edit 'Current system image' selecting the lowest (newest) entry in the dropdown.

Edit all three python version selections using the dropdowns to select and save as 3.13 (or the highest available python version).

Then return to the *Dashboard* tab of the Pythonanywhere console.

### Install the Py4web Software

Open a bash terminal session by clicking the blue button at bottom left. You should see a terminal prompt like:

```bash
14:27 ~ $
```

Enter the command **`python3 -m pip install --upgrade py4web --no-cache-dir --user`**

This installs the latest released version of py4web and all its dependencies.

Next create a py4web directory using the command **`mkdir py4web`** and switch to it using the command **`cd py4web`**.

Complete the installation by running the command **`py4web setup apps`**. Answer 'Y' to create the `apps` folder, then answer the questions relating to each py4web app to install. You can answer 'N' to most of them, but be sure to answer 'Y' to **_dashboard, _default, _documentation, _minimal, and _scaffold**.

Provide a secure password for the py4web dashboard, making sure to keep track of it for future use! You need to enter the password twice to have it confirmed and stored.

After the password is stored, you will be prompted:

`Type "/home/davidmanns/.local/bin/py4web run apps" "to start the py4web server.`

**Do Not do this !!**

But do not close the bash terminal tab in your browser as you may need it later when installing **oxcam**.

### Create your Py4web Website

Open the *Web* tab in a new browser tab by right clicking on 'web' in the menu at top right and selecting 'open in new tab'. The web page should show that you have no web apps. Click the blue button to start the process of creating a new app. This will display a box showing what the URL of you site will be. You will see that it uses your Pythonanywhere username. You will append `'/oxcam'` to form the base URL that you will actually use for the public, or `'/_dashboard'` to access the py4web dashboard.

Click next, and at the following screens select **Bottle** and then the latest version of Python 3.

You will then reach the **Quickstart New Bottle Project** dialog. You need to edit the displayed path to be `/home/your_username/py4web/bottle_app.py` (***you will need to change 'mysite' to 'py4web'***).

Clicking next returns you to the *Web* tab. Scroll down to the 'Code' section. You may need to edit the source code or working directories (by clicking on them) so that they are ***both '/home/your_username/py4web'***.

### Edit the WSGI configuration file

Click the link for WSGI configuration file and your WSGI configuration file appears in an editor. You may need to edit the project_home definition so that it reads:

`project_home = '/home/your_username/py4web/apps'`

Be sure to **Save** the edited file using the button at the top of the screen!

### Update the bottle_app.py File

Switch to *Files* tab using the menu at top right, and click on 'py4web' on the left side to open that directory. You should find bottle_app.py in the contents. Click on the small edit (pencil) icon beside it to open it in an editor. Select and delete the existing content and copy and paste the following:

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

Return to the *Web* tab and click the big green button to reload the application.

Open a new browser tab to check you have a working py4web installation.

Browse to [https://yourusername/pythonanywhere.com/_dashboard](https://yourusername/pythonanywhere.com/_dashboard) (you need to replace yourusername with your Pythonanywhere username), and you should be prompted for the password you selected earlier.

Continue following the [install](install#find-the-latest-version-of-the-oxcam-software) script to install the oxcam app in your new py4web installation.
