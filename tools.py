"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

The actions in this file are tools used either by database administrator
or developers. They are accessed using the URL, not via menus
"""
from py4web import action, response, redirect, Field, request, URL
from py4web.utils.factories import Inject
from .common import db, session, flash
from .session import checkaccess
from py4web.utils.form import Form, FormStyleDefault
from py4web.utils.grid import Grid, GridClassStyle
from yatl.helpers import XML, H5
from .settings import SOCIETY_SHORT_NAME, PAGE_BANNER, GRACE_PERIOD
from py4web.utils.factories import Inject
from io import StringIO, TextIOWrapper
from pydal.validators import IS_NOT_EMPTY

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER))

@action('db_tool', method=['POST', 'GET'])
@preferred
@checkaccess('admin')
def db_tool():
	access = session.access	#for layout.html
	parsed = Grid.parse(request.query)

	def validate_query(form):
		"""
		Validate the query field to ensure it is not empty and is a valid expression.
		This is a simple validation; you may want to enhance it based on your requirements.
		"""
		query = form.vars.get('query', '')
		if query:
			try:
				db(eval(query)).select(orderby=eval(form.vars.get('orderby', '')) if form.vars.get('orderby') else None,
					left=eval(form.vars.get('left', '')) if form.vars.get('left') else None)
						# This will raise an error if the query, orderby, left are invalid
			except Exception as e:
				form.errors['query'] = f'Invalid query: {str(e)}'
		if form.vars.get('do_update') and not form.vars.get('field_update'):
			form.errors['field_update'] = 'You must specify fields to update.'
		return form.errors
	
	form = Form([
		Field('query', 'string', default=request.query.get('query', ''), requires=IS_NOT_EMPTY()),
		Field('orderby', 'string', default=request.query.get('orderby', '')),
		Field('left', 'string', default=request.query.get('left', '')),
		Field('delete_all', 'boolean', default=(request.query.get('delete_all') == 'On'),
			comment='Beware, are you really sure you want to do this!'),
		Field('do_update', 'boolean', default=(request.query.get('do_update') == 'On')),
		Field('field_update', 'string', default=request.query.get('field_update', '')),
	], keep_values=True, formstyle=FormStyleDefault, validation=validate_query)

	if form.accepted:
		url = URL('db_tool', vars=dict(
			query=form.vars.get('query', ''),
			orderby=form.vars.get('orderby', ''),
			left=form.vars.get('left', ''),
			delete_all='On' if form.vars.get('delete_all') else '',
			do_update='On' if form.vars.get('do_update') else '',
			field_update=form.vars.get('field_update', '')
		))
		redirect(url)
	
	header = XML("The \"query\" is a condition like \"db.table1.field1=='value'\" \
or \"db.table.field2.like('%value%')\"<br>\
Use (...)&(...) for AND, (...)|(...) for OR, and ~(...) for NOT to build more complex queries.<br>\
Something like \"db.table1.field1==db.table2.field2\" results in a SQL JOIN. Results cannot be edited.<br>\
\"field update\" is an optional expression like \"field1='...', field2='...', ...\".<br>\
See the Py4web documentation (DAL) for to learn more.")

	if request.query.get('query'):
		grid = Grid(eval(request.query.get('query')),
				orderby=eval(request.query.get('orderby')) if request.query.get('orderby') else None,
				left=eval(request.query.get('left')) if request.query.get('left') else None,
				details=False, editable=True, create=True, deletable=True,
				show_id=True, search_queries=[],
				)
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
				redirect('my_account')
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
