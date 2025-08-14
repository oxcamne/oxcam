# oxcam

## Introduction

OxCam is for Oxford and/or Cambridge Alumni groups and Societies and provides a simple but comprehensive solution for maintaining a web site and managing the various operations common to such groups.

It can be deployed on low cost cloud services such as PythonAnywhere or Linode (Akamai) at very low cost.

- It can provide a public facing web site, with pages created using a combination of Markdown and HTML, or it can work in combination with an external web site. In the latter case, it can serve dynamic content for embedding in the external site (examples would be a calendar of future events, a listing of past events)
- At it's simplest it can simply be used to maintain mailing lists and send out notices.
- It can support events and provide registration capabilities including payment collection, maintaining a wait
list, etc.
- One or more paid membership categories can be implemented, either sending renewal reminders or using autopay subscriptions, and collecting dues payments through a payment processor such as Stripe. Members are provided access to an online directory.
- By uploading transaction files (in .csv format) from banks and payment processors oxcam it can maintain comprehensive accounts.

A group can choose how much of the above to implement and can expand it's use over time.

The project includes an online [User Guide](https://oxcamne.github.io/oxcam).

For questions, bug reports, feature requests etc. use the Issues forum (to post you need to register on github).

## Prerequisites

OxCam is a [Python](https://www.python.org) App running under the open source web framework [Py4web](https://github.com/web2py/py4web). It serves a website containing an embedded database holding the groups data. You will need:

- A web server. Most likely you will be using a service such as Pythonanywhere or Linnode (Alamai), but you could use your own hardware, such as a Linux server.
- Python 3.8+ must be installed on the server. The app has been developed and is currently running on Python 3.10.
- [Py4web](https://py4web.com/_documentation) must be installed on the server. Please see the [Py4web documentation](https://py4web.com/_documentation/static/en/chapter-03.html) for information on installing on various environments. If using PythonAnywhere to host OxCam, please see [https://oxcamne.github.io/oxcam/py4web_pythonanywhere](https://oxcamne.github.io/oxcam/py4web_pythonanywhere).

## License

This software is released under the [BSD-3-Clause License](LICENSE)

## Installation

For support information including installation, please see [https://oxcamne.github.io/oxcam/support](https://oxcamne.github.io/oxcam/support).

## Contributors and Collaborators

The software was developed by David Manns for use in running the Oxford & Cambridge Society of New England. It is Oxford & Cambridge centric in that it is designed for matriculated alumni, who must provide their Oxbridge College and matriculation list in order to subscribe to mailing lists, register for events, etc.

For support, questions, or if you wish to collaborate on improving the software please contact <secretary@oxcamne.org>.
