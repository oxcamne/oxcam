# oxcam

## Introduction

OxCam is for Oxford and/or Cambridge Alumni groups and Societies and provides a simple but comprehensive solution for maintaining a web site and managing the various operations common to such groups.

It can be deployed on low cost cloud services such as PythonAnywhere or Linode (Akamai) at very low cost.

- It can implement a public facing web site, with pages created using a combination of Markdown and HTML, or it can work in combination with an external web site. In the latter case, it can serve dynamic content for embedding in the external site (examples would be a calendar of future events, a listing of past events)
- At it's simplest it can simply be used to maintain mailing lists and send out notices.
- It can track events and provide registration capabilities including payment collection, maintaining a wait
list, etc.
- One or more paid membership categories can be implemented, either sending renewal reminders or using autopay subscriptions, and collecting dues payments through a payment processor such as Stripe. Members are provided access to an online directory.
- By uploading transaction files (in .csv format) from banks and payment processors oxcam it can maintain comprehensive accounts.

A group can choose how much of the above to implement and can expand it's use over time.

The project includes an online [User Guide](https://oxcamne.github.io/oxcam).

For questions, bug reports, feature requests etc. use the Issues forum (to post you need to register on github).

## Prerequisites

OxCam is a [Python](https://www.python.org) App running under the open source web framework [Py4web](https://github.com/web2py/py4web).

OxCam is a web app and these requirements apply to your chosen web server environment:

- Python 3.8+ must be installed. The app has been developed and is currently running on Python 3.10.
- [Py4web](https://py4web.com/_documentation) must also be installed. Please see the [Py4web documentation](https://py4web.com/_documentation) for information on it's installation. There is information on installing Py4web on a variety of environments. If you are installing Py4web on PythonAnywhere, please see [https://oxcamne.github.io/oxcam/py4web_pythonanywhere](https://oxcamne.github.io/oxcam/py4web_pythonanywhere).
- You will need to use the Py4web Dashboard for certain operations, so will need to use that password, which is set during Py4web installation.
- git must be installed; you will use it in a terminal session to clone this software from the github repositary, and to pull future updates of OxCam.

## License

This software is released under the [BSD-3-Clause License](LICENSE)

## Installation

For support information including installation, please see [https://oxcamne.github.io/oxcam/support](https://oxcamne.github.io/oxcam/support).

## Contributors and Collaborators

The software was developed by David Manns for use in running the Oxford & Cambridge Society of New England. It is Oxford & Cambridge centric in that it is designed for matriculated alumni, who must provide their Oxbridge College and matriculation list in order to subscribe to mailing lists, register for events, etc.

For support, questions, or if you wish to collaborate on improving the software please contact <secretary@oxcamne.org>.
