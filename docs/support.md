# [Oxford/Cambridge Alumni Group Application - Support Guide](index.md)

This section of the guide covers installation and support and is intended for the more tech-savvy volunteer organizer charged with installing and maintaining the organization's IT infrastructure. To return to this page from elsewhere in the guide click on the title. There is also a [User Guide](index.md).

The online database is an open source [project](https://github.com/oxcamne/oxcam). Please start by reading the project README you will see there (you probably came here from there!).

 Oxcam is a [Python](https://www.python.org) App running under the open source web framework [Py4web](https://github.com/web2py/py4web). See the [contents](contents.md) page for a description of the app structure.

You need a web server belonging to the organization. OxCamNE uses PythonAnywhere and has an account there with username 'oxcamne', hence the database is reached at [https://oxcamne.pythonanywhere.com/oxcam](https://oxcamne.pythonanywhere.com/oxcam). This is a low cost and relatively straightforward option. Whatever your choice of web server, first ensure that the prerequisites described in the oxcam and py4web README files are satisfied and that you have Py4web up and running on your web server. The [Py4web documentation](https://py4web.com/_documentation) has information on installing Py4web on a variety of environments. **However, if you will be using Pythonanywhere,** please follow this [installation guide](py4web_pythonanywhere.md) to install py4web there.

See instructions on installing the oxcam app [**here**](install). If you are installing a development environment see [**here**](development_install.md).

For managing and supporting the database there are a number of tools:

- depending where your web server is hosted there will be a **web console** to handle its basic operation. In the case of PythonAnywhere, you reach this by logging in to the groups PythonAnywhere account. This is where you go to start or stop the server, to apply software updates, to examine web traffic logs, to download database backup files for archival elsewhere, etc.

- the **Py4web dashboard** will be used primarily to examine any failure tickets. It can also be used for some database administration tasks.

- there are various admin tools built into oxcam. These include [**db_restore**](db_restore.md), [**db_backup**](db_backup.md), and [**db_tool**](db_tool.md).

- a log file is maintained in **py4web/oxcam.log**. In a PythonAnywhere environment it contains only info logging which includes recording logins, together with some Stripe related messages. In other environments it may also include warning and error messages, and info from the daily_maintenance task.
