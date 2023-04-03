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
from .models import primary_email, res_tbc
from py4web.utils.grid import Grid, GridClassStyleBulma, Column
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import *
import datetime, random, re, markmin

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

def getmeta(name):
	m = db(db.Metadata.Name==name).select().first()
	return m.Code if m else None

@action('index')
@action.uses('message.html', db, session, flash)
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
	left = None
	qdesc = ""
	errors = ''
	legend = H5('Member Records')
	db.Members.Name.readable = False
	db.Members.Affiliations.readable = False

	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	admin = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('admin')
	if not admin:
		db.Members.Access.writable = False
	db.Members.City.requires=db.Members.State.requires=db.Members.Zip.requires=None

	search_form=Form([
		Field('mailing_list', 'reference Email_Lists', 
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Email_Lists', '%(Listname)s', zero="list?"))),
		Field('event', 'reference Events', 
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Events', '%(Description).20s', orderby = ~db.Events.DateTime, zero="event?")),
				comment = "exclude/select confirmed event registrants (with/without mailing list selection) "),
		Field('good_standing', 'boolean', comment='tick to limit to members in good standing'),
		Field('field', 'string', requires=IS_EMPTY_OR(IS_IN_SET(['Affiliation', 'Email']+db.Members.fields,
					zero='search?'))),
		Field('value', 'string')],
		keep_values=True, formstyle=FormStyleBulma
	)

	if len(search_form.vars) == 0:
		search_form.vars = request.query
	backvars=dict(mailing_list=search_form.vars.get('mailing_list'),
						event=search_form.vars.get('event'),
						field=search_form.vars.get('field'),
						value=search_form.vars.get('value'))
	if search_form.vars.get('good_standing'):
		backvars['good_standing'] = 'On'
	back = URL('members/select', scheme=True, vars=backvars)
	
	if path=='select':
		legend = CAT(legend, A("Send Email to Specific Address(es)", _href=URL('composemail', vars=dict(back=back))))
		db.Members.Name.readable = True
		db.Members.Affiliations.readable = True
		session['search_form_vars'] = backvars
	elif path and path.startswith('edit'):
		legend = CAT(legend,
	       			P(A('back', _href=URL('members/select', scheme=True, vars=session.get('search_form_vars')))))

	if search_form.vars.get('mailing_list'):
		query.append(f"(db.Emails.Member==db.Members.id)&db.Emails.Mailings.contains({search_form.vars.get('mailing_list')})")
		qdesc = f"{db.Email_Lists[search_form.vars.get('mailing_list')].Listname} mail list, "
	if search_form.vars.get('event'):
		if search_form.vars.get('mailing_list'):
			left=f"db.Reservations.on((db.Reservations.Member == db.Members.id)&(db.Reservations.Event=={search_form.vars.get('event')})&(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&(db.Reservations.Waitlist!=True))"
			query.append("(db.Reservations.id==None)")
		else:
			query.append(f"(db.Reservations.Member==db.Members.id)&(db.Reservations.Event=={search_form.vars.get('event')})&(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&(db.Reservations.Waitlist!=True)")
		qdesc += f"{'excluding ' if search_form.vars.get('mailing_list') else ''}{db.Events[search_form.vars.get('event')].Description[0:25]} attendees, "
	if search_form.vars.get('good_standing'):
		query.append("((db.Members.Membership!=None)&(((db.Members.Paiddate==None)|(db.Members.Paiddate>=datetime.datetime.now()))|(db.Members.Charged!=None)|((db.Members.Stripe_subscription!=None)&(db.Members.Stripe_subscription!=('Cancelled')))))")
		qdesc += ' in good standing, '
	if search_form.vars.get('value'):
		field = search_form.vars.get('field')
		value = search_form.vars.get('value')
		if not search_form.vars.get('field'):
			errors = 'Please specify which field to search'
		elif field == 'Affiliation':
			query.append(f"db.Colleges.Name.ilike('%{value}%')&(db.Affiliations.College==db.Colleges.id)&(db.Members.id==db.Affiliations.Member)")
			qdesc += f" with affiliation matching '{value}'."
		elif field == 'Email':
			query.append(f"db.Emails.Email.ilike('%{value}%')&(db.Emails.Member==db.Members.id)")
			qdesc += f" with email matching '{value}'."
		else:
			fieldtype = eval("db.Members."+field+'.type')
			m = re.match(r"^([<>]?=?)\s*(.*)$", value, flags=re.DOTALL)
			operator = m.group(1)
			value = m.group(2)
			if fieldtype == 'string' or fieldtype == 'text':
				if not operator:
					query.append(f'db.Members.{field}.like("%{value}%")')
					qdesc += f' {field} contains {value}.'
				elif operator == '=':
					query.append(f'db.Members.{field}.like("{value}")')
					qdesc += f' {field} equals {value}.'
				else:
					query.append(f"(db.Members.{field}{operator}{value})")
					qdesc += f' {field} {operator} {value}.'
			elif fieldtype == 'date' or fieldtype == 'datetime':
				try:
					date = datetime.datetime.strptime(value, '%m/%d/%Y').date()
				except:
					errors = 'please use mm/dd/yyyy format for dates'
				if not errors:
					if not operator or operator == '=':
						operator = '=='
					query.append(f"(db.Members.{field}{operator}'{date.strftime('%Y-%m-%d')}')")
					qdesc += f' {field} {operator} {value}.'
			elif fieldtype == 'boolean':
				if value != 'T' and value != 'F':
					errors = 'please use T or F for boolean field'
				else:
					query.append(f'(db.Members.{field}=={value}')
					qdesc += f' {field} {value}'
			elif fieldtype.startswith('decimal'):
				if not value.isdigit():
					errors = 'please use only digits'
				else:
					query.append(f'(db.Members.{field}{operator}{value})')
					qdesc += f' {field} {operator} {value}.'
			else:
				errors = f'search {fieldtype} fields not yet implemented'
	query = '&'.join(query)
	if query == '':
		query = 'db.Members.id>0'

	if errors:
		flash.set(errors)
	
	if qdesc and path=='select':
		legend = CAT(legend,
				P(A("Send Notice to "+qdesc, _href=URL('composemail',
					vars=dict(query=query, left=left or '', qdesc=qdesc, back=back)))))

	grid = Grid(path, eval(query), left=eval(left) if left else None,
	     	orderby=db.Members.Lastname|db.Members.Firstname,
			columns=[db.Members.Name, db.Members.Membership, db.Members.Paiddate,
					db.Members.Affiliations, db.Members.Access, db.Members.Notes],
			details=not write, editable=write, create=write,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
			search_form=search_form,
			deletable=False)
	return locals()

def emailparse(body, subject, query):
#this function validates and expands boilerplate <...> elements except the ones left til the last minute	
	m = re.match(r"^(.*)(\{\{.*\}\})(.*)$", body, flags=re.DOTALL)
	if m:			#don't unpack included html content
		return emailparse(m.group(1), subject, query)+[(m.group(2), None)]+emailparse(m.group(3), subject, query)

	m = re.match(r"^(.*)<(.*)>(.*)$", body, flags=re.DOTALL)
	if m:			#found something to expand
		text = func = None
		if m.group(2)=='subject':
			text = subject
		elif m.group(2)=='greeting' or m.group(2)=='email' or m.group(2)=='member' or m.group(2)=='reservation':
			if not query or m.group(2)=='reservation' and not ('Reservations.Member' in query):
				raise Exception(f"<{m.group(2)}> can't be used in this context")
			func=m.group(2)
		else:	#metadata?
			text = getmeta(m.group(2)).replace('<subject>', subject)
			if not text:
				raise Exception(f"<{m.group(2)}>  is not in metadata")
		return emailparse(m.group(1), subject, query)+[(text, func)]+emailparse(m.group(3), subject, query)
	return [(body, None)]
	
#display member profile
def member_profile(member):
	body = '------------------------\n'
	body += '**Name:**|' + f"{member.Lastname}, {member.Title or ''} {member.Firstname} {member.Suffix or ''}" + '\n'
	affiliations = db(db.Affiliations.Member == member.id).select(orderby = db.Affiliations.Modified)
	body += '**Affiliations:**'
	for aff in affiliations:
		body += '|' + aff.College.Name + ' ' + str(aff.Matr or '') + '\n'
	body += '\n**Address line 1:**|' + (member.Address1 or '') + '\n'
	body += '**Address line 2:**|' + (member.Address2 or '') + '\n'
	body += '**Town/City:**|' + (member.City or '') + '\n'
	body += '**State:**|' + (member.State or '') + '\n'
	body += '**Zip:**|' + (member.Zip or '') + '\n'
	body += '**Home phone:**|' + (member.Homephone or '') + '\n'
	body += '**Work phone:**|' + (member.Workphone or '') + '\n'
	body += '**Mobile:**|' + (member.Cellphone or '') + ' (not in directory)\n'
	body += '**Email:**|' + (primary_email(member.id) or '') + (' (not in directory)\n' if member.Privacy==True else '\n')
	body += '------------------------\n\n'
	return body
	
#create confirmation of event
def evtconfirm(event_id, member_id, justpaid=0):
	event = db.Events[event_id]
	resvtns = db((db.Reservations.Event==event_id)&(db.Reservations.Member==member_id)).select(
					orderby=~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname)
	if not resvtns: return ''
	tbc = res_tbc(member_id, event_id) or 0
	tbcdues = res_tbc(member_id, event_id, True) or 0
	body = '------------------------\n'
	body += '**Event:**|' + (event.Description or '') + '\n'
	body += '**Venue:**|' + (event.Venue or '') + '\n'
	body += '**Date:**|' + event.DateTime.strftime("%A %B %d, %Y") + '\n'
	body += '**Time:**|' + event.DateTime.strftime("%I:%M%p") + '\n'
	body += '------------------------\n'
	body += '------------------------\n'
	body += '**Name**|**Affiliation**|**Selection**|**Ticket Cost**\n'
	for t in resvtns:
		body += '%s, %s %s %s|'%(t.Lastname, t.Title or '', t.Firstname, t.Suffix or '')
		body += (t.Affiliation.Name if t.Affiliation else '') +'|'
		body += (t.Selection or '') + '|'
		body += '$%6.2f'%(t.Unitcost or 0.00) + '|'
		if t.Waitlist:
			body += '%s\n'%('``**waitlisted**``:red')
		elif t.Provisional:
			body += '%s\n'%('``**unconfirmed**``:red')
		else:
			body += '\n'
	if tbcdues > tbc:
		body += 'Membership Dues|||$%6.2f\n'%(tbcdues - tbc)
	body += '**Total cost**|||**$%6.2f**\n'%((resvtns.first().Totalcost or 0) + tbcdues - tbc)
	body += '**Paid**|||**$%6.2f**\n'%((resvtns.first().Paid or 0)+(resvtns.first().Charged or 0)+justpaid)
	if tbcdues>justpaid:
		body += '**Net amount due**|||**$%6.2f**\n'%(tbcdues-justpaid)
	body += '------------------------\n'
	if (tbcdues)>justpaid:
		body += 'To pay online please visit '+URL('member', 'registration', args=[event.id], scheme=True, host=getmeta('Subdomain'))
	elif event.Notes and not resvtns[0].Waitlist and not resvtns[0].Provisional:
		body += '\n\n%s\n'%event.Notes
	return body

@action('composemail', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess('write')
def composemail():
	query = request.query.get('query')
	qdesc = request.query.get('qdesc')
	left = request.query.get('left')

	legend = CAT(H5("Send Email"),
	      		P(A('back', _href=request.query.get('back'))))
	footer=DIV("You can use <subject>, <greeting>, <member>, <reservation>, <email>, or <metadata> ",
				"where metadata is 'Letterhead', 'Membership Secretary' or ", "'Reservations', etc.  ",
				"You can also include html content thus: {{content}}. Email is formatted using ",
					A("Markmin", _href='http://www.web2py.com/examples/static/markmin.html', _target="Markmin"),
					".")
	source = [row['Email'] for row in db((db.Emails.Member == session['member_id']) & \
	   (db.Emails.Email.contains(SOCIETY_DOMAIN.lower()))).select(
			db.Emails.Email, orderby=~db.Emails.Modified)]
	if len(source) == 0:
		flash.set('Sorry, you cannot send email without a Society email address')
		redirect(URL('accessdenied'))
	
	form = Form(
		[Field('template', 'reference EMProtos',
			requires=IS_IN_DB(db, 'EMProtos.id','%(Subject)s', orderby=~db.EMProtos.Modified),
			comment='Optional: select an existing mail template')],
			submit_value='Use Template', formstyle=FormStyleBulma,
			form_name="template_form")
	if form.accepted:
		request.query['proto'] = form.vars.get('template')
		redirect(URL('composemail', vars=request.query))

	proto = db(db.EMProtos.id == request.query.get('proto')).select().first()
	fields =[Field('sender', 'string', requires=IS_IN_SET(source), default=source[0])]
	if query:
		legend = CAT(legend, P(f'To: {qdesc}'))
	else:
		fields.append(Field('to', 'string',
			comment='Include spaces between multiple recipients',
   			requires=[IS_NOT_EMPTY(), IS_LIST_OF_EMAILS()]))
	fields.append(Field('bcc', 'string', requires=IS_LIST_OF_EMAILS(), default=''))
	fields.append(Field('subject', 'string', requires=IS_NOT_EMPTY(), default=proto.Subject if proto else ''))
	fields.append(Field('body', 'text', requires=IS_NOT_EMPTY(), default=proto.Body if proto else \
				"<Letterhead>\n<greeting>\n\n" if query else "<Letterhead>\n\n"))
	fields.append(Field('save', 'boolean', default=proto!=None, comment='store/update template'))
	if proto:
		form=None
		fields.append(Field('delete', 'boolean', comment='tick to delete template; sends no message'))
	form2 = Form(fields, form_name="message_form", keep_values=True,
					submit_value = 'Send', formstyle=FormStyleBulma)
			
	if form2.accepted:
		if proto:
			if form2.vars['delete']:
				db(db.EMProtos.id == proto.id).delete()
				flash.set("Template deleted: "+ proto.Subject)
				redirect(request.query.get('back'))
			if form2.vars['save']:
				proto.update_record(Subject=form2.vars['subject'],
					Body=form2.vars['body'], Modified=datetime.datetime.now())
				flash.set("Template updatelend: "+ form2.vars['subject'])
		else:
			if form2.vars['save']:
				db.EMProtos.insert(Subject=form2.vars['subject'], Body=form2.vars['body'])
				flash.set("Template stored: "+ form2.vars['subject'])

		bcc = re.compile('[^,;\s]+').findall(form2.vars['bcc'])
		try:
			bodyparts = emailparse(form2.vars['body'], form2.vars['subject'], query)
		except Exception as e:
			flash.set(e)
			bodyparts = None
		if bodyparts:
			if query:
				select_fields = [db.Members.id]
				if 'Reservations.Member' in query:	#refers to Reservation
					select_fields.append(db.Reservations.Event)
				if 'Mailings.contains'in query:		#using a mailing list
					select_fields.append(db.Emails.Email)
					unsubscribe = URL('member',  'mail_lists', scheme=True)
					bodyparts.append((f"\n\n''This message addressed to {qdesc} [[unsubscribe {unsubscribe}]]''", None))
				bodyparts.append((f"\n\n''{getmeta('Visit Website Instructions')}''", None))
				rows = db(eval(query)).select(*select_fields, left=eval(left) if left!='' else None, distinct=True)
				for row in rows:
					body = ''
					member = db.Members[row.get(db.Members.id)]
					to = row.get(db.Emails.Email) or primary_email(member.id)
					if not to:
						continue
					for part in bodyparts:
						if part[0]:
							body += part[0]
						elif part[1] == 'greeting':
							if member.Title:
								title = member.Title[4:] if member.Title.startswith('The ') else member.Title
								name = member.Firstname if title.find("Sir") >= 0 else member.Lastname
								body += 'Dear ' + title + ' ' + name + ',\n\n'
							else:
								body += 'Dear ' + member.Firstname.partition(' ')[0] + ',\n\n'
						elif part[1] == 'email':
							body += to
						elif part[1] == 'member':
							body += member_profile(member)
						elif part[1] == 'reservation':
							body += evtconfirm(row.get(db.Reservations.Event), member.id)
					message = HTML(XML(markmin.markmin2html(body)))
					auth.sender.send(to=to, subject=form2.vars['subject'], bcc=bcc, body=message)
				flash.set(f"{len(rows)} emails sent to {qdesc}")
			else:
				to = re.compile('[^,;\s]+').findall(form2.vars['to'])
				body = ''
				for part in bodyparts:
					body += part[0]		
				flash.set(f"Email sent to: {to}")
				message = HTML(XML(markmin.markmin2html(body)))
				auth.sender.send(to=to, subject=form2.vars['subject'], bcc=bcc, body=message)
			redirect(request.query.get('back'))
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
@action.uses('message.html', session, flash)
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

