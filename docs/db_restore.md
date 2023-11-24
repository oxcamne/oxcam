# [Oxford/Cambridge Alumni Group Database - Support Guide](support.md)

## db_restore tool

This tool allows the database to be recreated from a backup .csv file.

If using SQLite, first stop the web server, delete the py4web/apps/oxcam/databases folder and its contents, and then restart the web server. This creates a clean, but empty, database.

Browse to \<your py4web url\>/oxcam/db_restore. You will see:

![db_restore form](images/db_restore.png)

Use Browse... to locate the backup.csv file you wish to use, then click Restore.
When the database is loaded, you will need to login again.

The Overwrite checkbox can be used in a development context to reload a clean database without starting/stopping the web server or deleting the existing database; it deletes all existing database content, however all the imported records are renumbered, which will break any external links such as registration links.
