# [Oxford/Cambridge Alumni Group Application - Support Guide](support.md)

## Development Installation

For development purposes you can use any Windows, Mac, or Linux machine to set up a development and local host web server for testing. This page documents the setup of a Mac environment; the alternatives would be similar.

### Prerequisites

You will be using the terminal app, or bash depending on your environment, in what follows.

You need to have Python installed. It should be version 3.8 or higher. The [Python.org](https://www.python.org/downloads/) website makes it most convenient to download the latest version of Python which at the time of writing is 3.13.6

On the Mac or Linux, the most convenient way to install python is to use 'homebrew', which also makes it easy to select Python versions other than the latest. Homebrew is also the way to install git, which is also required. You can [install homebrew here](https://brew.sh/).

Once homebrew is installed, you can install git, and Python, with the following commands on a terminal (if you need to install an earlier version of python, specify as, e.g. python@3.11):

```bash
$ brew install git
...
$ brew install python
...
```

If you are going to use VScode, as recommended, [download and install it](https://code.visualstudio.com/download). The rest of this document assumes the use of VScode.

### Install Py4web and OxCam Source Code from Github

First identify where you wish to put a source code distribution of py4web, which will also include our proprietary software. It will all be contained in a folder 'py4web'.

Open a terminal and navigate to where you want to place the py4web folder. Download the py4web code and the oxcam code using the following commands:

```bash
git clone https://github.com/web2py/py4web.git
...
cd py4web/apps
git clone https://github.com/oxcamne/oxcam.git
...
```

This creates the py4web folder (directory) and downloads the latest version of py4web along with a copy of it's git repository and then, within py4web's apps folder, the latest version of oxcam with a copy of its git repository. In development you would normally use the latest version software on the main branches of these products on Github.

At this point we are done with the standalone terminal window, and will continue using vscode.

### Set up VScode and Python Virtual Environment

Launch Vscode, and open the workspace on the py4web folder you have now created. This is a good time to install the Vscode extensions you may need. Make sure the Microsoft IntelliSense Python extension is included. I also recommend installing the Git History extension (Don Jayamanne).

Before continuing, it is good practice to set up a python virtual environment for the workspace we just created, to ensure that we have a stable python setup which matches that in production, regardless of other versions of python which may be installed on your machine.

In the Code/View menu click on Command Palette... and search for the Python: Create Environment command. Click on it, and then select Venv. You will then be presented with a list of possible Python versions found on your machine. Tick the boxes to process the oxcam requirements.txt file. This will include all the additional python modules oxcam needs in the venv (you may see only oxcam listed - py4web no longer uses a requirements.txt file and it's dependencies will be added later).

Then in Command Palette find the Python: Select Interpreter. Click on this and then in the list presented click on the venv that you just created. This ensures that Py4web will always use this environment.

### Finish Setting Up Py4web

Once the virtual environment is set up, you can use a terminal window within VScode to complete the Py4web installation. You may need to open a terminal window by selecting Terminal in the View menu. Your prompt might be something like:

```(.venv) davidmanns@Mac py4web %```

The (venv) confirms that you are operating in the virtual environment. As shown you should be looking at the py4web folder itself. Now execute the commands:

```bash
make assets
make test
pip install  --upgrade -r ./apps/oxcam/requirements.txt
py4web setup apps
py4web set_password
```

This password is for running the Py4web dashboard on the localhost [http://127.0.0.1:8000/_dashboard](http://127.0.0.1:8000/_dashboard) so it doesn't need to be a strong password. The pip install's may be unnecessary as the VScode Create Environment may detect py4web and oxcam's requirements.txt files and have already taken care of this, but running them again is benign.

You should also use VScode to edit the py4web/.vscode/launch.json. This already contains a configuration to launch the localhost webserver running py4web under the vscode debugger. I recommend adding the "-L 20" argument to show web calls in the terminal window. I have also added configurations to allow for running the email daemon and daily maintenance job under vscode. You can edit the installed launch.json to replace it with the following:

```json
{   "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: py4web",
            "type": "dbugpy",
            "request": "launch",
            "program": "py4web.py",
            "args": ["run", "-L 20", "apps"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        },
        {
            "name": "Python: daily",
            "type": "dbugpy",
            "request": "launch",
            "program": "py4web.py",
            "args": [
                "call", "apps", "oxcam.daily_maintenance.daily_maintenance"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        },
        {
            "name": "Python: email",
            "type": "dbugpy",
            "request": "launch",
            "program": "py4web.py",
            "args": [
                "call", "apps", "oxcam.email_daemon.email_daemon"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        }
    ]
}
```

Finally, you need to create [settings_private.py](https://oxcamne.github.io/oxcam/install#configure-the-software-for-your-organization) in the py4web/apps/oxcam directory. If you are maintaining OxCamNE's instance you can copy the oxcamne development version from the root folder of the OxCamNE archive.

Note that if you THREAD_SUPPORT=True you should not need the Python: Email configuration. You might use the Python: daily configuration to run the task on demand.

### Start Py4web and oxcam

Go to the debugger section of Vscode and launch using the py4web configuration of the edited launch.json file. You should see something like the following in Vscode's terminal window:

```bash
(.venv) davidmanns@Davids-Air oxcam %  cd /Users/davidmanns/Library/CloudStorage/OneDr
ive-Personal/Desktop/py4web ; /usr/bin/env /Users/davidmanns/Library/CloudStorage/OneD
rive-Personal/Desktop/py4web/.venv/bin/python /Users/davidmanns/.vscode/extensions/ms-
python.python-2023.20.0/pythonFiles/lib/python/debugpy/adapter/../../debugpy/launcher 
56654 -- py4web.py run -L\ 20 apps 

 /#######  /##     /##/##   /## /##      /## /######## /####### 
| ##__  ##|  ##   /##/ ##  | ##| ##  /# | ##| ##_____/| ##__  ##
| ##  \ ## \  ## /##/| ##  | ##| ## /###| ##| ##      | ##  \ ##
| #######/  \  ####/ | ########| ##/## ## ##| #####   | ####### 
| ##____/    \  ##/  |_____  ##| ####_  ####| ##__/   | ##__  ##
| ##          | ##         | ##| ###/ \  ###| ##      | ##  \ ##
| ##          | ##         | ##| ##/   \  ##| ########| #######/
|__/          |__/         |__/|__/     \__/|________/|_______/
Is still experimental...

Py4web: 1.20231029.2 on Python 3.10.12 (main, Jun 20 2023, 19:43:52) [Clang 14.0.3 (clang-1403.0.22.14.1)]


[X] loaded _dashboard       
[X] loaded _documentation       
[X] loaded todo       
[X] loaded _default       
[X] loaded _minimal       
[X] loaded _scaffold       
[X] loaded showcase       
[X] loaded _websocket       
[X] loaded oxcam       
    output fadebook       
/Users/davidmanns/Library/CloudStorage/OneDrive-Personal/Desktop/py4web email_daemon running
[X] loaded fadebook       
Dashboard is at: http://127.0.0.1:8000/_dashboard
Ombott v1.0.0 server starting up (using <class 'py4web.server_adapters.rocketServer.<locals>.RocketServer'>(reloader=False, logging_level=20))...
Listening on http://127.0.0.1:8000/
Hit Ctrl-C to quit.
```

Now open the py4web dashboard at [http://127.0.0.1:8000/_dashboard](http://127.0.0.1:8000/_dashboard). You should see all the standard applications, plus oxcam, running. If any are flagged in red, there is a problem to investigate.

You can now run the oxcam app at [http://127.0.0.1:8000/oxcam](http://127.0.0.1:8000/oxcam). You should be asked to login by specifying your email and then taken to the db_restore tool and prompted to upload the database from a .csv file. You can download a current database backup from the production instance in Pythonanywhere, or use a backup file saved in the OxCamNE archive, or use db_oxcam_minimal.csv which is in the py4web/apps/oxcam directory.
