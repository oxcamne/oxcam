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
from py4web import action, request, response, redirect, URL, Field
from yatl.helpers import H5, H6, XML, HTML, TABLE, TH, TD, THEAD, TR
from .common import db, session, auth, flash
from .settings import SOCIETY_DOMAIN, STRIPE_PKEY, STRIPE_SKEY, LETTERHEAD,\
	SUPPORT_EMAIL, GRACE_PERIOD, SOCIETY_NAME, MEMBERSHIP, STRIPE_EVENT,\
	MEMBER_CATEGORIES, MAIL_LISTS, STRIPE_FULL, STRIPE_STUDENT, TIME_ZONE,\
	UPLOAD_FOLDER
from .models import ACCESS_LEVELS, CAT, A, event_attend, event_wait, member_name,\
	member_affiliations, member_emails, primary_affiliation, primary_email,\
	primary_matriculation, dues_type, event_revenue, event_unpaid, res_tbc, res_status,\
	res_conf, res_totalcost, res_wait, res_prov, bank_accrual
from pydal.validators import IS_LIST_OF_EMAILS, IS_EMPTY_OR, IS_IN_DB, IS_IN_SET,\
	IS_NOT_EMPTY, IS_DATE, IS_DECIMAL_IN_RANGE, IS_INT_IN_RANGE
from .utilities import member_good_standing, ageband, update_Stripe_email, newpaiddate,\
	collegelist, tdnum, get_banks, financial_content, event_confirm, msg_header, msg_send,\
	society_emails, emailparse, notification, notify_support, member_profile
from .session import checkaccess
from py4web.utils.grid import Grid, GridClassStyleBulma, Column
from py4web.utils.form import Form, FormStyleBulma
from py4web.utils.factories import Inject
import datetime, re, markmin, stripe, csv, decimal, io
from io import StringIO
from py4web.utils.mailer import Mailer

grid_style = GridClassStyleBulma
form_style = FormStyleBulma

@action('index')
@action.uses('message.html', db, session, flash)
@checkaccess(None)
def index():
	message = H6("Please select one of the following:")
	member = db.Members[session['member_id']] if session.get('member_id') else None
	access = session['access']	#for layout.html

	if not member or not member_good_standing(member):
		message = CAT(message, A("Join or Renew your Membership", _href=URL('registration')), XML('<br>'))
	else:
		message = CAT(message, A("Update your member profile or contact information", _href=URL('registration')), XML('<br>'))

	if member:
		message = CAT(message, A("Update your email address and/or mailing list subscriptions", _href=URL(f"emails/Y/{session.get('member_id')}")), XML('<br>'))
	else:
		message = CAT(message, A("Join our mailing list(s)", _href=URL("registration", vars=dict(mail_lists='Y'))), XML('<br>'))

	if member and member.Stripe_subscription!='Cancelled' and member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)-datetime.timedelta(days=45)).date()):
		if member.Stripe_subscription:
			message = CAT(message, A("View membership subscription/Update credit card", _href=URL('update_card')), XML('<br>'))
		message = CAT(message, A("Cancel your membership", _href=URL('cancel_subscription')), XML('<br>'))

	message = CAT(message, XML('<br>'),
	       H6(XML(f"To register for events use links below or visit {A(f'www.{SOCIETY_DOMAIN}.org', _href=f'https://www.{SOCIETY_DOMAIN}.org')}:")),
	       XML('<br>'))
	events = db(db.Events.DateTime>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)).select(orderby = db.Events.DateTime)
	events = events.find(lambda e: e.Booking_Closed>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) or event_attend(e.id))
	for event in events:
		waitlist = ''
		if event.Booking_Closed < datetime.datetime.now(TIME_ZONE).replace(tzinfo=None):
			waitlist = ' *Booking Closed, waitlisting*'
		elif event_wait(event.id) or (event.Capacity and (event_attend(event.id) or 0) >= event.Capacity):
			waitlist = ' *Sold Out, waitlisting*'
		pass
		message = CAT(message, event.DateTime.strftime('%A, %B %d '), 
			A(f"{event.Description}", _href=URL(f'registration/{event.id}')), waitlist, XML('<br>'))
	return locals()

@action('members', method=['POST', 'GET'])
@action('members/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def members(path=None):
	access = session['access']	#for layout.html
	query = []
	left = None #only used if mailing list with excluded event attendees
	qdesc = ""
	errors = ''
	header = H5('Member Records')
	back = URL('members/select', scheme=True)

	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	admin = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('admin')
	if not admin:
		db.Members.Access.writable = False
	db.Members.City.requires=db.Members.State.requires=db.Members.Zip.requires=None
	db.Members.Created.default = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)

	search_form=Form([
		Field('mailing_list', 'reference Email_Lists', 
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Email_Lists', '%(Listname)s', zero="mailing?"))),
		Field('event', 'reference Events', 
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Events', '%(Description).20s', orderby = ~db.Events.DateTime, zero="event?")),
				comment = "exclude/select confirmed event registrants (with/without mailing list selection) "),
		Field('good_standing', 'boolean', comment='tick to limit to members in good standing'),
		Field('field', 'string', requires=IS_EMPTY_OR(IS_IN_SET(['Affiliation', 'Email']+db.Members.fields,
					zero='field?'))),
		Field('value', 'string')],
		keep_values=True, formstyle=FormStyleBulma)
	
	if path=='select':
		if len(search_form.vars) == 0:
			search_form.vars = session.get('filter') or {}
		else:
			filter=dict(mailing_list=search_form.vars.get('mailing_list'),
						event=search_form.vars.get('event'),
						field=search_form.vars.get('field'),
						value=search_form.vars.get('value')) if len(search_form.vars)>0 else {}
			if search_form.vars.get('good_standing'):
				filter['good_standing'] = 'On'
			session['filter'] = filter
		header = CAT(header, A("Send Email to Specific Address(es)", _href=URL('composemail')), XML('<br>'))
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page?authuser=1"
	elif path:
		caller = re.match(f'.*/{request.app_name}/([a-z_]*).*', session['url_prev']).group(1)
		if caller!='members' and caller not in ['composemail', 'affiliations', 'emails', 'dues', 'member_reservations']:
			session['back'].append(session['url_prev'])
		if len(session['back'])>0 and re.match(f'.*/{request.app_name}/([a-z_]*).*', session['back'][-1]).group(1)!='members':
			back = session['back'][-1]
		header = CAT(A('back', _href=back), H5('Member Record'))
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page/member-record?authuser=1"
		if path.startswith('edit') or path.startswith('details'):
			member_id = path[path.find('/')+1:]
			header= CAT(header, 
	       			A('Member reservations', _href=URL(f'member_reservations/{member_id}/select')), XML('<br>'),
					A('OxCam affiliation(s)', _href=URL(f'affiliations/N/{member_id}/select')), XML('<br>'),
					A('Email addresses and subscriptions', _href=URL(f'emails/N/{member_id}/select')), XML('<br>'),
					A('Dues payments', _href=URL(f'dues/{member_id}/select')), XML('<br>'),
					A('Send Email to Member', _href=URL('composemail',
					 	vars=dict(query=f"db.Members.id=={member_id}", left='',
		 					qdesc=member_name(member_id)))))
	else:
		session['filter'] = None
		session['back'] = []

	if search_form.vars.get('mailing_list'):
		query.append(f"(db.Members.id==db.Emails.Member)&db.Emails.Mailings.contains({search_form.vars.get('mailing_list')})")
		qdesc = f"{db.Email_Lists[search_form.vars.get('mailing_list')].Listname} mail list, "
	if search_form.vars.get('event'):
		if search_form.vars.get('mailing_list'):
			left=f"db.Reservations.on((db.Reservations.Member == db.Members.id)&(db.Reservations.Event=={search_form.vars.get('event')})&(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&(db.Reservations.Waitlist!=True))"
			query.append("(db.Reservations.id==None)")
		else:
			query.append(f"(db.Members.id==db.Reservations.Member)&(db.Reservations.Event=={search_form.vars.get('event')})&(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&(db.Reservations.Waitlist!=True)")
		qdesc += f"{'excluding ' if search_form.vars.get('mailing_list') else ''}{db.Events[search_form.vars.get('event')].Description[0:25]} attendees, "
	if search_form.vars.get('good_standing'):
		query.append("((db.Members.Membership!=None)&(((db.Members.Paiddate==None)|(db.Members.Paiddate>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()))|(db.Members.Charged!=None)|((db.Members.Stripe_subscription!=None)&(db.Members.Stripe_subscription!=('Cancelled')))))")
		qdesc += ' in good standing, '
	if search_form.vars.get('value'):
		field = search_form.vars.get('field')
		value = search_form.vars.get('value')
		if not search_form.vars.get('field'):
			errors = 'Please specify which field to search'
		elif field == 'Affiliation':
			query.append(f'db.Colleges.Name.ilike("%{value}%")&(db.Affiliations.College==db.Colleges.id)&(db.Members.id==db.Affiliations.Member)')
			qdesc += f" with affiliation matching '{value}'."
		elif field == 'Email':
			query.append(f"(db.Members.id==db.Emails.Member)&db.Emails.Email.ilike('%{value}%')")
			qdesc += f" with email matching '{value}'."
		else:
			fieldtype = eval("db.Members."+field+'.type')
			m = re.match(r"^([<>]?=?)\s*(.*)$", value, flags=re.DOTALL)
			operator = m.group(1)
			value = m.group(2)
			if fieldtype == 'string' or fieldtype == 'text':
				if not operator:
					query.append(f'db.Members.{field}.ilike("%{value}%")')
					qdesc += f' {field} contains {value}.'
				elif operator == '=':
					query.append(f'db.Members.{field}.ilike("{value}")')
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
	
	if path=='select':
		if qdesc:
			header = CAT(header,
				A(f"Send Notice to {qdesc}", _href=URL('composemail',
					vars=dict(query=query, left=left or '', qdesc=qdesc))), XML('<br>'))
		header = CAT(header,
	       XML("Use filter to select a mailing list or apply other filters.<br>Selecting an event selects \
(or excludes from a mailing list) attendees.<br>You can filter on a member record field \
using an optional operator (=, <, >, <=, >=) together with a value."))
		footer = CAT(A("View recent Dues Payments", _href=URL('get_date_range',
				vars=dict(function='dues_payments', title="Dues Payments"))), XML('<br>'),
			A("Export membership analytics as CSV file", _href=URL('member_analytics')), XML('<br>'),
			A("Export selected records as CSV file", _href=URL('members_export',
						vars=dict(query=query, left=left or '', qdesc=qdesc))))

	def member_deletable(id): #deletable if not member, never paid dues or attended recorded event, or on mailing list
		m = db.Members[id]
		emails = db(db.Emails.Member == id).select()
		ifmailings = False
		for em in emails:
			if em.Mailings and len(em.Mailings) > 0: ifmailings = True
		return not m.Membership and not m.Paiddate and not m.Access and \
				not ifmailings and db(db.Dues.Member == id).count()==0 and \
				db(db.Reservations.Member == id).count()==0 and not m.President

	def validate(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if not form.vars.get('id'):
			return	#adding record
		
		if form.vars.get('Paiddate'):
			dues = db(db.Dues.Member == form.vars.get('id')).select(orderby=~db.Dues.Date).first()
			if dues:
				dues.update_record(Nowpaid = form.vars.get('Paiddate'))

	grid = Grid(path, eval(query), left=eval(left) if left else None,
	     	orderby=db.Members.Lastname|db.Members.Firstname,
			columns=[Column('Name', lambda r: member_name(r['id'])),
	    			db.Members.Membership, db.Members.Paiddate,
				    Column('Affiliations', lambda r: member_affiliations(r['id'])),
					db.Members.Access],
			headings=['Name', 'Status', 'Until', 'College', 'Access'],
			details=not write, editable=write, create=write, show_id=True,
			grid_class_style=grid_style,
			formstyle=form_style,
			search_form=search_form,
			validation=validate,
			deletable=lambda r: member_deletable(r['id'])
			)
	return locals()

@action('members_export', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def members_export():
	stream = StringIO()
	content_type = "text/csv"
	filename = 'members.csv'
	query = request.query.get('query')
	left = request.query.get('left')
	rows = db(eval(query)).select(db.Members.ALL, left=left, orderby=db.Members.Lastname|db.Members.Firstname)
	try:
		writer=csv.writer(stream)
		writer.writerow(['Name', 'Affiliations', 'Emails']+db.Members.fields)
		for row in rows:
			data = [member_name(row.id), member_affiliations(row.id), member_emails(row.id)]+[row[field] for field in db.Members.fields]
			writer.writerow(data)
	except Exception as e:
		flash.set(e)
		redirect(URL('members/select'))
	return locals()	

@action('member_analytics', method=['GET'])
@action('member_analytics/<path:path>', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def member_analytics(path=None):
	stream=StringIO()
	content_type = "text/csv"
	filename = 'member_analytics.csv'
	writer=csv.writer(stream)
	writer.writerow(['Name', 'Matr', 'AgeBand', 'Year', 'Category'])

	matr = db.Affiliations.Matr.min()
	matrrows = db(db.Affiliations.Matr!=None).select(db.Affiliations.Member, matr, groupby = db.Affiliations.Member)

	query = (db.Members.Paiddate >= datetime.date(2007,1,1))|((db.Members.Paiddate==None)&(db.Members.Membership!=None))
	left = db.Dues.on(db.Dues.Member==db.Members.id)

	rows = db(query).select(db.Members.id, db.Members.Firstname, db.Members.Lastname,
			 		db.Members.Paiddate, db.Members.Created, db.Dues.Date, 
					db.Dues.Amount, db.Dues.Nowpaid, db.Dues.Prevpaid, db.Dues.Status,
					orderby=db.Members.Lastname|db.Members.Firstname|db.Dues.Date,
					left = left)
	
	l = None
	thisyear = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year
	for r in rows:
		if r.Members.Lastname == 'Allen':
			pass
		if not l or r.Members.id != l.Members.id:
			endyear = 0
			name = r.Members.Lastname + ', ' + r.Members.Firstname
			m = matrrows.find(lambda m: m.Affiliations.Member == r.Members.id).first()
			matric = m[matr] if m else None
			if r.Dues.Date and r.Dues.Prevpaid and not r.Dues.Nowpaid:
				#assume has been a member since 2007 until Prevaid
				startyear = max(r.Members.Created.date().year, 2007)
				endyear = r.Dues.Prevpaid.year - 1
				while startyear <= endyear:
					writer.writerow([name, str(matric) if matric else '',
									ageband(startyear, matric),
									str(startyear), r.Dues.Status if r.Dues.Status else 'Full'])
					startyear += 1
		l = r
		if not r.Members.Paiddate:	#life members
			startyear = max(r.Members.Created.date().year, 2007)
			endyear = thisyear
		elif not r.Dues.Date:	#no dues payment recorded
			endyear = r.Members.Paiddate.year - 1
			startyear = endyear
			# assume a one year membership from attending an event.
		elif not r.Dues.Nowpaid:
			startyear = max(r.Dues.Date.year, endyear+1)
			endyear = startyear + r.Dues.Amount/(5 if r.Dues.Status=='Student' else 20) - 1
		else:				#dues payments recorded
			startyear = max(r.Dues.Date.year, endyear+1)
			endyear = r.Dues.Nowpaid.year-1
			if r.Dues.Nowpaid>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date() and endyear==thisyear-1:
				endyear = thisyear	#assume renewal later this year
	
		while startyear <= endyear:
			writer.writerow([name, str(matric) if matric else '',
							ageband(startyear, matric),
							str(startyear), r.Dues.Status if r.Dues.Status else 'Full'])
			startyear += 1

	return locals()

@action('member_reservations/<member_id:int>', method=['POST', 'GET'])
@action('member_reservations/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def member_reservations(member_id, path=None):
# .../member_reservations/member_id/...
	access = session['access']	#for layout.html
	header = CAT(A('back', _href=URL(f"members/{'details' if access=='read' else 'edit'}/{member_id}", scheme=True)),
				H5('Member Reservations'),
	      		H6(member_name(member_id)),
				A('Add New Reservation', _href=URL(f'add_member_reservation/{member_id}', scheme=True)))
	if path=='select':
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page/member-reservations?authuser=1"
	else:
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/events-page/reservation-display?authuser=1"

	grid = Grid(path, (db.Reservations.Member==member_id)&(db.Reservations.Host==True),
			left=db.Events.on(db.Events.id == db.Reservations.Event),
			orderby=~db.Events.DateTime,
			columns=[db.Events.DateTime,
	    			Column('event', lambda row: A(row.Reservations.Event.Description[0:23], _href=URL(f"reservation/N/{member_id}/{row.Reservations.Event}"))),
				    Column('wait', lambda row: res_wait(row.Reservations.Member, row.Reservations.Event) or ''),
				    Column('conf', lambda row: res_conf(row.Reservations.Member, row.Reservations.Event) or ''),
				    Column('cost', lambda row: res_totalcost(row.Reservations.Member, row.Reservations.Event) or ''),
				    Column('tbc', lambda row: res_tbc(row.Reservations.Member, row.Reservations.Event, True) or '')],
			grid_class_style=grid_style,
			formstyle=form_style,
			details=False, editable = False, create = False, deletable = False)
	return locals()
	
@action('add_member_reservation/<member_id:int>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('write')
def add_member_reservation(member_id):
	access = session['access']	#for layout.html
	header = CAT(A('back', _href=URL(f'members/edit/{member_id}', scheme=True)),
	      		H5('Add New Reservation'),
	      		H6(member_name(member_id)),
				)

	form=Form([Field('event', 'reference db.Events',
		  requires=IS_IN_DB(db, 'Events', '%(Description)s', orderby = ~db.Events.DateTime,
		      				zero='Please select event for new reservation from dropdown.'))],
		formstyle=FormStyleBulma)
	
	if form.accepted:
		redirect(URL(f"reservation/N/{member_id}/{form.vars.get('event')}"))
	return locals()

@action('affiliations/<ismember>/<member_id:int>', method=['POST', 'GET'])
@action('affiliations/<ismember>/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def affiliations(ismember, member_id, path=None):
	access = session['access']	#for layout.html
	session['url']=session['url_prev']	#preserve back link
	if ismember=='Y':
		if member_id!=session['member_id']:
			raise Exception(f"invalid call to affiliations from member {session['member_id']}")
		write = True
	else:
		if not session.get('access'):
			redirect(URL('accessdenied'))
		db.Affiliations.Matr.requires=IS_EMPTY_OR(IS_INT_IN_RANGE(1900,datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date().year+1))
		#allow matr to be omitted, may get it from member later.
		write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page/member-affiliations?authuser=1"
	db.Affiliations.Member.default=member_id

	header = CAT(A('back', _href=session['url_prev']),
	      		H5('Member Affiliations'),
	      		H6(member_name(member_id)))
	footer = "Multiple affiliations are listed in order modified. The topmost one \
is used on name badges etc."

	def affiliation_modified(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(path, db.Affiliations.Member==member_id,
	     	orderby=db.Affiliations.Modified,
			columns=[db.Affiliations.College, db.Affiliations.Matr, db.Affiliations.Notes],
			details=not write, editable=write, create=write, deletable=write,
			validation=affiliation_modified,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

#switch user's primary email to newly validated email
@action('switch_email', method=['GET'])
@action.uses("gridform.html", session, db, flash)
def switch_email():
	member_id = request.query.get('member_id')
	member = db.Members[member_id]
	session['member_id'] = int(member_id)
	session['access'] = member.Access
	email_id = db.Emails.insert(Member=member_id, Email=session['email'], Mailings=eval(request.query.get('mailings')))
	flash.set("Please review your mailing list subscriptions")
	notify_support(member, 'Email address change',
		f"New primary email address {primary_email(member.id)}")
	session['url'] = URL('index')	#will be back link from emails page
	redirect(f"emails/Y/{member_id}/select")

@action('emails/<ismember>/<member_id:int>', method=['POST', 'GET'])
@action('emails/<ismember>/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def emails(ismember, member_id, path=None):
	access = session['access']	#for layout.html
	session['url']=session['url_prev']	#preserve back link
	if ismember=='Y':
		if member_id!=session['member_id']:
			raise Exception(f"invalid call to emails controller from member {session['member_id']}")
		write = True
	else:
		if not session['access']:
			redirect(URL('accessdenied'))
		write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page/member-emails?authuser=1"
	db.Emails.Member.default=member_id

	if path=='new':
		db.Emails.Email.writable = True
		old_primary_email = db(db.Emails.Member == member_id).select(orderby=~db.Emails.Modified).first()
		db.Emails.Mailings.default = old_primary_email.Mailings if old_primary_email else None
		if ismember=='Y':
			db.Emails.Mailings.readable=db.Emails.Mailings.writable=False
	elif path=='select':
		update_Stripe_email(db.Members[member_id])

	header = CAT(A('back', _href=session['url_prev']),
	      		H5('Member Emails'),
	      		H6(member_name(member_id)))
	if path=='select':
		header = CAT(header, XML("Note, the most recently edited (topmost) email is used for messages \
directed to the individual member, and appears in the Members Directory. Notices \
are sent as specified in the Mailings Column.<br>To switch to a new email address, use <b>+New</b> button.<br>\
To change your mailing list subscritions, use the <b>Edit</b> button."))
	footer = XML(MAIL_LISTS)

	def validate(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if ismember=='Y' and not form.vars.get('id'): #member adding new address
			session['url'] = URL('switch_email', vars=dict(mailings=db.Emails.Mailings.default,
										member_id=member_id))
			redirect(URL('send_email_confirmation', vars=dict(email=form.vars['Email'])))

	grid = Grid(path, db.Emails.Member==member_id,
	     	orderby=~db.Emails.Modified,
			columns=[db.Emails.Email, db.Emails.Mailings],
			details=not write, editable=write, create=write,
			deletable=lambda row: write and (ismember!='Y' or row['id']!=db(db.Emails.Member == member_id).select(orderby=~db.Emails.Modified).first().id),
			validation=validate,
			grid_class_style=grid_style,
			formstyle=form_style,
			)

	if ismember=='Y' and (path.startswith('edit') or path.startswith('details')):	#substitute user friendly form for grid form
		grid = None
		email = db.Emails[path[path.find('/')+1:]]
		header = CAT(header, email.Email)
		fields = []
		for list in db(db.Email_Lists.id>0).select():
			fields.append(Field(list.Listname.replace(' ', '_'), 'boolean', default=list.id in email.Mailings))
		form = Form(fields)
		if form.accepted:
			mailings = []
			for list in db(db.Email_Lists.id>0).select():
				if form.vars.get(list.Listname.replace(' ', '_')):
					mailings.append(list.id)
			email.update_record(Mailings=mailings)
			flash.set('Thank you for updating your mailing list subscriptions')
			notify_support(db.Members[member_id],"Mail Subscriptions Updated",
		  		f"{email.Email} {', '.join([list.Listname for list in db(db.Email_Lists.id.belongs(mailings)).select()])}")
			redirect(URL(f"emails/Y/{member_id}/select"))
	return locals()
	
@action('dues/<member_id:int>', method=['POST', 'GET'])
@action('dues/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def dues(member_id, path=None):
# .../dues/member_id/...
	access = session['access']	#for layout.html
	session['url']=session['url_prev']	#preserve back link
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page/member-dues?authuser=1"
	db.Dues.Member.default=member_id

	member=db.Members[member_id]
	db.Dues.Member.default=member.id
	db.Dues.Status.default=member.Membership
	db.Dues.Prevpaid.default = member.Paiddate
	db.Dues.Nowpaid.default = newpaiddate(member.Paiddate)

	header = CAT(A('back', _href=session['url_prev']),
	      		H5('Member Dues'),
	      		H6(member_name(member_id)))

	def dues_validated(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (not form.vars.get('id')): 	#adding dues record
			member.update_record(Membership=form.vars.get('Status'), Paiddate=form.vars.get('Nowpaid'),
								Charged=None)

	grid = Grid(path, db.Dues.Member==member_id,
	     	orderby=~db.Dues.Date,
			columns=[db.Dues.Amount, db.Dues.Date, db.Dues.Notes, db.Dues.Prevpaid, db.Dues.Nowpaid],
			details=not write, editable=write, create=write, deletable=write,
			validation=dues_validated,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()
	
@action('dues_payments', method=['GET'])
@action('dues_payments/<path:path>', method=['GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def dues_payments(path=None):
	access = session['access']	#for layout.html
	if not path:
		session['query2'] = f"(db.Dues.Date >= \'{request.query.get('start')}\') & (db.Dues.Date <= \'{request.query.get('end')}\')"
	
	header =H5('Dues Payments')
	footer = A("Export as CSV file", _href=URL('dues_export'))

	grid = Grid(path, eval(session.get('query2')),
			orderby=~db.Dues.Date,
			columns=[Column("Name", lambda row: A(member_name(row['Member'])[0:20], _href=URL(f"members/edit/{row['Member']}"))),
	    			Column("College", lambda row: primary_affiliation(row['Member'])),
	    			Column("Matr", lambda row: primary_matriculation(row['Member'])),
					db.Dues.Status, db.Dues.Date, db.Dues.Prevpaid, db.Dues.Nowpaid,
					Column("Type", lambda row: dues_type(row['Date'], row['Prevpaid']))],
			deletable=False, details=False, editable=False, create=False,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

@action('dues_export', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('read')
def dues_export():
	stream = StringIO()
	content_type = "text/csv"
	filename = 'dues.csv'
	query = session['query2']
	rows = db(eval(query)).select(orderby=~db.Dues.Date)
	try:
		writer=csv.writer(stream)
		writer.writerow(['Member_id', 'Name', 'College', 'Matr', 'Status', 'Date', 'PrevDate', 'Type'])
		for row in rows:
			data = [row.Member, member_name(row.Member), primary_affiliation(row.Member), 
	   				primary_matriculation(row.Member), row.Status, row.Date, row.Prevpaid or '',
					dues_type(row.Date, row.Prevpaid)]
			writer.writerow(data)
	except Exception as e:
		flash.set(e)
		redirect(session['url_prev'])
	return locals()	
	
@action('events', method=['POST', 'GET'])
@action('events/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def events(path=None):
	access = session['access']	#for layout.html
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	back = URL('events/select', scheme=True)

	header = H5('Events')

	if not path:
		session['back'] = []
	elif path=='select':
		footer = CAT(A("Export all Events as CSV file", _href=URL('events_export')), XML('<br>'),
			A("Export event analytics as CSV file", _href=URL('event_analytics')))
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/events-page?authuser=1"
	elif path=='new':
		header = CAT(A('back', _href=back), H5('New Event'))
		_help = "https://sites.google.com/oxcamne.org/help-new/how-to/set-up-a-new-event?authuser=1"
	else:
		url = URL('register', path[path.find('/')+1:], scheme=True)
		header = CAT(A('back', _href=back), H5('Event Record'),
	       			"Booking link is ", A(url, _href=url), XML('<br>'),
	       			A('Make a Copy of This Event', _href=URL('event_copy', path[path.find('/')+1:])))
		_help = "https://sites.google.com/oxcamne.org/help-new/how-to/set-up-a-new-event?authuser=1"
	       		
	def checktickets(form):
		for t in form.vars['Tickets']:
			if t!='' and not re.match(r'[^\$]*\$[0-9]+\.?[0-9]{0,2}$', t):
				form.errors['Tickets'] = f"{t} is not a good ticket definition"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(path, db.Events.id>0,
	     	orderby=~db.Events.DateTime,
		    headings=['Datetime', 'Event', 'Venue', 'Paid', 'TBC', 'Conf', 'Wait'],
			columns=[db.Events.DateTime,
					Column('event', lambda row: A(row.Description[0:23], _href=URL(f"event_reservations/{row['id']}"))),
	   				db.Events.Venue,
					Column('Paid', lambda row: event_revenue(row.id) or ''),
					Column('TBC', lambda row: event_unpaid(row.id) or ''),
					Column('Conf', lambda row: event_attend(row.id) or ''),
					Column('Wait', lambda row: event_wait(row.id) or '')],
			search_queries=[["Event", lambda value: db.Events.Description.ilike(f'%{value}%')],
		    				["Venue", lambda value: db.Events.Venue.ilike(f'%{value}%')],
						    ["Speaker", lambda value: db.Events.Speaker.ilike(f'%{value}%')]],
			details=not write, editable=write, create=write,
			deletable=lambda r: write and db(db.Reservations.Event == r['id']).count() == 0 and db(db.AccTrans.Event == r['id']).count() == 0,
			validation=checktickets,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

@action('event_analytics', method=['GET'])
@action('event_analytics/<path:path>', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def event_analytics():
	stream=io.StringIO()
	content_type = "text/csv"
	filename = 'event_analytics.csv'

	writer=csv.writer(stream)
	writer.writerow(['Name', 'College', 'Oxbridge', 'Matr', 'AgeBand', 'PartySize', 'Event', 'EventYear'])

	rows = db((db.Reservations.Host==True) & (db.Reservations.Waitlist==False) & (db.Reservations.Provisional==False)& \
					(db.Reservations.Event == db.Events.id)).select(db.Reservations.Member, db.Reservations.Lastname,
				db.Reservations.Firstname, db.Reservations.Affiliation, db.Events.Description, db.Events.DateTime, db.Events.id,
					orderby = db.Reservations.Lastname|db.Reservations.Firstname|db.Events.DateTime)

	membid = 0

	for r in rows:
		if r.Reservations.Member != membid:
			membid = r.Reservations.Member
			name = r.Reservations.Lastname + ', ' + r.Reservations.Firstname
			matric = None
			affs = db((db.Affiliations.Member==membid) & (db.Affiliations.Matr!=None)).select(db.Affiliations.Matr)
			for m in affs:
				if m.Matr<(matric or 10000):
					matric =m.Matr
			college = ''
			oxbridge = True
			if r.Reservations.Affiliation:
				c = db.Colleges[r.Reservations.Affiliation]
				college = c.Name
				oxbridge = c.Oxbridge
		
		partysize = db((db.Reservations.Event==r.Events.id) & (db.Reservations.Member==r.Reservations.Member)).count()

		writer.writerow([name, college, oxbridge,
							str(matric) if matric else '', ageband(r.Events.DateTime.year, matric),
							str(partysize), r.Events.Description,
							r.Events.DateTime.year if r.Events.DateTime.month <= 9 else r.Events.DateTime.year + 1])
	return locals()
		
@action('event_reservations/<event_id:int>', method=['POST', 'GET'])
@action('event_reservations/<event_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def event_reservations(event_id, path=None):
# ...event_reservatins/event_id/...
# request.query: waitlist=True, provisional=True
	access = session['access']	#for layout.html
	db.Reservations.id.readable=db.Reservations.Event.readable=False
	back=URL(f'event_reservations/{event_id}/select', vars=request.query, scheme=True)

	event = db.Events[event_id]
	header = CAT(A('back', _href=URL('events/select')),
	      		H5('Provisional Reservations' if request.query.get('provisional') else 'Waitlist' if request.query.get('waitlist') else 'Reservations'),
				H6(f"{event.DateTime}, {event.Description}"),
				XML("Click on the member name to drill down on a reservation and view/edit the details."), XML('<br>'))
	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/events-page/reservation-list?authuser=1"

	query = f'(db.Reservations.Event=={event_id})'
	#for waitlist or provisional, have to include hosts with waitlisted or provisional guests
	if request.query.get('waitlist') or request.query.get('provisional'):
		query += f"&db.Reservations.Member.belongs([r.Member for r in \
db((db.Reservations.Event=={event_id})&{'(db.Reservations.Waitlist==True)' if request.query.get('waitlist') else '(db.Reservations.Provisional==True)'}).\
select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	else:
		query += '&(db.Reservations.Waitlist==False)&(db.Reservations.Provisional==False)'
		header = CAT(header, A('Export Doorlist as CSV file',
			 _href=(URL(f'doorlist_export/{event_id}', scheme=True))), XML('<br>'))
	query += '&(db.Reservations.Host==True)'

	if not request.query.get('provisional'):
		header = CAT(header, A('Send Email Notice', _href=URL('composemail', vars=dict(query=query,
			left  = "[db.Emails.on(db.Emails.Member==db.Reservations.Member),db.Members.on(db.Members.id==db.Reservations.Member)]",	
			qdesc=f"{event.Description} {'Waitlist' if request.query.get('waitlist') else 'Attendees'}",
			))), XML('<br>'))
	header = CAT(header, XML('Display: '))
	if request.query.get('waitlist') or request.query.get('provisional'):
		header = CAT(header, A('reservations', _href=URL(f'event_reservations/{event_id}')), ' or ')
	if not request.query.get('waitlist'):
		header = CAT(header, A('waitlist', _href=URL(f'event_reservations/{event_id}/select', vars=dict(waitlist=True))), ' or ')
		
	if not request.query.get('provisional'):
		header = CAT(header, A('provisional', _href=URL(f'event_reservations/{event_id}/select', vars=dict(provisional=True))), XML(' (not checked out)'))
	grid = Grid(path, eval(query),
			left=db.Members.on(db.Members.id == db.Reservations.Member),
			orderby=db.Reservations.Created if request.query.get('waitlist') else db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[Column('member', lambda row: A(member_name(row.Reservations.Member)[0:20], _href=URL(f"reservation/N/{row.Reservations.Member}/{event_id}/select"))),
	    				db.Members.Membership, db.Members.Paiddate, db.Reservations.Affiliation, db.Reservations.Notes,
					    Column('cost', lambda row: res_totalcost(row.Reservations.Member, row.Reservations.Event) or ''),
					    Column('tbc', lambda row: res_tbc(row.Reservations.Member, row.Reservations.Event, True) or ''),
					    Column('count', lambda row: (res_wait(row.Reservations.Member, row.Reservations.Event) if request.query.get('waitlist')\
				      		else res_prov(row.Reservations.Member, row.Reservations.Event) if request.query.get('provisional') else res_conf(row.Reservations.Member, row.Reservations.Event)) or'')],
			headings=['Member', 'Type', 'Until', 'College', 'Notes', 'Cost', 'Tbc', '#'],
			details=False, editable = False, create = False, deletable = False,
			rows_per_page=200, grid_class_style=grid_style, formstyle=form_style)
	return locals()
	
@action('reservation/<ismember>/<member_id:int>/<event_id:int>', method=['POST', 'GET'])
@action('reservation/<ismember>/<member_id:int>/<event_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def reservation(ismember, member_id, event_id, path=None):
#this controller is for dealing with the addition/modification of an expanded reservation
#used both by database users with access privilege, and by members themselves registering for events.
# in the latter case, ismember=='Y'
	access = session['access']	#for layout.html
	if ismember=='Y':
		if member_id!=session['member_id']:
			raise Exception(f"invalid call to reservation from member {session['member_id']}")
		write = True
		db.Reservations.Provisional.default = True
		db.Reservations.Waitlist.writable = db.Reservations.Waitlist.readable = False
	else:
		if not session.get('access'):
			session['url'] = session['url_prev']
			redirect(URL('accessdenied'))
		write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
		_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/events-page/reservation-display?authuser=1"

	db.Reservations.Created.default = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	member = db.Members[member_id]
	event = db.Events[event_id]
	session['event_id'] = event_id
	is_good_standing = member_good_standing(member, event.DateTime.date())
	if is_good_standing:
		membership = member.Membership
	elif ismember=='Y':
		membership = session.get('membership')
		if membership:		#joining as part of event registration
			is_good_standing = True

	all_guests = db((db.Reservations.Member==member.id)&(db.Reservations.Event==event.id)).select(orderby=~db.Reservations.Host)
	host_reservation = all_guests.first()
	confirmed_ticket_cost = 0
	provisional_ticket_cost = 0
	adding = 0
	confirmed = 0
	for row in all_guests:
		if row.Ticket:
			row.update_record(Unitcost=decimal.Decimal(re.match('.*[^0-9.]([0-9]+\.?[0-9]{0,2})$', row.Ticket).group(1)))
		if not row.Waitlist:
			if row.Provisional:
				adding += 1
				provisional_ticket_cost += row.Unitcost or 0
			else:
				confirmed += 1
				confirmed_ticket_cost += row.Unitcost or 0
	
	back = URL(f'reservation/{ismember}/{member_id}/{event_id}/select')
	caller = re.match(f'.*/{request.app_name}/([a-z_]*).*', session['url_prev']).group(1)
	if caller not in ['reservation', 'composemail', 'members']:
		session['back'].append(session['url_prev'])
	if path=='select':
			back = session['back'][-1]

	header = CAT(H5('Event Registration'), H6(member_name(member_id)),
			XML(event_confirm(event.id, member.id, event_only=True)))
	if ismember!='Y':
		header = CAT(A('back', _href=back), header)

	if path=='select':
		if ismember=='Y':
			if not host_reservation:
				redirect(URL(f'reservation/Y/{member_id}/{event_id}/new'))
			attend = event_attend(event_id) or 0
			wait = event_wait(event_id) or 0
			waitlist = False
			if datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.Booking_Closed:
				waitlist = True
				flash.set("Registration is closed, new registrations will be waitlisted.")
			elif wait > 0 or (event.Capacity and attend+adding>event.Capacity):
				waitlist = True
				flash.set("Event is full: please Checkout to add all unconfirmed guests to the waitlist.")
			elif event.Capacity and attend+adding>=event.Capacity-2:
				flash.set(f"Event is nearly full, registration for more than {event.Capacity-attend} places will be wait listed.")
			dues_tbc = f", including ${session['dues']} membership dues." if session.get('dues') else '.'
			payment = (int(session.get('dues') or 0)) + confirmed_ticket_cost - (host_reservation.Paid or 0) - (host_reservation.Charged or 0)
			if not waitlist:
				payment += (provisional_ticket_cost or 0)
			if not event.Guests or len(all_guests)<event.Guests:
				header = CAT(header,  XML(f"Use the blue <b>+New</b> button to add guests.<br>"))
			if adding!=0 or payment!=0:
				header = CAT(header,  XML(f"Use the blue <b>Checkout</b> button (below) to complete your registration.<br>"))
			if payment>0:
				header = CAT(header, XML(f"You will be charged ${payment} at Checkout{dues_tbc}<br>"))

			fields = []
			if event.Survey:
				fields.append(Field('survey', requires=IS_IN_SET(event.Survey[1:], zero=event.Survey[0],
									error_message='Please make a selection'),
									default = host_reservation.Survey if host_reservation else None))
			if event.Comment:
				fields.append(Field('comment', 'string', comment=event.Comment,
									default = host_reservation.Comment if host_reservation else None))
			if host_reservation:
				host_reservation.update_record(Checkout=str(dict(membership=session.get('membership'), dues=session.get('dues'))).replace('Decimal','decimal.Decimal'))
				form2 = Form(fields, formstyle=FormStyleBulma, keep_values=True, submit_value='Checkout')
		else:
			header = CAT(header, A('send email', _href=(URL('composemail', vars=dict(
				query=f"(db.Members.id=={member_id})&(db.Members.id==db.Reservations.Member)&(db.Reservations.Event=={event_id})",
				qdesc=member_name(member_id), left="db.Emails.on(db.Emails.Member==db.Members.id)")))),
				XML(" (use "), "<reservation>", XML(" to include confirmation and payment link)<br>"),
				A('view member record', _href=URL(f'members/edit/{member_id}')),
				XML("<br>Top row is the member's own reservation, additional rows are guests.<br>\
Use Add Record to add the member, initially, then to add additional guests.<br>\
Edit rows to move on/off waitlist or first row to record a check payment.<br>\
Moving member on/off waitlist will also affect all guests."))

	#set up reservations form, we have both member and event id's
	db.Reservations.Member.default = member.id
	db.Reservations.Event.default=event.id
	clist = collegelist(sponsors = event.Sponsors or [])
	db.Reservations.Affiliation.requires=requires=IS_EMPTY_OR(IS_IN_SET(clist))

	if host_reservation:
		#update member's name from member record in case corrected
		host_reservation.update_record(Title=member.Title, Firstname=member.Firstname,
					Lastname=member.Lastname, Suffix=member.Suffix) 
			
	if len(event.Selections)>0:
		db.Reservations.Selection.requires=IS_IN_SET(event.Selections, error_message='please make a selection')
	else:
		db.Reservations.Selection.writable = db.Reservations.Selection.readable = False
		
	if len(event.Tickets)>0:
		db.Reservations.Ticket.requires=IS_EMPTY_OR(IS_IN_SET(event.Tickets, error_message='please select the appropriate ticket'))
	else:
		db.Reservations.Ticket.writable = db.Reservations.Ticket.readable = False
	
	db.Reservations.Event.writable=db.Reservations.Event.readable=False
	if ismember!='Y':
		db.Reservations.Provisional.writable = db.Reservations.Provisional.readable = True
	db.Reservations.Member.readable = False

	if path and path != 'select' and not path.startswith('delete'):	#editing or creating reservation
		db.Reservations.Unitcost.writable=db.Reservations.Unitcost.readable=False
		if ismember=='Y':
			db.Reservations.Modified.readable = db.Reservations.Modified.writable = False
		else:
			db.Reservations.Survey.readable = True
			db.Reservations.Comment.readable = True
		if host_reservation and (path=='new' or host_reservation.id!=int(path[path.find('/')+1:])):
			#this is a new guest reservation, or we are revising a guest reservation
			db.Reservations.Host.default=False
			db.Reservations.Firstname.writable=True
			db.Reservations.Lastname.writable=True
			db.Reservations.Ticket.default = event.Tickets[0]
		else:
			#creating or revising the host reservation
			db.Reservations.Title.default = member.Title
			db.Reservations.Firstname.default = member.Firstname
			db.Reservations.Lastname.default = member.Lastname
			db.Reservations.Suffix.default = member.Suffix
			if ismember!='Y':
				db.Reservations.Paid.writable=db.Reservations.Paid.readable=True
				db.Reservations.Charged.writable=db.Reservations.Charged.readable=True
				db.Reservations.Checkout.writable=db.Reservations.Checkout.readable=True
			db.Reservations.Firstname.readable=db.Reservations.Lastname.readable=False
			if event.Tickets:
				db.Reservations.Ticket.default = event.Tickets[0]
				for t in event.Tickets:
					if is_good_standing:
						if t.lower().startswith(membership.lower()):
							db.Reservations.Ticket.default = t
							db.Reservations.Ticket.writable = False
					elif t.lower().startswith('non-member'):
						db.Reservations.Ticket.default = t
						db.Reservations.Ticket.writable = False

			affinity = db(db.Affiliations.Member==member_id).select(orderby=db.Affiliations.Modified).first()
			if affinity:
				db.Reservations.Affiliation.default = affinity.College
				db.Reservations.Affiliation.writable = False

			if ismember=='Y' and path=='new' and not event.Selections and \
				(not event.Tickets or len(event.Tickets)==1 or db.Reservations.Ticket.writable==False):
				#no choices needed, create the Host reservation and display checkout screen
				db.Reservations.insert(Member=member_id, Event=event_id, Host=True,
			   		Firstname=member.Firstname, Lastname=member.Lastname, Affiliation=affinity.College,
					Ticket=db.Reservations.Ticket.default)
				redirect(URL(f"reservation/Y/{member_id}/{event_id}/select"))
	
	def validate(form):
		if form.vars.get('Waitlist') and form.vars.get('Provisional'):
			form.errors['Waitlist'] = "Waitlist and Provisional should not both be set"
		if ismember=='Y' and form.vars.get('Ticket') != db.Reservations.Ticket.default and db.Reservations.Ticket.writable==True:
			if form.vars.get('Ticket'):
				if host_reservation and form.vars.get('Ticket').endswith('$0'):
					form.errors['Ticket'] = "Freshers should please register themselves individually."
				elif not form.vars.get('Notes'):
					form.errors['Ticket']='Please note below how this guest qualifies for the ticket discount.'
			else:
				form.errors['Ticket'] = "Please select the appropriate ticket type."
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id')):
			if int(form.vars.get('id')) == host_reservation.id and form.vars.get('Waitlist') != host_reservation.Waitlist:
				for row in all_guests:
					if row.id != host_reservation.id and not row.Provisional:
						row.update_record(Waitlist = form.vars.get('Waitlist'))

	grid = Grid(path, (db.Reservations.Member==member.id)&(db.Reservations.Event==event.id),
			orderby=~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[db.Reservations.Lastname, db.Reservations.Firstname, 
					db.Reservations.Notes, db.Reservations.Selection, db.Reservations.Unitcost,
					Column('Status', lambda row: res_status(row.id))],
			headings=['Last', 'First', 'Notes', 'Selection', 'Price', 'Status'],
			deletable=lambda row: write and (len(all_guests)==1 or row['id'] != host_reservation.id) \
						and (ismember!='Y' or row.Provisional or row.Waitlist),
			details=not write, 
			editable=lambda row: write and (ismember!='Y' or row['Provisional'] or row['Waitlist']), 
			create=write and (ismember!='Y' or not event.Guests or (len(all_guests)<event.Guests)),
			grid_class_style=grid_style, formstyle=form_style, validation=validate, show_id=ismember!='Y')
	
	if ismember=='Y' and path=='select':
		if len(form2.errors)>0:
			flash.set("Error(s) in form, please check")
		elif adding==0 and payment==0:
			form2 = ''	#don't need the Checkout form
		elif form2.accepted:
			#Checkout logic
			host_reservation.update_record(Survey=form2.vars.get('survey'), Comment=form2.vars.get('comment'))
			for row in all_guests.find(lambda row: row.Provisional==True):
				row.update_record(Provisional=False, Waitlist=waitlist)

			if waitlist:
				flash.set(f"{'You' if confirmed==0 else 'Your additional guest(s)'} have been added to the waitlist.")
			
			if payment==0:	#free event, confirm booking
				if not waitlist:
					host_reservation.update_record(Checkout=None)
					subject = 'Registration Confirmation'
					message = msg_header(member, subject)
					message += '<br><b>Your registration is now confirmed:</b><br>'
					message += event_confirm(event.id, member.id, 0)
					msg_send(member, subject, message)
					flash.set('Thank you. Confirmation has been sent by email.')
				redirect(back)
			redirect(URL('checkout'))
	return locals()

@action('doorlist_export/<event_id:int>', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('read')
def doorlist_export(event_id):
	stream = StringIO()
	content_type = "text/csv"
	filename = 'doorlist.csv'
	hosts = db((db.Reservations.Event==event_id)&(db.Reservations.Host==True)&(db.Reservations.Waitlist==False)&(db.Reservations.Provisional==False)).select(
					orderby=db.Reservations.Lastname|db.Reservations.Firstname,
					left=db.Members.on(db.Reservations.Member == db.Members.id))
	try:
		writer=csv.writer(stream)
		writer.writerow(['HostLast','HostFirst','Notes','LastName','FirstName','CollegeName','Selection','Table','Ticket',
							'Email','Cell','Survey','Comment'])
		for host in hosts:
			guests=db((db.Reservations.Event==event_id)&(db.Reservations.Member==host.Reservations.Member)\
					&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).select(
				orderby=~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname)
				
			for guest in guests:
				email = primary_email(host.Members.id) if host.Reservations.id==guest.id else ''
				writer.writerow([host.Reservations.Lastname, host.Reservations.Firstname, guest.Notes or '',
									guest.Lastname, guest.Firstname, guest.Affiliation.Name if guest.Affiliation else '',
									guest.Selection or '', '', guest.Ticket or '', email,
									host.Members.Cellphone if host.Reservations.id==guest.id else '',
									guest.Survey or '', guest.Comment or ''])
	except Exception as e:
		flash.set(e)
		redirect(session['url_prev'])
	return locals()
	
@action('event_copy/<event_id:int>', method=['GET'])
@action.uses(db, session, flash)
@checkaccess('write')
def event_copy(event_id):
	event = db.Events[event_id]
	db.Events.insert(Page=event.Page, Description='Copy of '+event.Description, DateTime=event.DateTime,
				Booking_Closed=event.Booking_Closed, Members_only=event.Members_only, Allow_join=event.Allow_join,
				Guest=event.Guests, Sponsors=event.Sponsors, Venue=event.Venue, Capacity=event.Capacity,
				Speaker=event.Speaker, Tickets=event.Tickets, Selections=event.Selections,
				Notes=event.Notes, Survey=event.Survey, Comment=event.Comment)
	redirect(URL('events/select'))

@action('events_export', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def events_export():
	stream = StringIO()
	content_type = "text/csv"
	filename = 'events.csv'
	rows = db(db.Events.id>0).select(db.Events.ALL, orderby=~db.Events.DateTime)
	try:
		writer=csv.writer(stream)
		writer.writerow(db.Events.fields+['Revenue', 'Unpaid', 'Provisional','Waitlist', 'Attendees'])
		for r in rows:
			data = [r[field] for field in db.Events.fields]+[event_revenue(r.id), event_unpaid(r.id),
					db((db.Reservations.Event==r.id)&(db.Reservations.Provisional==True)).count(),
					db((db.Reservations.Event==r.id)&(db.Reservations.Waitlist==True)).count(),
					db((db.Reservations.Event==r.id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).count()]
			writer.writerow(data)
	except Exception as e:
		flash.set(e)
	return locals()
	
@action('get_date_range', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('read')
def get_date_range():
# vars:	function: controller to be given the date range
#		title: heading for date range screen
#		range: ytd - year to date
#				 taxyear - prior full calendar year
#		otherwise one full year ending now
	access = session['access']	#for layout.html
	today = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()
	year_ago = (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) - datetime.timedelta(days=365) + datetime.timedelta(days=1)).date()
	year_begin = datetime.date(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year, 1, 1)	#start of current calendar 
	prev_year_begin = datetime.date(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year-1, 1, 1)
	prev_year_end = datetime.date(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year-1, 12, 31)

	header=H5(request.query.get('title'))		

	def checkform(form):
		if form.vars.start > form.vars.end:
			form.errors.end = 'end should not be before start!'
		
	form=Form(
		[Field('start', 'date', requires=[IS_NOT_EMPTY(),IS_DATE(format='%Y-%m-%d')],
			default = year_begin if request.query.get('range')=='ytd' else prev_year_begin if request.query.get('range')=='taxyear' else year_ago),
		Field('end', 'date', requires=[IS_NOT_EMPTY(),IS_DATE(format='%Y-%m-%d')],
			default = today if request.query.get('range')!='taxyear' else prev_year_end)]
	)
	
	if form.accepted:
		redirect(URL(request.query.get('function'), vars=dict(title=request.query.get('title'),
					start=form.vars.get('start'), end=form.vars.get('end'))))	
	return locals()

@action('financial_detail/<event:int>', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess('accounting')
def financial_detail(event, title=''):
	access = session['access']	#for layout.html
	title = request.query.get('title')
	
	caller = re.match(f'.*/{request.app_name}/([a-z_]*).*', session['url_prev']).group(1)
	if caller!='transactions':
		session['back'].append(session['url_prev'])
	session['url_prev'] = None #no longer needed, save cookie space

	message = CAT(A('back', _href=session['back'][-1]), H5(f'{title}'),
			financial_content(event if event!=0 else None, request.query.get('query'), request.query.get('left')))
	return locals()
	
@action('financial_statement', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess('accounting')
def financial_statement():
	access = session['access']	#for layout.html
	start = request.query.get('start')
	end = request.query.get('end')
	startdatetime = datetime.datetime.fromisoformat(start)
	enddatetime = datetime.datetime.fromisoformat(end)+datetime.timedelta(days=1)
	startdate = datetime.date.fromisoformat(start)
	enddate = datetime.date.fromisoformat(end)
	title = f"Financial Statement for period {start} to {end}"

	if not start or not end:
		redirect(URL('get_date_range', vars=dict(function='financial_statement',title='Financial Statement')))
		
	message = CAT(H5(title), H6('Assets'))
	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/accounts/financial-statement?authuser=1"

	sumamt = db.AccTrans.Amount.sum()
	sumfee = db.AccTrans.Fee.sum()

	def accrual(query, datetime):
		query+=f"&(((db.AccTrans.Timestamp<'{datetime}')&(db.AccTrans.Accrual==True))|((db.AccTrans.Timestamp>='{datetime}')&(db.Events.DateTime<'{datetime}')))"
		left="db.Events.on(db.Events.id==db.AccTrans.Event)"
		r = db(eval(query)).select(sumamt, left = eval(left)).first()
		return (r[sumamt] or 0, query, left)
		
	def prepaid(query, datetime):
		query+=f"&((db.AccTrans.Timestamp<'{datetime}')&(db.AccTrans.Accrual!=True)&(db.Events.DateTime>='{datetime}'))"
		left="db.Events.on(db.Events.id==db.AccTrans.Event)"
		r = db(eval(query)).select(sumamt, left = eval(left)).first()
		return (-(r[sumamt] or 0), query, left)
		
	def prepaiddues(date_time):
		end = (date_time + datetime.timedelta(days=365)).date()
		date = date_time.date()
		rows = db((db.Dues.Nowpaid > end) & (db.Dues.Date < date)).select()
		prepaid = 0
		for r in rows:
			yr = r.Prevpaid.year if r.Prevpaid else r.Date.year
			if yr < r.Date.year: yr = r.Date.year
			prepaid -= r.Amount * (r.Nowpaid.year - end.year) / (r.Nowpaid.year - yr)
		return (prepaid, None, None)
	
	assets = get_banks(startdatetime, enddatetime)
	
	assets['Accounts Payable'] = [accrual('(db.AccTrans.Amount<0)', startdatetime),
								accrual('(db.AccTrans.Amount<0)', enddatetime),'Pending event/accrued expenses']
	assets['Accounts Receivable'] = [accrual('(db.AccTrans.Amount>0)', startdatetime),
								accrual('(db.AccTrans.Amount>0)', enddatetime),'Pending event revenue']
	assets['Prepaid Expenses'] = [prepaid('(db.AccTrans.Amount<0)', startdatetime),
								prepaid('(db.AccTrans.Amount<0)', enddatetime), 'Event expenses prepaid']
	assets['Prepaid Events'] = [prepaid('(db.AccTrans.Amount>0)', startdatetime),
								prepaid('(db.AccTrans.Amount>0)', enddatetime), 'Event revenue prepaid']
	assets['Prepaid Dues'] = [prepaiddues(startdatetime), prepaiddues(enddatetime),'Dues prepaid for future years']
	
	#now build the report
	rows = [THEAD(TR(TH('Description'), TH(f'{start}'), TH(f'{end}'), TH('Net Change'), TH('Notes')))]
	totals = [0, 0]
	for a in sorted(assets):
		if assets[a][0][0] + assets[a][1][0] > 0: #positive balances, treat as asset
			rows.append(TR(TD(a), tdnum(assets[a][0][0], assets[a][0][1], assets[a][0][2]),
								tdnum(assets[a][1][0], assets[a][1][1], assets[a][1][2]),
								tdnum(assets[a][1][0]-assets[a][0][0]), TD(assets[a][2])))
			totals[0] += assets[a][0][0]
			totals[1] += assets[a][1][0]
	rows.append(THEAD(TR(TH('Total'), tdnum(totals[0], th=True), tdnum(totals[1], th=True), tdnum(totals[1]-totals[0], th=True))))
	message = CAT(message, TABLE(*rows))

	rows = [THEAD(TR(TH('Description'), TH(f'{start}'), TH(f'{end}'), TH('Net Change'), TH('Notes')))]
	ltotals = [0, 0]
	for a in sorted(assets):
		if assets[a][0][0] + assets[a][1][0] <= 0 and not (assets[a][0][0]==0 and assets[a][1][0]==0): #negative balances, treat as liability
			rows.append(TR(TD(a), tdnum(-assets[a][0][0], assets[a][0][1], assets[a][0][2]),
								tdnum(-assets[a][1][0], assets[a][1][1], assets[a][1][2]),
								tdnum(assets[a][0][0]-assets[a][1][0]), TD(assets[a][2])))
			ltotals[0] -= assets[a][0][0]
			ltotals[1] -= assets[a][1][0]
	rows.append(TR(TD('Reserve Fund'), tdnum(totals[0]-ltotals[0]), tdnum(totals[1]-ltotals[1]),
					tdnum(totals[1]-totals[0]-ltotals[1]+ltotals[0]), TD('Uncommitted Funds')))
	rows.append(THEAD(TR(TH('Total'), tdnum(totals[0], th=True), tdnum(totals[1], th=True), tdnum(totals[1]-totals[0], th=True))))
	message = CAT(message, H6('\nLiabilities'), TABLE(*rows))
	
	transfer = db(db.CoA.Name=='Transfer').select().first().id	#ignoretransfertransactions
	query = f"(((db.AccTrans.Event!=None)&(db.Events.DateTime>='{startdatetime}')&(db.Events.DateTime<'{enddatetime}'))|\
((db.AccTrans.Event==None)&(db.AccTrans.Account!={transfer})&\
(db.AccTrans.Timestamp>='{startdatetime}')&(db.AccTrans.Timestamp<'{enddatetime}')))"
	left='db.Events.on(db.Events.id==db.AccTrans.Event)'

	events = db(eval(query)).select(db.AccTrans.Event, db.Events.Description, db.Events.DateTime,
					left = eval(left), orderby = db.Events.DateTime, groupby = db.Events.DateTime)

	rows = [THEAD(TR(TH('Event'), TH('Date'), TH('Revenue'), TH('Expense'), TH('Net Revenue')))]
	totrev = totexp = 0
	for e in events:
		name = 'Admin' if e.AccTrans.Event == None else e.Events.Description
		date = '' if e.AccTrans.Event == None else e.Events.DateTime.date()
		rev = exp = 0
		accounts = db(eval(query+'&(db.AccTrans.Event==e.AccTrans.Event)')).select(sumamt, sumfee,
					left = eval(left), orderby = db.AccTrans.Account, groupby = db.AccTrans.Account)
		for a in accounts:
			if a[sumamt] >= 0:
				rev += a[sumamt]
			else:
				exp += a[sumamt]
			exp += a[sumfee] or 0
		rows.append(TR(TD(A(name[0:25], _href=URL(f'financial_detail/{e.AccTrans.Event or 0}', vars=dict(title=title, query=query, left=left)))), 
		 				TD(date), tdnum(rev), tdnum(exp), tdnum(rev + exp)))
		totrev += rev
		totexp += exp
	rows.append(THEAD(TR(TH('Total'), TH(''), tdnum(totrev, th=True),
		      tdnum(totexp, th=True), tdnum(totrev+totexp, th=True))))
	message  = CAT(message, H6('\nAdmin & Event Cash Flow'), TABLE(*rows))
	return locals()
	
@action('tax_statement', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess('accounting')
def tax_statement():
	access = session['access']	#for layout.html
	start = request.query.get('start')
	end = request.query.get('end')
	startdatetime = datetime.datetime.fromisoformat(start)
	enddatetime = datetime.datetime.fromisoformat(end)+datetime.timedelta(days=1)
	startdate = datetime.date.fromisoformat(start)
	enddate = datetime.date.fromisoformat(end)
	title = f"Financial Statement (cash based) for period {start} to {end}"
	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/accounts/tax-statement?authuser=1"

	if not start or not end:
		redirect(URL('get_date_range', vars=dict(function='financial_statement',title='Financial Statement')))
		
	message = CAT(H5(title), H6('Account Balances'))

	sumamt = db.AccTrans.Amount.sum()
	sumfee = db.AccTrans.Fee.sum()
	tktacct = db(db.CoA.Name=='Ticket sales').select().first().id
	sponacct = db(db.CoA.Name=='Sponsorships').select().first().id
	xferacct = db(db.CoA.Name=='Transfer').select().first().id	#ignore transfer transactions

	query = f"((db.AccTrans.Timestamp>='{startdatetime}')&(db.AccTrans.Timestamp < '{enddatetime}') & (db.AccTrans.Accrual!=True))"
	left = 'db.Events.on(db.Events.id == db.AccTrans.Event)'
	
	assets = get_banks(startdatetime, enddatetime)
	totals = [0, 0]
	rows = [THEAD(TR(TH('Description'), TH(start), TH(end), TH('Net Change'), TH('Notes')))]
	for a in sorted(assets):
		if assets[a][0][0] != 0 or assets[a][1][0] != 0:
			rows.append(TR(TD(a), tdnum(assets[a][0][0], assets[a][0][1], assets[a][0][2]),
								tdnum(assets[a][1][0], assets[a][1][1], assets[a][1][2]),
								tdnum(assets[a][1][0]-assets[a][0][0]), TD(assets[a][2])))
			totals[0] += assets[a][0][0]
			totals[1] += assets[a][1][0]
	rows.append(THEAD(TR(TH('Total'), tdnum(totals[0], th=True), tdnum(totals[1], th=True), tdnum(totals[1]-totals[0], th=True))))
	message = CAT(message, TABLE(*rows))

	tottkt = totspon = totrev = totexp = 0
	allrev = allexp = 0
	allrevexp = db(eval(f"{query}&(db.AccTrans.Account!={xferacct})")).select(sumamt, sumfee,
					orderby=db.AccTrans.Account, groupby=db.AccTrans.Account)
	for t in allrevexp:
		if t[sumamt] >= 0:
			allrev += t[sumamt]
		else:
			allexp += t[sumamt]
		allexp += (t[sumfee] or 0)

	events = db(eval(f"{query}&(db.AccTrans.Event!=None)")).select(db.Events.DateTime, db.Events.Description,
					db.Events.id, left = eval(left
			       ), orderby = db.Events.DateTime, groupby = db.Events.DateTime)
	rows =[THEAD(TR(TH('Event'), TH('Ticket Sales'), TH('Sponsorships'), TH('Revenue'), TH('Expense'), TH('Notes')))]
	for e in events:
		trans = db(eval(f"{query}&(db.AccTrans.Event=={e.id})")).select(db.AccTrans.Account, sumamt, sumfee,
					left = eval(left), orderby = db.AccTrans.Account, groupby = db.AccTrans.Account)
		tkt = trans.find(lambda t: t.AccTrans.Account == tktacct).first()
		spon = trans.find(lambda t: t.AccTrans.Account == sponacct).first()
		revenue = expense = 0
		for a in trans:
			if a[sumamt] >= 0:
				revenue += (a[sumamt] or 0)
			else:
				expense += (a[sumamt] or 0)
			expense += (a[sumfee] or 0)

		rows.append(TR(TD(A(e.Description[0:25], _href=URL(f'financial_detail/{e.id}', vars=dict(title=title, query=query, left=left)))),
					tdnum(tkt[sumamt] if tkt else 0), tdnum(spon[sumamt] if spon else 0),
					tdnum(revenue), tdnum(expense), TD(e.DateTime.date())))
		if spon:
			spontr = db(eval(f"{query}&(db.AccTrans.Event=={e.id})&(db.AccTrans.Account=={sponacct})")).select(
					db.AccTrans.Amount, db.AccTrans.Notes, left = eval(left))
			for t in spontr:
				rows.append(TR(TD(''), TD(''), tdnum(t.Amount), TD(''),TD(''), TD(t.Notes)))
		tottkt += tkt[sumamt] if tkt else 0
		totspon += spon[sumamt] if spon else 0
		totrev += revenue
		totexp += expense
	rows.append(THEAD(TR(TH('Totals'), tdnum(tottkt, th=True), tdnum(totspon, th=True), tdnum(totrev, th=True), tdnum(totexp, th=True))))
	rows.append(THEAD(TR(TH('with Other Exp./Rev.'), TH(''), TH(''), tdnum(allrev, th=True), tdnum(allexp, th=True))))
	rows.append(THEAD(TR(TH('Overall Net Revenue'), TH(''), TH(''), tdnum(allrev+allexp, th=True))))
	message = CAT(message, H6('Events'), TABLE(*rows))

	message = CAT(message, financial_content(None, query, left))
	return locals()
		
@action('accounting', method=['POST', 'GET'])
@action('accounting/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('accounting')
def accounting(path=None):
	access = session['access']	#for layout.html

	if not path:
		session['back'] = []	#stack or return addresses for controllers with multiple routes to reach them
		session['query'] = None	#query stored by transactions controller
		session['left'] = None	#accompanies query
	elif path=='select':
		header = CAT(H5('Banks'),
	       		A('Financial Statement', _href=URL('get_date_range', vars=dict(
					function='financial_statement', title='Financial Statement'))), XML('<br>'),
	       		A('Tax Statement', _href=URL('get_date_range', vars=dict(
					function='tax_statement', title='Tax Statement', range='taxyear'))), XML('<br>'),
				"Use Upload to load a file you've downloaded from bank/payment processor into accounting")
	else:
		header = CAT(A('back', _href=URL('accounting')) , H5('Banks'))
	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/accounts?authuser=1"

	grid = Grid(path, db.Bank_Accounts.id>0,
				orderby=db.Bank_Accounts.Name,
				columns=[db.Bank_Accounts.Name,
	     			Column('Accrued', lambda row: bank_accrual(row.id)),
	     			db.Bank_Accounts.Balance,
					Column('', lambda row: A('Upload', _href=URL(f'bank_file/{row.id}'))),
					Column('', lambda row: A('Transactions', _href=URL('transactions',
								vars=dict(query=f"db.AccTrans.Bank=={row.id}")))),
				],
				deletable=False, details=False, editable=True, create=True,
				grid_class_style=grid_style,
				formstyle=form_style,
	)		
	return locals()

@action('bank_file/<bank_id:int>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('accounting')
def bank_file(bank_id):
#upload and process a csv file from a bank or payment processor
#	.../bank_id		bank_id is reference to bank in Bank Accounts
	access = session['access']	#for layout.html
	bank = db.Bank_Accounts[bank_id]
	bkrecent = db((db.AccTrans.Bank==bank.id)&(db.AccTrans.Accrual!=True)).select(orderby=~db.AccTrans.Timestamp, limitby=(0,1)).first()
	unalloc = db(db.CoA.Name == 'Unallocated').select().first()
	acdues = db(db.CoA.Name == "Membership Dues").select().first()
	actkts = db(db.CoA.Name == "Ticket sales").select().first()
	origin = 'since account start'

	header = CAT(A('back', _href=URL('accounting')),
				H5(f"{bank.Name} Transactions"),
				XML(f"To download data since {markmin.markmin2html(f'``**{str(bkrecent.Timestamp.date()) if bkrecent else origin}**``:red')}:"), XML('<br>'),
				A('Login to Society Account', _href=bank.Bankurl, _target='blank'), XML('<br>'),
				XML(f"{markmin.markmin2html(bank.HowTo)}"))
	
	footer = f"Current Balance = {'$%8.2f'%(bank.Balance)}"
	stripe.api_key = STRIPE_SKEY
	
	form = Form([Field('downloaded_file', 'upload', uploadfield = False)],
				submit_button = 'Import')
	
	if not form.accepted:
		return locals()

	stored = 0
	unmatched = 0
	overlap = bkrecent==None
	row = None
	isok = True
				
	def getfields(cols, separator=''):
		if not cols: return None
		lcols= cols.split(',')
		s = ''
		for c in lcols:
			if s != '': s += separator
			s += row[c]
		return s
	def getdecimal(col):
		if not col: return 0
		sign = 1
		if col.startswith('-'):
			col = col[1:]
			sign = -1
		s = getfields(col)
		if not s or s == '': return 0
		#remove currency symbol, thousands commas, and deal with either '-' or (...) accounting format
		m = re.match('^([-\(]*)[^0-9]*([0-9.,-]*)\)*$', s)
		s = ('-' if m.group(1)!='' else '')+m.group(2).replace(',', '')
		return decimal.Decimal(s)*sign

#in the file, transactions may be in chronological order or the reverse (Stripe), so store them all in memory
#before processing. We first read from the file, to determine that there is overlap with previously processed files
#(at least one previously stored transaction in the file).
	file_transactions = []
	
	try:
		f = io.TextIOWrapper(form.vars.get('downloaded_file').file, encoding='utf-8')
		
		reader = csv.DictReader(f)
		headers = bank.Csvheaders.split(',')
		if headers != reader.fieldnames:
			raise Exception('File does not match expected column names')
		
		for row in reader:
			try:
				timestamp = datetime.datetime.strptime(getfields(bank.Date), bank.Datefmt)
			except:
				continue #special case, Cambridge Trust. Deposits made on the day the transactions are downloaded
				#are sent with date and time, but no reference. These early reports fail this timestamp conversion

			reference = getfields(bank.Reference)
			if db(db.AccTrans.Reference==reference).count() > 0:
				overlap = True
			else:
				file_transactions.insert(0,row) #reverse order so we process chronologically
			
		if overlap == False:
			raise Exception('file should start on or before '+bkrecent.Timestamp.date().strftime(bank.Datefmt))

		#now process the new transactions.				
		for row in file_transactions:
			reference = getfields(bank.Reference)
			timestamp = datetime.datetime.strptime(getfields(bank.Date), bank.Datefmt)
			if bank.Time:	#time is in a separate column
				time = datetime.datetime.strptime(getfields(bank.Time), bank.Timefmt)
				timestamp = datetime.datetime.combine(timestamp, time.time())
			
			#do the accounting
			checknumber = getfields(bank.CheckNumber)
			if checknumber and not checknumber.strip().isdigit():
				checknumber = None
			amount = getdecimal(bank.Amount)
			fee = getdecimal(bank.Fee)
			notes = getfields(bank.Notes, ' ')
			account=unalloc.id

			#process the special rules for this processor
			for r in bank.Rules:
				rule = eval(r)
				value = row[rule[0]]
				if value and re.compile(rule[1]).match(value):	#rule applies
					account = db(db.CoA.Name == rule[2]).select().first().id
			
			stored = stored + 1
			bank.update_record(Balance = (bank.Balance or 0) + amount + fee)

			if checknumber:		#see if there is an accrued and possibly split entry
				rows = db((db.AccTrans.Accrual==True)&(db.AccTrans.Bank==bank.id)&(db.AccTrans.CheckNumber==checknumber)).select()
				accrued=0
				for trans in rows: accrued+=trans.Amount
				if accrued==amount:
					for trans in rows:
						trans.update_record(Accrual=False, Timestamp=timestamp, Reference=reference)
					continue	#on to next transaction
			elif bank.Name=='Stripe':	#try to identify charges
				try:
					charge = stripe.Charge.retrieve(row[bank.Source])
					member = db(db.Members.Stripe_id==charge.customer).select().first()
					notes = f"{member_name(member.id)} {primary_email(member.id)}"
					if row[bank.Type]=='charge':
						if charge.description=='Subscription update' or (member.Charged and amount>=member.Charged):
							#dues paid, charge may also cover an event (auto renewal or manual)
							if (charge.description or '').startswith('Subscription'):
								customer = stripe.Customer.retrieve(charge.customer)
								notes += ' Subscription: '+ customer.subscriptions.data[0].id
								member.update_record(Stripe_next=datetime.datetime.fromtimestamp(customer.subscriptions.data[0].current_period_end).date())
							duesprice = stripe.Price.retrieve(eval(f'STRIPE_{member.Membership.upper()}'))
							duesamount = decimal.Decimal(duesprice.unit_amount)/100
							duesfee = (duesamount * fee)/amount	#prorate fee
							nowpaid = newpaiddate(member.Paiddate, timestamp=timestamp)
							db.Dues.insert(Member=member.id, Amount=duesamount, Date=timestamp.date(),
								Notes='Stripe', Prevpaid=member.Paiddate, Nowpaid=nowpaid, Status=member.Membership)
							member.update_record(Paiddate=nowpaid, Charged=None)
							db.AccTrans.insert(Bank = bank.id, Account = acdues.id, Amount = duesamount,
									Fee = duesfee, Accrual = False, Timestamp = timestamp,
									Reference = reference, Notes = notes)
							fee -= duesfee
							amount -= duesamount
						if amount==0:
							continue	#done with this row
							
						resvtn=db((db.Reservations.Member==member.id)&(db.Reservations.Charged>=amount)).select(
								orderby=db.Reservations.Modified).first()
						if resvtn:
							db.AccTrans.insert(Bank = bank.id, Account = actkts.id, Amount = amount, Fee = fee,
								Timestamp = timestamp, Event = resvtn.Event, Reference = reference, Accrual = False, Notes = notes)
							resvtn.update_record(Paid=(resvtn.Paid or 0) + amount, Charged = resvtn.Charged - amount, Checkout=None)
							continue
							
						#if paid reservation not found, store unallocated
				except Exception as e:
					pass	#if fails, leave unallocated
				
			db.AccTrans.insert(Bank = bank.id, Account = account, Amount = amount,
					Fee = fee if fee!=0 else None, Timestamp = timestamp,
					CheckNumber = checknumber, Reference = reference, Accrual = False, Notes = notes)
			if account==unalloc.id: unmatched += 1
								
		flash.set(f'{stored} new transactions processed, {unmatched} to allocate, new balance = ${bank.Balance}')
	except Exception as e:
		flash.set(f"{str(row)}: {str(e)}")
		isok = False
	if isok:
		redirect(URL('transactions', vars=dict(query=f'db.AccTrans.Bank=={bank.id}')))
	return locals()

@action('transactions', method=['POST', 'GET'])
@action('transactions/<path:path>', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('accounting')
def transactions(path=None):
	access = session['access']	#for layout.html
	db.AccTrans.Fee.writable = False

	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/accounts/transaction-list?authuser=1"

	back = URL('transactions/select', scheme=True)
	if not path:
		session['back'].append(session['url_prev'])
		session['url_prev'] = None	#no longer needed, save cookie space
		session['query'] = request.query.get('query')
		session['left'] = request.query.get('left')
	elif path=='select':
		back = session['back'][-1]
	elif path.startswith('edit') or path.startswith('details'):	#editing AccTrans record
		session['url'] = URL(f"transactions/{path}")	#strip off _referrer parameter to save cookie space
		db.AccTrans.Amount.comment = 'to split transaction, enter amount of a split piece'
		db.AccTrans.CheckNumber.writable = False
		db.AccTrans.CheckNumber.requires = None
		transaction = db.AccTrans[path[path.find('/')+1:]]
		if transaction.Accrual:
			db.AccTrans.Fee.readable = db.AccTrans.Fee.writable = False
			db.AccTrans.Timestamp.writable=True
		if transaction.Amount>0:
			db.AccTrans.Amount.requires=IS_DECIMAL_IN_RANGE(0, transaction.Amount)
		else:
			db.AccTrans.Amount.requires=IS_DECIMAL_IN_RANGE(transaction.Amount, 0)
	elif path=='new':	#adding AccTrans accrual
		db.AccTrans.Amount.comment='enter full amount of check as a negative number; split using Edit if multiple accounts',
		db.AccTrans.Timestamp.writable=True
		db.AccTrans.Amount.requires=IS_DECIMAL_IN_RANGE(-100000, 0)
		db.AccTrans.CheckNumber.requires=IS_NOT_EMPTY()
	session['url_prev'] = None	#no longer needed, save cookie space
	query = session['query']
	left = session['left']

	bank_id_match=re.match('db.AccTrans.Bank==([0-9]+)$', query)
	bank_id = int(bank_id_match.group(1)) if bank_id_match else None
	db.AccTrans.Bank.default = bank_id
	
	header = CAT(A('back', _href=back), H5('Accounting Transactions'))

	def validate(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if not form.vars.get('id'): #must be creating an accrual
			return
		new_amount = decimal.Decimal(form.vars.get('Amount'))
		fee = transaction.Fee
		if new_amount!=transaction.Amount:	#new split
			if transaction.Fee:
				fee = (transaction.Fee*new_amount/transaction.Amount).quantize(decimal.Decimal('0.01'))
			db.AccTrans.insert(Timestamp=transaction.Timestamp, Bank=transaction.Bank,
								Account=transaction.Account, Event=transaction.Event,
								Amount=transaction.Amount-new_amount, Fee=transaction.Fee - fee,
								CheckNumber=transaction.CheckNumber, Accrual=transaction.Accrual,
								 Reference=transaction.Reference,Notes=form.vars.get('Notes'))	#the residual piece
			db.AccTrans[form.vars.get('id')].update_record(Fee=fee)
			
	search_queries = [
		["Account", lambda value: db.AccTrans.Account.belongs([r.id for r in db(db.CoA.Name.ilike(f'%{value}%')).select(db.CoA.id)])],
		["Event", lambda value: db.AccTrans.Event.belongs([r.id for r in db(db.Events.Description.ilike(f'%{value}%')).select(db.Events.id)])],
		["Notes", lambda value: db.AccTrans.Notes.ilike(f'%{value}%')],
	]
	
	grid = Grid(path, eval(query), left=eval(left) if left else None,
			orderby=~db.AccTrans.Timestamp,
			columns=[db.AccTrans.Timestamp, db.AccTrans.Account, db.AccTrans.Event,
	 				db.AccTrans.Amount, db.AccTrans.Fee, db.AccTrans.CheckNumber, db.AccTrans.Accrual,
					db.AccTrans.Notes],
			headings=['Timestamp', 'Account','Event','Amt', 'Fee', 'Chk#', 'Acc', 'Notes'],
			validation=validate, search_queries=search_queries, show_id=True,
			deletable=lambda r: r.Accrual, details=False, editable=True, create=bank_id!=None,
			field_id=db.AccTrans.id, grid_class_style=grid_style, formstyle=form_style)
	return locals()

@action('composemail', method=['POST', 'GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess('write')
def composemail():
	access = session['access']	#for layout.html
	session['url']=session['url_prev']	#preserve back link

	_help = "https://sites.google.com/oxcamne.org/help-new/home/membership-database/members-page/send-email?authuser=1"
	
	query = request.query.get('query')
	qdesc = request.query.get('qdesc')
	left = request.query.get('left')

	header = CAT(A('back', _href=session['url_prev']), H5("Send Email"))
	source = society_emails(session['member_id'])

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
		header = CAT(header, XML(f'To: {qdesc}'))
		footer = A("Export bcc list for use in email", _href=URL('bcc_export',
						vars=dict(query=query, left=left or '')))
	else:
		fields.append(Field('to', 'string',
			comment='Include spaces between multiple recipients',
   			requires=[IS_NOT_EMPTY(), IS_LIST_OF_EMAILS()]))
	fields.append(Field('bcc', 'string', requires=IS_LIST_OF_EMAILS(), default=''))
	fields.append(Field('subject', 'string', requires=IS_NOT_EMPTY(), default=proto.Subject if proto else ''))
	fields.append(Field('body', 'text', requires=IS_NOT_EMPTY(), default=proto.Body if proto else "<Letterhead>\n<greeting>\n\n" if query else "<Letterhead>\n\n",
				comment=CAT("You can use placeholders <letterhead>, <subject>, <greeting>, <member>, <reservation>, <email>, ",
				"<support_email>, <society_domain>, <society_name>, or <home_url>, depending on the context. ",
				"You can also include html content thus: {{content}}. Email is formatted using ",
				A('Markmin', _href='http://www.web2py.com/examples/static/markmin.html', _target='Markmin'), '.')))
#'letterhead', 'society_domain', 'society_name', 'home_url', 'support_email'
	fields.append(Field('save', 'boolean', default=proto!=None, comment='store/update template'))
	#fields.append(Field('attachment', 'upload', uploadfield=False))
	if proto:
		form=''
		fields.append(Field('delete', 'boolean', comment='tick to delete template; sends no message'))
	form2 = Form(fields, form_name="message_form", keep_values=True,
					submit_value = 'Send', formstyle=FormStyleBulma)
			
	if form2.accepted:
		sender = f"{SOCIETY_NAME} <{form2.vars['sender']}>"
		if proto:
			if form2.vars['delete']:
				db(db.EMProtos.id == proto.id).delete()
				flash.set("Template deleted: "+ proto.Subject)
				redirect(session['url_prev'])
			if form2.vars['save']:
				proto.update_record(Subject=form2.vars['subject'],
					Body=form2.vars['body'])
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

#		if form2.vars.get('attachment'):
#			attachment = Mailer.Attachment(form2.vars.get('attachment').file,
#				  filename=form2.vars.get('attachment').filename)

		if bodyparts:
			if query:
				db.emailqueue.insert(subject=form2.vars['subject'], bodyparts=str(bodyparts), sender=sender,
			 		bcc=bcc, query=query, left=left, qdesc=qdesc,
					scheme=URL('index', scheme=True).replace('index', ''))
				flash.set(f"email notice sent to '{qdesc}'")
			else:
				to = re.compile('[^,;\s]+').findall(form2.vars['to'])
				body = ''
				for part in bodyparts:
					body += part[0]		
				flash.set(f"Email sent to: {to}")
				auth.sender.send(to=to, sender=sender, reply_to=sender, 
		     		subject=form2.vars['subject'], bcc=bcc, body=HTML(XML(body)))
			redirect(session['url_prev'])
	return locals()

@action('bcc_export', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def bcc_export():
	stream = StringIO()
	content_type = "text/plain"
	filename = 'bcc.txt'
	query = request.query.get('query')
	mailing_list = 'Mailings.contains'in query
	left = request.query.get('left') or "db.Emails.on(db.Emails.Member==db.Members.id)"
	rows = db(eval(query)).select(db.Members.id, db.Emails.Email, left=eval(left) if left else None,
			       orderby=db.Members.id|~db.Emails.Modified, distinct=True)
	try:
		writer=csv.writer(stream)
		for row in rows:
			email = row.get(db.Emails.Email) or primary_email(row.get(db.Members.id))
			if email:
				writer.writerow([email])
	except Exception as e:
		flash.set(e)
		redirect(session['url_prev'])
	return locals()

#######################Member Directory linked from Society web site#########################
@action('directory', method=['GET'])
@action('directory/<path:path>', method=['GET'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def directory(path=None):
	access = session['access']	#for layout.html
	if not session['member_id'] or not member_good_standing(db.Members[session['member_id']]):
		session.flash = 'Sorry, Member Directory is only available to members in good standing.'
		redirect(URL('index'))
			
	query = "(db.Members.Membership!=None)&(db.Members.Membership!='')"
	header = CAT(H5('Member Directory'),
	      XML(f"You can search by last name, town, state, or college/university using the boxes below; click on a name to view contact information"))

	grid = Grid(path, eval(query),
		columns=(Column('Name', lambda r: A(f"{member_name(r['id'])}", _href=URL(f"contact_details/{r['id']}"))),
	   			Column('Affiliations', lambda r: member_affiliations(r['id'])),
				db.Members.City, db.Members.State),
		orderby=db.Members.Lastname|db.Members.Firstname,
		search_queries=[["Last Name", lambda value: db.Members.Lastname.ilike(f'%{value}%')],
						["Town", lambda value: db.Members.City.ilike(f'%{value}%')],
						["State ('xx')", lambda value: db.Members.State.ilike(f'%{value}%')],
						["College/University", lambda value: db.Members.id.belongs([a.Member for a in db(db.Affiliations.College.belongs([c.id for c in db(db.Colleges.Name.ilike(f"%{value}%")).select()])).select()])]],
		details=False, editable=False, create=False, deletable=False,
		show_id=True,
		grid_class_style=grid_style,
		formstyle=form_style)
	return locals()
	
@action('contact_details/<member_id:int>', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess(None)
def contact_details(member_id):
	access = session['access']	#for layout.html
	member=db.Members[member_id] if session['member_id'] else None
	if not member or not member.Membership:
		raise Exception("hack attempt?")
	
	message = CAT(A('back', _href=session['url_prev']),
				H5("Member Directory - Contact Details"),
	       member_name(member_id), XML('<br>'),
		   member_affiliations(member_id), XML('<br>'))
	email = primary_email(member_id)
	if not member.Privacy and email:
		message = CAT(message, A(email, _href=f"mailto:{email}",_target='email'), XML('<br>'))
	if member.Homephone:
		message = CAT(message, f"home phone: {member.Homephone}", XML('<br>'))
	if member.Workphone:
		message = CAT(message, f"work phone: {member.Workphone}", XML('<br>'))
	message = CAT(message, XML('<br>'))

	if member.Address1:
		message = CAT(message, f"{member.Address1}", XML('<br>'))
	if member.Address2:
		message = CAT(message, f"{member.Address2}", XML('<br>'))
	message = CAT(message, f"{member.City or ''}, {member.State or ''} {member.Zip or ''}")
	return locals()

################################# New Event/Membership Registration Process  ################################
@action('registration', method=['GET', 'POST'])
@action('registration/<event_id:int>', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def registration(event_id=None):	#deal with eligibility, set up member record and affiliation record as necessary
#used for both event booking and join/renewal
	access = session['access']	#for layout.html
	db.Members.Created.default = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	db.Reservations.Created.default = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	if event_id:
		event = db(db.Events.id==event_id).select().first()
		if not event or datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.DateTime or (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.Booking_Closed and not event_attend(event_id)):
			flash.set('Event is not open for booking.')
			redirect(URL('index'))
		if datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.Booking_Closed:
			flash.set('Booking is closed, but you may join the wait list.')
		session['event_id'] = event_id
		session['membership'] = None	#gets set if membership dues to be collected
		session['dues'] = None
	else:
		event = None
		if not request.query.get('join_or_renew'):
			session['event_id'] = None
			session['membership'] = None
			session['dues'] = None
			
	affinity = None
	clist = collegelist(event.Sponsors if event_id and event.Sponsors else [])
	member_id = session.get('member_id')
	
	if member_id:
		member = db.Members[member_id]
		affinity = db((db.Affiliations.Member==member_id)&db.Affiliations.College.belongs([c[0] for c in clist])).select(
							orderby=db.Affiliations.Modified).first()
		if affinity:
			clist = [(affinity.College, affinity.College.Name)]	#primary affiliation is only choice
		if event_id:	#event reservation
			member_reservation = db((db.Reservations.Event == event_id) & (db.Reservations.Member==member_id)\
										& (db.Reservations.Host==True)).select().first()
			sponsor = not affinity.College.Oxbridge if affinity else False
			if member_reservation:
				if member_reservation.Checkout:	#checked out but didn't complete payment
					checkout = eval(member_reservation.Checkout)
					if not member_good_standing(member, event.DateTime.date()):
						#still need dues, so signal
						session['membership'] = checkout.get('membership')
						session['dues'] = str(checkout.get('dues')) if checkout.get('dues') else None
				redirect(URL(f'reservation/Y/{member_id}/{event_id}/'))	#go add guests and/or checkout
			if member_good_standing(member, event.DateTime.date()) or sponsor \
					or ((affinity or member.Membership)and not event.Members_only):
				#members in good standing at time of event, or, members of sponsor organizations, or
				#membership-eligible and event open to all alums then no need to gather member information
				redirect(URL(f'reservation/Y/{member_id}/{event_id}/new'))	#go create this member's reservation

		elif request.query.get('mail_lists'):
			session['url'] = URL('index')
			redirect(URL(f"emails/Y/{member_id}"))
		else:		#dues payment or profile update
			if not session.get('membership') and \
					member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)+datetime.timedelta(days=GRACE_PERIOD)).date()):
				redirect(URL('profile')) #edit profile if good standing for at least grace period
			if member.Stripe_subscription == 'Cancelled':
				member.update_record(Stripe_subscription = None, Stripe_next = None)
	else:
		member = None
		
	header = H5('Event Registration: Your Information' if event 
				else 'Mailing List Registration' if request.query.get('mail_lists')
				else 'Membership Application/Renewal: Your Information')
	if event:
		header = CAT(header, XML(f"Event: {event.Description}<br>When: {event.DateTime.strftime('%A %B %d, %Y %I:%M%p')}<br>Where: {event.Venue}<br><br>\
	This event is open to {'all alumni of Oxford & Cambridge' if not event.Members_only else 'members of '+SOCIETY_DOMAIN}\
	{' and members of sponsoring organizations (list at the top of the Affiliations dropdown)' if event.Sponsors else ''}\
	{' and their guests.' if not event.Guests or event.Guests>1 else ''}.<br>"))
	elif not request.query.get('mail_lists'):
		header = CAT(header, XML(MEMBERSHIP))
		
	#gather the person's information as necessary (may have only email)
	fields=[]
	fields.append(Field('firstname', 'string', requires = IS_NOT_EMPTY(),
					default=member.Firstname if member else ''))
	fields.append(Field('lastname', 'string', requires = IS_NOT_EMPTY(),
					default=member.Lastname if member else ''))
	fields.append(Field('affiliation', 'reference Colleges',
			default=affinity.College if affinity else None, 
			requires=IS_IN_SET(clist, zero=None) if affinity else IS_EMPTY_OR(IS_IN_SET(clist,
						zero = 'Please select your sponsoring organization or College/University' if event and event.Sponsors else \
								'Please select your College' if not member or not member.Membership else ''))))
	if not affinity or not affinity.Matr:
		fields.append(Field('matr', 'integer', default = affinity.Matr if affinity else None,
				requires=IS_EMPTY_OR(IS_INT_IN_RANGE(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year-100,datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year+1)),
				comment='Please enter your matriculation year, not graduation year'))

	if event:
		mustjoin = event.Members_only and not event.Sponsors
		if event.Members_only or event.Allow_join:
			fields.append(Field('join_or_renew', 'boolean', default=mustjoin,
				comment=' this event is restricted to OxCamNE members' if mustjoin else \
					' tick if you are an Oxbridge alum and also wish to join OxCamNE or renew your membership'))
	elif not request.query.get('mail_lists'):
		fields.append(Field('membership', 'string',
						default=member.Membership if member and member.Membership else '',
						requires=IS_IN_SET(MEMBER_CATEGORIES, zero='please select your membership category')))
		fields.append(Field('notes', 'string'))
						
	def validate(form):
		if form.vars.get('affiliation') and not db.Colleges[form.vars.get('affiliation')].Oxbridge: #sponsor member
			if form.vars.get('join_or_renew'):
				form.errors['join_or_renew']="You're not eligible to join "+SOCIETY_DOMAIN+'!'
			return	#go ahead with sponsor registration
		if not form.vars.get('affiliation') and not (member and member.Membership): #not alum, not approved friend member
			form.errors['affiliation']='please select your affiliation from the dropdown, or contact '+SUPPORT_EMAIL
		if form.vars.get('affiliation') and (not affinity or not affinity.Matr) and not form.vars.get('matr'):
			form.errors['matr'] = 'please enter your matriculation year'
		if event and event.Members_only and not form.vars.get('join_or_renew'):
			form.errors['join_or_renew'] = 'This event is for members only, please join/renew to attend'
		if not event and not request.query.get('mail_lists') and form.vars.get('membership')!=MEMBER_CATEGORIES[0]:
			if not form.vars.get('notes'):
				form.errors['notes'] = 'Please note how you qualify for '+form.vars.get('membership')+' status'
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
	
	form = Form(fields, validation=validate, formstyle=FormStyleBulma, keep_values=True)
		
	if form.accepted:
		if member:
			notes = f"{datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).strftime('%m/%d/%y')} {form.vars.get('notes')}"
			if member.Notes:
				notes = member.Notes+'\n'+notes
				
			member.update_record(Firstname = form.vars['firstname'], Notes=notes,
							Lastname = form.vars['lastname'])
		else:
			member_id = db.Members.insert(Firstname = form.vars['firstname'], 
										Lastname = form.vars['lastname'])
			member = db.Members[member_id]
			session['member_id'] = member_id
			if request.query.get('mail_lists'):
				db.Emails.Mailings.default = [list.id for list in db(db.Email_Lists.Member==True).select()]
			email_id = db.Emails.insert(Member=member_id, Email=session.get('email'))

		if form.vars.get('affiliation'):
			if affinity:
				if form.vars.get('matr'):
					affinity.update_record(Matr=form.vars.get('matr'), Modified=affinity.Modified)	#note, preserve Modified, keep as primary affiliation
			else:
				db(db.Affiliations.Member==member_id).delete()	#delete any stray sponsor affiliation.
				db.Affiliations.insert(Member = member_id, College = form.vars['affiliation'],
										Matr = form.vars.get('matr'))

		if event and form.vars.get('join_or_renew'):
			flash.set("Please complete your membership application, then you'll return to event registration")
			redirect(URL('registration', vars=dict(join_or_renew='Y')))	#go deal with membership
			
		if (request.query.get('mail_lists')):
			session['url'] = URL('index')
			flash.set("Please review your subscription settings below.")
			redirect(URL(f"emails/Y/{member_id}/edit/{email_id}"))
				
		if request.query.get('join_or_renew') or not event:	#collecting dues with event registration, or joining/renewing
			#membership dues payment
			#get the subscription plan id (Full membership) or 1-year price (Student) from Stripe Products
			stripe.api_key = STRIPE_SKEY
			price_id = eval(f"STRIPE_{form.vars.get('membership')}".upper())
			price = stripe.Price.retrieve(price_id)
			session['membership'] = form.vars.get('membership')
			session['dues'] = str(decimal.Decimal(price.unit_amount)/100)
			session['subscription'] = True if price.recurring else False
			#ensure the default mailing list subscriptions are in place in the primary email
			email = db(db.Emails.Member==member.id).select(orderby=~db.Emails.Modified).first()
			mailings = email.Mailings or []
			for list in db(db.Email_Lists.Member==True).select():
				if list.id not in mailings:
					mailings.append(list.id)
			email.update_record(Mailings=mailings)
		
		if event:
			redirect(URL(f'reservation/Y/{member_id}/{event_id}/new'))	#go create this member's reservation
		else:	#joining or renewing
			if not member.Paiddate or member.Paiddate < (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)-datetime.timedelta(GRACE_PERIOD)).date():
				#new/reinstated member, gather additional profile information
				flash.set("Next, please review/complete your directory profile")
				redirect(URL('profile')) #gather profile info
			if session.vars.get('event_id'):
				redirect(URL(f'reservation/Y/{member_id}/{event_id}/new'))	#go create this member's reservation
			redirect(URL('checkout'))
	return locals()
	
######################################## Join/Renew/Profile Update ######################################
@action('profile', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def profile():
	access = session['access']	#for layout.html
	if not session.get('member_id'):
		redirect(URL('index'))

	
	member = db.Members[session.get('member_id')]

	header = H5('Profile Information')
	if member.Paiddate:
		header = CAT(header,
	       XML(f"Your membership {'expired' if member.Paiddate < datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date() else 'expires'} on {member.Paiddate.strftime('%m/%d/%Y')}"))
	if member.Stripe_next:
		header = CAT(header, XML(f" Renewal payment will be charged on {member.Stripe_next.strftime('%m/%d/%Y')}."))
	header = CAT(header,
	      XML(f"{'<br><br>' if member.Paiddate else ''}The information on this form, except as noted, is included \
in our online Member Directory which is available through our home page to \
all members in good standing. Fields marked * are required.<br><br>\
You can use this screen at any time to update your information (it can be \
reached by using the join/renew link on our home page).<br>\
{A('Review or Edit your college affiliation(s)', _href=URL(f'affiliations/Y/{member.id}'))}<br>\
{A('Manage your email address(es) and mailing list subscriptions', _href=URL(f'emails/Y/{member.id}'))}<br>"))
	
	db.Members.Membership.readable = db.Members.Paiddate.readable = db.Members.Stripe_id.readable = False
	db.Members.Stripe_subscription.readable = db.Members.Stripe_next.readable = db.Members.Charged.readable = False
	db.Members.Access.readable = db.Members.Committees.readable = db.Members.President.readable = False
	db.Members.Notes.readable = db.Members.Created.readable = db.Members.Modified.readable = False
	db.Members.Membership.writable = db.Members.Paiddate.writable = db.Members.Stripe_id.writable = False
	db.Members.Stripe_subscription.writable = db.Members.Stripe_next.writable = db.Members.Charged.writable = False
	db.Members.Access.writable = db.Members.Committees.writable = db.Members.President.writable = False
	db.Members.Notes.writable = db.Members.Created.writable = db.Members.Modified.writable = False

	def validate(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	form = Form(db.Members, record=member, show_id=False, deletable=False,
	     			validation=validate, formstyle=FormStyleBulma, keep_values=True)
					
	if form.accepted:
		#ready to checkout
		if session.get('dues'):
			if session.get('event_id'):
				redirect(URL(f"reservation/Y/{member.id}/{session['event_id']}/new"))	#go create this member's reservation
			redirect(URL('checkout'))
		flash.set('Thank you for updating your profile information.')
		notify_support(member, 'Member Profile Updated', member_profile(member))
	
	return locals()
	
@action('stripe_update_card', method=['GET'])
@action.uses("checkout.html", session)
@checkaccess(None)
def stripe_update_card():
	access = session['access']	#for layout.html
	stripe_session_id = request.query.get('stripe_session_id')
	stripe_pkey = STRIPE_PKEY
	return locals()
	
@action('stripe_switched_card', method=['GET'])
@action.uses("checkout.html", session, db, flash)
@checkaccess(None)
def stripe_switched_card():
	access = session['access']	#for layout.html
	stripe.api_key = STRIPE_SKEY
	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]

	stripe_session = stripe.checkout.Session.retrieve(session['stripe_session_id'], expand=['setup_intent'])
	stripe.Customer.modify(member.Stripe_id,
				invoice_settings={'default_payment_method': stripe_session.setup_intent.payment_method})
	stripe.Subscription.modify(member.Stripe_subscription,
				default_payment_method=stripe_session.setup_intent.payment_method)
	flash.set('Thank you for updating your credit card information!')
	notify_support(member, 'Credit Card Update', 'Credit card updated.')
	redirect(URL('update_card'))

@action('update_card', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def update_card():
	access = session['access']	#for layout.html
	stripe.api_key = STRIPE_SKEY

	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]
	
	if member.Stripe_subscription and member.Stripe_subscription!='Cancelled':
		try:	#check subscription still exists on Stripe
			subscription = stripe.Subscription.retrieve(member.Stripe_subscription)
		except Exception as e:
			member.update_record(Stripe_subscription=None, Stripe_next=None)
	if not (member.Stripe_subscription and member.Stripe_subscription!='Cancelled'):
		redirect(URL('index'))	#Stripe subscription doesn't exist
		
	paymentmethod = stripe.PaymentMethod.retrieve(subscription.default_payment_method)
	renewaldate = member.Stripe_next.strftime('%b %d, %Y')
	duesamount = decimal.Decimal(subscription.plan.amount)/100
	header = CAT(H5('Membership Subscription'),
	      XML(f"Your next renewal payment of ${duesamount} will be charged to {paymentmethod.card.brand.capitalize()} \
....{paymentmethod.card.last4} exp {paymentmethod.card.exp_month}/{paymentmethod.card.exp_year} on {renewaldate}.<br><br>"))
	
	form = Form([], submit_value='Update Card on File')

	if form.accepted:
		stripe_session = stripe.checkout.Session.create(
		  payment_method_types=['card'],
		  mode='setup',
		  customer=member.Stripe_id,
		  setup_intent_data={},
		  success_url=URL('stripe_switched_card', scheme=True),
		  cancel_url=URL('index', scheme=True)
		)
		session['stripe_session_id'] = stripe_session.stripe_id
		redirect(URL('stripe_update_card', vars=dict(stripe_session_id=stripe_session.id)))
	return locals()
	
@action('cancel_subscription', method=['GET', 'POST'])
@action.uses("gridform.html", db, session, flash)
@checkaccess(None)
def cancel_subscription():
	access = session['access']	#for layout.html
	stripe.api_key = STRIPE_SKEY
	
	if not session.get('member_id'):
		redirect(URL('index'))
	member = db.Members[session['member_id']]
	if not (member and member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)-datetime.timedelta(days=45)).date())):
		raise Exception("perhaps Back button or mobile auto re-request?")
	
	header = CAT(H5('Membership Cancellation'),
	      XML(f"We are very sorry to lose you as a member. If you must leave, please click the button to confirm!.<br><br>"))
	
	form = Form([], submit_value='Cancel Subscription')
	
	if form.accepted:
		if member.Stripe_subscription:	#delete Stripe subscription if applicable
			try:
				stripe.Subscription.delete(member.Stripe_subscription)
			except Exception as e:
				pass
		
		member.update_record(Stripe_subscription = 'Cancelled', Stripe_next=None)
		#if we simply cleared Stripe_subscription then the daily backup daemon might issue membership reminders!
		if not member.Paiddate:	#just joined but changed their mind?
			member.update_record(Membership=None, Charged=None)

		effective = max(member.Paiddate or datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date(), datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()).strftime('%m/%d/%Y')
		notification(member, 'Membership Cancelled', f'Your membership is cancelled effective {effective}.')
		flash.set(f'Your membership is cancelled effective {effective}.')
		redirect(URL('index'))
	return locals()

@action('checkout', method=['GET'])
@action.uses("checkout.html", db, session, flash)
@checkaccess(None)
def checkout():
	access = session['access']	#for layout.html
	if (not session.get('membership') and not session.get('event_id')) or not session.get('member_id'):
		redirect(URL('index'))	#protect against regurgitated old requests
		
	pk = STRIPE_PKEY	#use the public key on the client side	
	stripe.api_key = STRIPE_SKEY

	member = db.Members[session.get('member_id')]
	if member.Stripe_id:	#check customer still exists on Stripe
		try:
			customer = stripe.Customer.retrieve(member.Stripe_id)
		except Exception as e:
			member.update_record(Stripe_id=None, Stripe_subscription=None)
	
	mode = 'payment'
	items = []
	params = {}	#for checkout_success
	event = None
	
	if member.Stripe_id:
		stripe.Customer.modify(member.Stripe_id, email=primary_email(member.id))	#in case has changed
	else:
		customer = stripe.Customer.create(email=primary_email(member.id))
		member.update_record(Stripe_id=customer.id)
	
	if session.get('membership'):	#this includes a membership subscription
		#get the subscription plan id (Full membership) or 1-year price (Student) from Stripe Products
		price_id = eval(f"STRIPE_{session.get('membership')}".upper())
		price = stripe.Price.retrieve(price_id)
		params['dues'] = session.get('dues')
		params['membership'] = session.get('membership')
		if price.recurring:
			mode = 'subscription'
		items.append(dict(price = price_id, quantity = 1))
		
	if session.get('event_id'):			#event registration
		event = db.Events[session.get('event_id')]
		tickets_tbc = res_tbc(member.id, event.id)
		if tickets_tbc:
			params['event_id'] = event.id
			params['tickets_tbc'] = tickets_tbc
			items.append(dict(price_data = dict(currency='usd', unit_amount=int(tickets_tbc*100),
						product=STRIPE_EVENT), description = event.Description, quantity=1))
		 
	stripe_session = stripe.checkout.Session.create(
	  customer=member.Stripe_id,
	  payment_method_types=['card'], line_items=items, mode=mode,
	  success_url=URL('checkout_success', vars=params, scheme=True),
	  cancel_url=session.get('url_prev')
	)
	stripe_session_id = stripe_session.stripe_id		#for use in template
	session['stripe_session_id'] = stripe_session.stripe_id
	stripe_pkey = STRIPE_PKEY
	return locals()

@action('checkout_success', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess(None)
def checkout_success():
	member = db.Members[session.get('member_id')]
	dues = decimal.Decimal(request.query.get('dues') or 0)
	tickets_tbc = decimal.Decimal(request.query.get('tickets_tbc') or 0)
	stripe.api_key = STRIPE_SKEY
	stripe_session = stripe.checkout.Session.retrieve(session.get('stripe_session_id'))

	if not stripe_session or decimal.Decimal(stripe_session.amount_total)/100 != tickets_tbc + dues:
		raise Exception(f"Unexpected checkout_success callback received from Stripe, member {member.id}, event {session.get('event_id')}")
		redirect(URL('index'))

	subject = 'Registration Confirmation' if tickets_tbc>0 else 'Thank you for your membership payment'
	message = f"{msg_header(member, subject)}<br><b>Received: ${dues+tickets_tbc}</b><br>"
	
	if dues:
		next = None
		if stripe_session.subscription:
			subscription = stripe.Subscription.retrieve(stripe_session.subscription)
			next = datetime.datetime.fromtimestamp(subscription.current_period_end).date()
		member.update_record(Membership=request.query.get('membership'),
			Stripe_subscription=stripe_session.subscription, Stripe_next=next, Charged=dues)
		message += 'Thank you, your membership is now current.</b><br>'
		
	if tickets_tbc:
		host_reservation = db((db.Reservations.Event==request.query.get('event_id'))&(db.Reservations.Member == member.id)\
					&(db.Reservations.Host == True)).select().first()
		message += '<br><b>Your registration is now confirmed:</b><br>'
		message +=event_confirm(request.query.get('event_id'), member.id, dues+tickets_tbc)
		host_reservation.update_record(Charged = (host_reservation.Charged or 0) + tickets_tbc, Checkout = None)

	msg_send(member,subject, message)
	
	flash.set('Thank you for your payment. Confirmation has been sent by email!')
	session['membership'] = None
	session['dues'] = None
	session['event_id'] = None
	session['stripe_session_id'] = None
	if dues:
		flash.set('Confirmation has been sent by email. Please review your mailing list subscriptions.')
		session['url'] = URL('index')
		redirect(URL(f"emails/Y/{member.id}/select"))
		#it would be nice to go right to edit the subscription of the primary email,
		#but a side effect of Stripe Checkout seems to be that the first 'submit' doesn't work
		#I think this is CSRF protection at work.
		#redirect(URL(f"emails/Y/{member.id}/edit/{db(db.Emails.Member == member.id).select(orderby=~db.Emails.Modified).first().id}"))
	redirect(URL('index'))
