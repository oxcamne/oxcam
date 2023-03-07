"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposed the function at URL:

	http://127.0.0.1:8000/{app_name}/{path}

If app_name == '_default' then simply

	http://127.0.0.1:8000/{path}

If path == 'index' it can be omitted:

	http://127.0.0.1:8000/

The path follows the bottlepy syntax.

@action.uses('generic.html')  indicates that the action uses the generic.html template
@action.uses(session)         indicates that the action uses the session
@action.uses(db)              indicates that the action uses the db
@action.uses(T)               indicates that the action uses the i18n & pluralization
@action.uses(auth.user)       indicates that the action requires a logged in user
@action.uses(auth)            indicates that the action requires the auth object

session, db, T, auth, and tempates are examples of Fixtures.
Warning: Fixtures MUST be declared with @action.uses({fixtures}) else your app will result in undefined behavior
"""

from py4web import action, request, abort, redirect, URL, Field, DAL
from yatl.helpers import *
from .common import db, session, T, cache, auth, logger, authenticated, unauthenticated, flash
from .settings_private import *
from .models import primary_affiliation, member_affiliations
from py4web.utils.grid import Grid, GridClassStyleBulma, Column
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import *
import datetime, random

"""
decorator for validating login & access permission using a one-time code
sent to email address.
Allows for an access level parameter associated with a user
for an explanation see the blog article from which I cribbed 
	https://www.artima.com/weblogs/viewpost.jsp?thread=240845#decorator-functions-with-decorator-arguments

"""
def checkaccess(requiredaccess):
	def wrap(f):
		def wrapped_f(*args, **kwds):
			session['prev_url'] = session.get('url')
			session['url']=request.url
			if not session.get('logged_in') == True:    #logged in
				if db(db.Members.id>0).count()==0:
					session['url']=URL('db_restore')
				redirect(URL('login'))

			#check access
			if requiredaccess != None:
				require = ACCESS_LEVELS.index(requiredaccess)
				if not session['member_id'] or not session['access']:
					if db(db.Members.id>0).count()==0:
						return f(*args, **kwds)
				have = ACCESS_LEVELS.index(session['access']) if session['access'] != None else -1
				if have < require:
					redirect(URL('accessdenied'))
			return f(*args, **kwds)
		return wrapped_f
	return wrap

@action('index')
@action.uses('message.html', db, session)
@checkaccess(None)
def index():
	message = "reached index"
	return locals()

@action('members', method=['POST', 'GET'])
@action('members/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def members(path=None):
	query = []
	left = ""
	qdesc = ""
	legend = H5('Member Records')
	errors = ''
	
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	admin = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('admin')
	if not admin:
		db.Members.Access.writable = False
	db.Members.City.requires=db.Members.State.requires=db.Members.Zip.requires=None

	form=Form([
		Field('mailing_list', 'reference Email_Lists', default=request.query.get('mailing_list'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Email_Lists', '%(Listname)s', zero="list?"))),
		Field('event', 'reference Events', default=request.query.get('event'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Events', '%(Description).20s', orderby = ~db.Events.DateTime, zero="event?")),
				comment = "exclude/select confirmed event registrants (with/without mailing list selection) "),
		Field('good_standing', 'boolean', default=request.query.get('good_standing'), 
				comment='tick to limit to members in good standing'),
		Field('field', 'string', requires=IS_EMPTY_OR(IS_IN_SET(['Affiliation', 'Email']+db.Members.fields,
					zero='search?')), default=request.query.get('field')),
		Field('value', 'string', default=request.query.get('value'))],
		keep_values=True
	)
		
	if len(form.vars) > 0:
		if form.vars.get('mailing_list'):
			query.append("(db.Emails.Member==db.Members.id)&db.Emails.Mailings.contains(form.vars.get('mailing_list'))")
			qdesc = db.Email_Lists[form.vars.get('mailing_list')].Listname+' mail list, '
		if form.vars.get('event'):
			if form.vars.get('mailing_list'):
				left="db.Reservations.on((db.Reservations.Member == db.Members.id)&\
			    	(db.Reservations.Event==form.vars.get('event'))&\
					(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&\
					(db.Reservations.Waitlist!=True))"
				query.append("(db.Reservations.id==None)")
			else:
				query.append("(db.Reservations.Member==db.Members.id)&(db.Reservations.Event==form.vars.get('event'))&\
					(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&\
					(db.Reservations.Waitlist!=True)")
			qdesc += (' excluding ' if form.vars.get('mailing_list') else '')+db.Events[form.vars.get('event')].Description[0:25]+' attendees, '
		if form.vars.get('good_standing'):
			query.append("((db.Members.Membership!=None)&(((db.Members.Paiddate==None)|(db.Members.Paiddate>=datetime.datetime.now()))\
						|(db.Members.Charged!=None)|((db.Members.Stripe_subscription!=None)&(db.Members.Stripe_subscription!=('Cancelled')))))")
			qdesc += ' in good standing, '
		if form.vars.get('value'):
			field = form.vars.get('field')
			value = form.vars.get('value')
			if not form.vars.get('field'):
				errors = 'Please specify which field to search'
			elif field == 'Affiliation':
				affiliated_members=[r.Member for r in db(db.Colleges.Name.ilike('%'+value+'%')&\
					(db.Affiliations.College==db.Colleges.id)).select(db.Affiliations.Member, orderby=db.Affiliations.Member, distinct=True)]
				query.append('db.Members.id.belongs(affiliated_members)')
				qdesc += " with affiliation matching '"+value+"'."
			elif field == 'Email':
				email_match_members=[r.Member for r in db(db.Emails.Email.ilike('%'+value+'%')).select(db.Emails.Member)]
				query.append('db.Members.id.belongs(email_match_members)')
				qdesc += " with email matching '"+value+"'."
			else:
				fieldtype = eval("db.Members."+field+'.type')
				if fieldtype != 'string':
					errors = 'search '+fieldtype+' fields not yet supported'
				else:
					query.append('db.Members.'+field+'.like("%'+value+'%")')
					qdesc += ' '+field+' contains '+value+'.'
	query = '&'.join(query)
	if query == '': query = 'db.Members.id>0'

	if errors or qdesc:
		flash.set(errors or "Filtered: "+qdesc)

	grid = Grid(path, eval(query), left=eval(left) if left else None,
	     	orderby=db.Members.Lastname|db.Members.Firstname,
			columns=[db.Members.Name, db.Members.Membership, db.Members.Paiddate,
					db.Members.Affiliations, db.Members.Access, db.Members.Notes],
			details=not write, editable=write, create=write,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
			search_form=form,
			deletable=False)
	return locals()

@action('person', method=['POST', 'GET'])
@action('person/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db)
def person(path=None):
	legend = H5('Person Records')		
	grid = Grid(path,
            formstyle=FormStyleBulma,
            grid_class_style=GridClassStyleBulma,
            query=(db.person.id > 0),
            orderby=[db.person.last],
			columns=[db.person.name, db.person.first, db.person.last])
	return locals()

@action('login', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
def login():
	form = Form([Field('email', 'string',
				requires=[IS_NOT_EMPTY(), IS_EMAIL()], default = session.get('email'))],
				formstyle=FormStyleBulma)
	legend = P("Please specify your email to login, you will receive a verification email there.")
 
	if form.accepted:
		user = db(db.users.email==form.vars['email'].lower()).select().first()
		token = str(random.randint(10000,999999))
		if user:
			id = user.id
			user.update_record(tokens= [token]+(user.tokens or []),
				when_issued = datetime.datetime.now())
		else:
			id = db.users.insert(email = form.vars['email'].lower(),
				tokens= [token],
				when_issued = datetime.datetime.now(),
				url = session['url'])
		log = 'login '+request.remote_addr+' '+form.vars['email']+' '+request.environ['HTTP_USER_AGENT']+' '+session['url']
		logger.info(log)
		message = HTML(DIV(
					A("Please click to continue to "+SOCIETY_DOMAIN, _href=URL('validate', id, token, scheme=True)),
					P("Please ignore this message if you did not request it."),
					P(DIV("If you have questions, please contact ",
	   						A(SUPPORT_EMAIL, _href='mailto:'+SUPPORT_EMAIL),
							".")),
					))
		auth.sender.send(to=form.vars['email'], subject='Confirm Email',
							body=message)
		form = None

		legend = DIV(P('Please click the link sent to your email to continue.'),
					P('This link is valid for 15 minutes.'))
	return locals()

@action('validate/<id:int>/<token:int>', method=['POST', 'GET'])
@action.uses("message.html", db, session)
def validate(id, token):
	user = db(db.users.id == id).select().first()
	if not user or not int(token) in user.tokens or datetime.datetime.now() > user.when_issued + datetime.timedelta(minutes = 15):
		redirect(URL('index'))
	session['logged_in'] = True
	session['id'] = user.id
	session['email'] = user.email
	log = 'verified '+request.remote_addr+' '+user.email
	logger.info(log)
	user.update_record(tokens=[])
	rows = db((db.Members.id == db.Emails.Member) & db.Emails.Email.ilike(user.email)).select(
				db.Members.ALL, distinct=True)
	if len(rows)<=1:
		if len(rows) == 1:
			member = rows.first()
			session['member_id'] = member.id
			session['access'] = member.Access
		else:
			session['member_id'] = 0
			session['access'] = None
		redirect(user.url)	#a new email

	tbody=TBODY()
	for member in rows:
		paid = str(member.Paiddate) if member.Paiddate else ''
		status = member.Membership or ''
		tbody.append(TR(
			TD(A('%40.40s '%(member.Name), _href=user.url)),
			TD('%9s '%(status)),
			TD(paid)))
	message = TABLE(THEAD(TR('Please select member:')),
					THEAD(TR(TH('Name'),TH('Status'),TH('Paid Date'))), tbody)
	return locals()

@action('accessdenied')
@action.uses('message.html', session)
def accessdenied():
	message = TBODY(
		DIV("You do not have permission for that, please contact ",
      		A(SUPPORT_EMAIL, _href='mailto:'+SUPPORT_EMAIL),
			" if you think this is wrong."),
		P(A('Go back', _href=session.get('prev_url'))))
	return locals()

@action('logout')
@action.uses(session)
def logout():
	session['logged_in'] = False
	redirect(URL('index'))

@action("db_restore", method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess('admin')
def db_restore():
	form = Form([Field('filespec', 'string', requires=IS_NOT_EMPTY(),
					   default='db_backup.csv')], formstyle=FormStyleBulma)
	legend = P(SOCIETY_DOMAIN+" database will be restored from this file in app base directory. Click Submit to proceed")
	
	if form.accepted:
		with open(form.vars['filespec'], 'r', encoding='utf-8', newline='') as dumpfile:
			for tablename in db.tables:	#clear out existing database
				db(db[tablename]).delete()
			db.import_from_csv_file(dumpfile, id_map={})   #, restore=True won't work in MySQL)
			flash.set("Database Restored from '"+form.vars['filespec']+"'")

	return locals()

@action("db_backup")
@action.uses("message.html", db, session)
@checkaccess('admin')
def db_backup():
	with open('db_backup.csv', 'w', encoding='utf-8', newline='') as dumpfile:
		db.export_to_csv_file(dumpfile)
	return dict(message=SOCIETY_DOMAIN+" database backed up to 'db_backup.csv' in app base directory.")

