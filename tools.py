"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are tools used either by database administrator
or developers. They are accessed using the URL, not via menus
"""
from py4web import action, response, redirect, Field
from py4web.utils.factories import Inject
from .common import db, session, flash
from .controllers import checkaccess, form_style
from py4web.utils.form import Form, FormStyleDefault
from py4web.utils.grid import Grid, GridClassStyle
from .settings import SOCIETY_DOMAIN
import io
from io import StringIO

@action('db_tool', method=['POST', 'GET'])
@action('db_tool/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('admin')
def db_tool(path=None):
	access = session['access']	#for layout.html
	form = Form([Field('query'),
	      		Field('do_update', 'boolean'),
			    Field('field_update')],
				keep_values=True, formstyle=FormStyleDefault)
	
	header = "The \"query\" is a condition like \"db.table1.field1=='value'\". Something like \"db.table1.field1==db.table2.field2\" results in a SQL JOIN.\
Use (...)&(...) for AND, (...)|(...) for OR, and ~(...) for NOT to build more complex queries.\
\"field_update\" is an optional expression like \"field1='newvalue'\". You cannot update the results of a JOIN"
	if not path:
		session['query'] = None

	try:
		if form.accepted:
			session['query'] = query=form.vars.get('query')
			rows = db(eval(form.vars.get('query'))).select()
			if form.vars.get('do_update'):
				for row in rows:
					update_string = f"row.update_record({form.vars.get('field_update')})"
					eval(update_string)
				form.vars['do_update']=False
				flash.set(f"{len(rows)} records updated, click Submit to see results")

		form.vars['query'] = query = session.get('query')
		if query:
			grid = Grid(path, eval(form.vars.get('query')),
					details=False, editable=True, create=True, deletable=True,
					grid_class_style=GridClassStyle, formstyle=form_style, show_id=True,
					)
	except Exception as e:
		flash.set(e)
	return locals()

@action("db_restore", method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('admin')
def db_restore():
	access = session['access']	#for layout.html
	header = f"Restore {SOCIETY_DOMAIN} database from backup file"
	
	form = Form([Field('overwrite_existing_database', 'boolean',
	       				default=True, comment='clear if new empty database'),
				Field('backup_file', 'upload', uploadfield = False)],
				submit_value = 'Restore')
	
	if form.accepted:
		try:
			with io.TextIOWrapper(form.vars.get('backup_file').file, encoding='utf-8') as backup_file:
				if form.vars.get('overwrite_existing_database'):
					for tablename in db.tables:	#clear out existing database
						db(db[tablename]).delete()
				db.import_from_csv_file(backup_file, id_map={} if form.vars.get('overwrite_existing_database') else None)   #, restore=True won't work in MySQL)
				flash.set(f"{SOCIETY_DOMAIN} Database Restored from {form.vars.get('backup_file').raw_filename}")
				redirect('login')
		except Exception as e:
			flash.set(f"{str(e)}")

	return locals( )

@action("db_backup")
@action.uses("download.html", db, session, Inject(response=response))
@checkaccess('admin')
def db_backup():
	access = session['access']	#for layout.html
	stream = StringIO()
	content_type = "text/csv"
	filename = f'{SOCIETY_DOMAIN}_db_backup.csv'
	db.export_to_csv_file(stream)
	return locals()

