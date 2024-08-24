"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are tools used either by database administrator
or developers. They are accessed using the URL, not via menus
"""
from py4web import action, response, redirect, Field, request
from py4web.utils.factories import Inject
from .common import db, session, flash
from .controllers import checkaccess, form_style
from py4web.utils.form import Form, FormStyleDefault
from py4web.utils.grid import Grid, GridClassStyle
from yatl.helpers import XML, H5
from .settings import SOCIETY_SHORT_NAME, PAGE_BANNER, HOME_URL, HELP_URL, GRACE_PERIOD
from py4web.utils.factories import Inject
from io import StringIO, TextIOWrapper

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL))

@action('db_tool', method=['POST', 'GET'])
@action('db_tool/<path:path>', method=['POST', 'GET'])
@preferred
@checkaccess('admin')
def db_tool(path=None):
	access = session.access	#for layout.html
	form = Form([Field('query'),
			  	Field('orderby'),
				Field('left'),
				Field('delete_all', 'boolean', comment='Beware, are you really sure you want to do this!'),
	      		Field('do_update', 'boolean'),
			    Field('field_update')],
				keep_values=True, formstyle=FormStyleDefault)
	
	header = XML("The \"query\" is a condition like \"db.table1.field1=='value'\" \
or \"db.table.field2.like('%value%')\"<br>\
Use (...)&(...) for AND, (...)|(...) for OR, and ~(...) for NOT to build more complex queries.<br>\
Something like \"db.table1.field1==db.table2.field2\" results in a SQL JOIN. Results cannot be edited.<br>\
\"field update\" is an optional expression like \"field1='...', field2='...', ...\".<br>\
See the Py4web documentation (DAL) for to learn more.")

	if not path:
		session['query2'] = None
		session['orderby2'] = None
		session['left2'] = None

	try:
		if form.accepted:
			session['query2'] = form.vars.get('query')
			session['orderby2'] = form.vars.get('orderby')
			session['left2'] = form.vars.get('left')
			rows = db(eval(form.vars.get('query'))).select()
			if form.vars.get('do_update'):
				for row in rows:
					update_string = f"row.update_record({form.vars.get('field_update')})"
					eval(update_string)
				form.vars['do_update']=False
				flash.set(f"{len(rows)} records updated")
			elif form.vars.get('delete_all'):
				db(eval(form.vars.get('query'))).delete()
				flash.set(f"{len(rows)} records deleted")
			form.vars['do_update'] = False
			form.vars['delete_all'] = False
		
		form.vars['query'] = session.get('query2')
		form.vars['orderby'] = session.get('orderby2')
		form.vars['left'] = session.get('left2')
		if form.vars.get('query'):
			grid = Grid(path, eval(form.vars.get('query')),
			   		orderby=eval(form.vars.get('orderby')) if form.vars.get('orderby') else None,
			   		left=eval(form.vars.get('left')) if form.vars.get('left') else None,
					details=False, editable=True, create=True, deletable=True,
					show_id=True,
					)
	except Exception as e:
		flash.set(e)
	return locals()

@action("db_restore", method=['POST', 'GET'])
@preferred
@checkaccess('admin')
def db_restore():
	access = session.access	#for layout.html
	header = f"Restore {SOCIETY_SHORT_NAME} database from backup file"
	
	form = Form([Field('overwrite_existing_database', 'boolean',
	       				default=False, comment='clear if new empty database'),
				Field('backup_file', 'upload', uploadfield = False)],
				submit_value = 'Restore')
	
	if form.accepted:
		try:
			with TextIOWrapper(form.vars.get('backup_file').file, encoding='utf-8') as backup_file:
				if form.vars.get('overwrite_existing_database'):
					for tablename in db.tables:	#clear out existing database
						db(db[tablename]).delete()
				db.import_from_csv_file(backup_file, id_map={} if form.vars.get('overwrite_existing_database') else None)   #, restore=True won't work in MySQL)
				flash.set(f"{SOCIETY_SHORT_NAME} Database Restored from {form.vars.get('backup_file').raw_filename}")
				session['logged_in'] = False
				redirect('index')
		except Exception as e:
			flash.set(f"{str(e)}")

	return locals( )

@action("db_backup")
@action.uses("download.html", db, session, Inject(response=response))
@checkaccess('admin')
def db_backup():
	access = session.access	#for layout.html
	stream = StringIO()
	content_type = "text/csv"
	filename = f'{SOCIETY_SHORT_NAME}_db_backup.csv'
	db.export_to_csv_file(stream)
	return locals()
