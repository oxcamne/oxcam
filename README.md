# oxcam

## Introduction

OxCam is a web based database app designed to support Oxford and/or Cambridge Alumni groups and Societies.
It can be deployed on low cost cloud services such as PythonAnywhere or Linode (Akamai) at a cost ~$5/month.

At it's simplest it can be used to maintain a mailing list and send out notices.

One or more paid membership categories can be implemented, either sending renewal reminders
or using autopay subscriptions, and collecting dues payments through a payment processor such as
Stripe. Members will have access to an online directory.

It can track events and provide registration capabilities including payment collection, maintaining a wait
list, etc.

By uploading transaction files (in .csv format) from banks and payment processors it can maintain
comprehensive accounts.

## Prerequisites

Python 3.8+ must be installed.
[Py4web](https://py4web.com/_documentation) must also be installed.

## License

This software is released under the [BSD-3-Clause License](https://github.com/oxcamne-secretary/oxcam/tree/main#LICENSE)
