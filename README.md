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

This clones the software into a new directory apps/oxcam. You next need to create a 'settings_private.py' in apps/oxcam.
The kit just cloned contains a template 'settings_private_template.py' in the directory.
