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
from py4web.utils.form import Form, FormStyleBulma
from py4web.utils.grid import Grid, GridClassStyleBulma
from yatl.helpers import XML, H5, CAT
from .settings import SOCIETY_SHORT_NAME, PAGE_BANNER, GRACE_PERIOD, SMTP_TRANS
from py4web.utils.factories import Inject
from io import StringIO, TextIOWrapper
from pydal.validators import IS_NOT_EMPTY, IS_EMAIL
from urllib.parse import urlparse, parse_qs
import re
from pathlib import Path

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER))

@action('db_tool', method=['POST', 'GET'])
@preferred
@checkaccess('admin')
def db_tool():
	access = session.access	#for layout.html
	parsed = Grid.parse(request.query)

	if not parsed.get('referrer'):
		form = Form([
			Field('query', 'string', default=request.query.get('query', ''), requires=IS_NOT_EMPTY()),
			Field('orderby', 'string', default=request.query.get('orderby', '')),
			Field('left', 'string', default=request.query.get('left', '')),
			Field('delete_all', 'boolean', default=(request.query.get('delete_all') == 'On'),
				comment='Beware, are you really sure you want to do this!'),
			Field('do_update', 'boolean', default=(request.query.get('do_update') == 'On')),
			Field('field_update', 'string', default=request.query.get('field_update', '')),
		], keep_values=True, formstyle=FormStyleBulma)

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

	qs = parse_qs(urlparse(parsed.get('referrer') or request.url).query)
	params = {k: v[0] if v else '' for k, v in qs.items()}	

	header = XML("The \"query\" is a condition like \"db.table1.field1=='value'\" \
or \"db.table.field2.like('%value%')\"<br>\
Use (...)&(...) for AND, (...)|(...) for OR, and ~(...) for NOT to build more complex queries.<br>\
Something like \"db.table1.field1==db.table2.field2\" results in a SQL JOIN. Results cannot be edited.<br>\
\"field update\" is an optional expression like \"field1='...', field2='...', ...\".<br>\
See the Py4web documentation (DAL) to learn more.")

	try:
		if params.get('do_update') or params.get('delete_all'):
			rows = db(eval(params.get('query'))).select()
			if params.get('do_update'):
				for row in rows:
					update_string = f"row.update_record({params.get('field_update')})"
					eval(update_string)
				del params['do_update']
				flash.set(f"{len(rows)} records updated")
			elif params.get('delete_all'):
				db(eval(params.get('query'))).delete()
				del params['delete_all']
				flash.set(f"{len(rows)} records deleted")
			redirect(URL('db_tool', vars=params))
		
		if params.get('query'):
			grid = Grid(eval(params.get('query')),
				orderby=eval(params.get('orderby')) if params.get('orderby') else None,
				left=eval(params.get('left')) if params.get('left') else None,
				details=False, editable=True, create=True, deletable=True,
				show_id=True, formstyle=FormStyleBulma,
				grid_class_style=GridClassStyleBulma, search_queries=[]
				)
	except Exception as e:
		flash.set(e)
	"""
	rows = db(eval(params.get('query'))).select(
				orderby=eval(params.get('orderby')) if params.get('orderby') else None,
				left=eval(params.get('left')) if params.get('left') else None)
	"""
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

@action("setup_settings_private", method=['POST', 'GET'])
@preferred
def setup_settings_private():
	if SMTP_TRANS:	#settings_private.py already set up
		redirect(URL('accessdenied'))

	access = session.access	#for layout.html
	header = CAT(
		H5("Setup settings_private.py"),
		XML(
"This file contains private settings, such as SMTP server details, payment processor keys, etc.<br>\
Minimally, you need to set up the SMTP server details to send emails. \
You can use a Gmail account, which will normally use 2-step verification, \
so you will need to create an Application Password. Search Gmail documentation for details. \
By default this will also be your support email address<br><br>\
You can later edit the settings_private.py file directly to complete your customization, \
using the editor in the py4web dashboard.<br><br>\
You can also load an initial minimal database by ticking the option. \
This will allow you to run the application, build and maintain a mailing list, and send mailings.<br>\
Alternatively, after restarting py4web, you can load a previously saved database backup using oxcam/db_restore.<br>"
		)
	)
	
	form = Form([
				Field('smtp_server', 'string', default='smtp.gmail.com',),
				Field('smtp_port', 'integer', default=587),
				Field('smtp_user', 'string', default='email_address', requires=IS_EMAIL()),
				Field('smtp_password', 'string', default='password', requires=IS_NOT_EMPTY()),
				Field('load_minimal_database', 'boolean',
		   				default=False, comment='load initial empty database')
				]
			)
	
	if form.accepted:
		try:
			this_dir = Path(__file__).parent
			template_path = this_dir / "settings_private_template.py"
			target_path = this_dir / "settings_private.py"
			with open(template_path, "r", encoding="utf-8") as f:
				content = f.read()
			# Replace the SMTP_TRANS line specifically
			smtp_line_pattern = (
				r"SMTP_TRANS\s*=\s*Email_Account\(\s*['\"]smtp_server['\"]\s*,\s*['\"]smtp_port['\"]\s*,\s*['\"]email_username['\"]\s*,\s*['\"]email_password['\"]\s*\)"
			)
			smtp_line_replacement = (
				f'SMTP_TRANS = Email_Account('
				f'"{form.vars["smtp_server"]}", '
				f'{form.vars["smtp_port"]}, '
				f'"{form.vars["smtp_user"]}", '
				f'"{form.vars["smtp_password"]}")'
			)
			content = re.sub(smtp_line_pattern, smtp_line_replacement, content)
			content = content.replace("your_support_email", form.vars["smtp_user"])
			with open(target_path, "w", encoding="utf-8") as f:
				f.write(content)
			done = "settings_private.py created/updated successfully."
			if form.vars.get('load_minimal_database'):
				# Load the minimal database
				with (this_dir / "minimal_database.csv").open("rb") as f:
					db.import_from_csv_file(
						TextIOWrapper(f, encoding='utf-8'),
						id_map={}
					)
				done += (" Minimal database loaded successfully.")
			done += (" Please restart py4web before continuing. Then visit My Account to set up your admin account.")
			flash.set(done)
		except Exception as e:
			flash.set(f"{str(e)}")

	return locals()

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
