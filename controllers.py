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
from py4web.utils.grid import Grid, GridClassStyleBulma, Column
from py4web.utils.form import Form, FormStyleBulma

grid_style = GridClassStyleBulma
form_style = FormStyleBulma

from py4web import action, request, response, redirect, URL, Field, HTTP, abort
from yatl.helpers import H5, H6, XML, TABLE, TH, TD, THEAD, TR, HTML, P, BUTTON, INPUT
from .common import db, session, flash
from .settings import SOCIETY_SHORT_NAME, SUPPORT_EMAIL, GRACE_PERIOD,\
	MEMBERSHIPS, TIME_ZONE, PAGE_BANNER, IS_PRODUCTION,\
	ALLOWED_EMAILS, DATE_FORMAT, CURRENCY_SYMBOL, SMTP_TRANS
from .pay_processors import paymentprocessor
from .models import ACCESS_LEVELS, CAT, A, event_attend, event_wait, member_name,\
	member_affiliations, member_emails, primary_affiliation, primary_email,\
	primary_matriculation, event_revenue, event_unpaid, page_name,\
	res_conf, event_cost, res_wait, res_prov, bank_accrual, tickets_sold,\
	res_unitcost, res_selection, event_paid_dict, event_ticket_dict, collegelist,\
	event_checked_in, res_checked_in
from pydal.validators import IS_LIST_OF_EMAILS, IS_EMPTY_OR, IS_IN_DB, IS_IN_SET,\
	IS_NOT_EMPTY, IS_DATE, IS_DECIMAL_IN_RANGE, IS_INT_IN_RANGE, IS_MATCH, CLEANUP
from .utilities import email_sender, member_good_standing, ageband, newpaiddate,\
	tdnum, get_banks, financial_content, event_confirm, msg_header, msg_send,\
	notification, notify_support, member_profile, generate_hash,\
	encode_url, pages_menu, template_expand
from .session import checkaccess
from .website import society_emails, about_content, history_content, upcoming_events
from py4web.utils.factories import Inject
import datetime, re, csv, decimal, pickle, markdown, dateutil
from io import StringIO

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER))
preferred_public = action.uses("gridform_public.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER))

@action('index')
@preferred
def index():
	if db(db.Pages.Page=='Home').count() > 0:
		redirect(URL('web/home'))
	redirect(URL('my_account'))

@action('my_account')
@preferred
@checkaccess(None)
def my_account():
	header = H6("Please select one of the following:")
	member = db.Members[session.member_id] if session.member_id else None
	access = session.access	#for layout.html

	if len(MEMBERSHIPS)>0 and (not member or not member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)+datetime.timedelta(days=GRACE_PERIOD)).date())):
		header = CAT(header, A("Join or Renew your Membership", _href=URL('registration')), XML('<br>'))
		# allow renewal once within GRACE_PERIOD of expiration.
	else:
		header = CAT(header, A("Update your member profile or contact information", _href=URL('registration')), XML('<br>'))

	if member:
		header = CAT(header, A("Update your email address and/or mailing list subscriptions",
				_href=URL(f"emails/Y/{session.member_id}",
				vars=dict(back=request.url))), XML('<br>'))
	else:
		header = CAT(header, A("Join our mailing list(s)", _href=URL("registration", vars=dict(mail_lists='Y'))), XML('<br>'))

	if member and member.Pay_subs!='Cancelled' and member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)-datetime.timedelta(days=GRACE_PERIOD)).date()):
		#the GRACE_PERIOD check means that a member without a subscription can cancel after expiration to turn of the nagging reminders.
		if member.Pay_subs:
			header = CAT(header, A("View membership subscription/Update credit card", _href=URL(f'{member.Pay_source}_view_card')), XML('<br>'))
		header = CAT(header, A("Cancel your membership",
						 _href=URL(f'cancel_subscription/{member.id}', vars=dict(back=request.url))), XML('<br>'))

	header = CAT(header, 
			H6(XML(f"To register for/view events use links below:")),
			upcoming_events())
	return locals()

@action('view_card')
@preferred
@checkaccess(None)
def view_card():
	if not session.Pay_source:
		redirect(URL('my_account'))
	paymentprocessor().view_card

@action('members', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def members():
	access = session.access	#for layout.html
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.url
	query = []
	left = None #only used if mailing list with excluded event attendees
	qdesc = ""
	errors = ''
	header = H5('Member Records')

	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	admin = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('admin')
	if not admin:
		db.Members.Access.writable = False
	search_form=Form([
		Field('mailing_list', 'reference Email_Lists', default = request.query.get('mailing_list'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Email_Lists', '%(Listname)s', zero="mailing?"))),
		Field('event', 'reference Events',  default = request.query.get('event'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Events',
				lambda r: f"{r.DateTime.strftime(DATE_FORMAT)} {r.Description[:25]}",
				orderby = ~db.Events.DateTime, zero="event?")),
				comment = "exclude/select confirmed event registrants (with/without mailing list selection) "),
		Field('good_standing', 'boolean',  default = request.query.get('good_standing'),
				comment='tick to limit to members in good standing'),
		Field('field', 'string', default = request.query.get('field'),
				requires=IS_EMPTY_OR(IS_IN_SET(['Affiliation', 'Email']+db.Members.fields,
								zero='field?'))),
		Field('value', 'string', default = request.query.get('value'))],
		keep_values=True, formstyle=FormStyleBulma)
	
	if parsed['mode'] == 'select':
		header = CAT(header, A("Send Email to Specific Address(es)",
						_href=URL('composemail', vars=dict(back=back))), XML('<br>'))
		
		if search_form.accepted:	#Filter button clicked
			select_vars = {}
			if search_form.vars.get('mailing_list'):
				select_vars['mailing_list'] = search_form.vars.get('mailing_list')
			if search_form.vars.get('event'):
				select_vars['event'] = search_form.vars.get('event')
			if search_form.vars.get('good_standing'):
				select_vars['good_standing'] = 'On'
			if search_form.vars.get('field'):
				select_vars['field'] = search_form.vars.get('field')
			if search_form.vars.get('value'):
				select_vars['value'] = search_form.vars.get('value')
			redirect(URL('members', vars=select_vars))
	else:
		header = CAT(A('back', _href=back), H5('Member Record'))
		if parsed['mode']=='edit' or parsed['mode']=='details':
			acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first().id
			member_id = request.query.get('id')
			member = db.Members[member_id]
			header= CAT(header, 
		   			A('Member reservations', _href=URL(f'member_reservations/{member_id}',
								vars=dict(back=request.url))), XML('<br>'),
					A('OxCam affiliation(s)', _href=URL(f'affiliations/N/{member_id}',
								vars=dict(back=request.url))), XML('<br>'),
					A('Email addresses and subscriptions', _href=URL(f'emails/N/{member_id}',
								vars=dict(back=request.url))), XML('<br>'),
					A('Dues payments', _href=URL('transactions', vars=dict(
						query=f"(db.AccTrans.Account=={acdues})&(db.AccTrans.Member=={member_id})",
						back=request.url))), XML('<br>'),
					A('Send Email to Member', _href=URL('composemail',
					 	vars=dict(query=f"db.Members.id=={member_id}", qdesc=member_name(member_id),
				 					back=request.url))))
			
			if member_good_standing(member, datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()):
				header = CAT(header, XML('<br>'), A('Cancel Membership',
						_href=URL(f"cancel_subscription/{member_id}", vars=dict(back=request.url))))

	if request.query.get('mailing_list'):
		query.append(f"(db.Members.id==db.Emails.Member)&db.Emails.Mailings.contains({request.query.get('mailing_list')})")
		qdesc = f"{db.Email_Lists[request.query.get('mailing_list')].Listname} mail list, "
	if request.query.get('event'):
		if request.query.get('mailing_list'):
			left=f"db.Reservations.on((db.Reservations.Member == db.Members.id)&(db.Reservations.Event=={request.query.get('event')})&(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&(db.Reservations.Waitlist!=True))"
			query.append("(db.Reservations.id==None)")
		else:
			query.append(f"(db.Members.id==db.Reservations.Member)&(db.Reservations.Event=={request.query.get('event')})&(db.Reservations.Host==True)&(db.Reservations.Provisional!=True)&(db.Reservations.Waitlist!=True)")
		qdesc += f"{'excluding ' if request.query.get('mailing_list') else ''}{db.Events[request.query.get('event')].Description[0:25]} attendees, "
	if request.query.get('good_standing'):
		query.append("((db.Members.Membership!=None)&(((db.Members.Paiddate==None)|(db.Members.Paiddate>=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()))|(db.Members.Charged!=None)|((db.Members.Pay_subs!=None)&(db.Members.Pay_subs!=('Cancelled')))))")
		qdesc += ' in good standing, '
	if request.query.get('value'):
		field = request.query.get('field')
		value = request.query.get('value')
		if not request.query.get('field'):
			errors = 'Please specify which field to search'
		elif field == 'Affiliation':
			query.append(f'(db.Colleges.Name.ilike("%{value}%")&(db.Affiliations.College==db.Colleges.id)&(db.Members.id==db.Affiliations.Member))')
			qdesc += f" with affiliation matching '{value}'."
		elif field == 'Email':
			query.append(f"(db.Members.id==db.Emails.Member)&db.Emails.Email.ilike('%{value}%')")
			qdesc += f" with email matching '{value}'."
		else:
			fieldtype = eval("db.Members."+field+'.type')
			m = re.match(r"^([\!<>]?=?)\s*(.*)$", value, flags=re.DOTALL)
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
					query.append(f'(db.Members.{field}{operator}"{value}")')
					qdesc += f' {field} {operator} {value}.'
			elif fieldtype == 'date' or fieldtype == 'datetime':
				try:
					date = datetime.datetime.strptime(value, DATE_FORMAT).date()
				except:
					errors = f'please use {DATE_FORMAT} format for dates'
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
	
	if parsed['mode'] == 'select':	
		if qdesc:
			header = CAT(header,
				A(f"Send Notice to {qdesc}", _href=URL('composemail',
					vars=dict(query=query, left=left or '', qdesc=qdesc,
			   		event_details=request.query.get('event') or '' if request.query.get('mailing_list') else '',
					back=back))), XML('<br>'))
		header = CAT(header,
		   XML(f"Use filter to select a <a href={URL('email_lists')}>\
mailing list</a> or apply other filters.<br>Selecting an event selects attendees; \
selecting an event AND a mailing list selects the mailing list less attendees \
AND includes the event Details in email notices.<br>\
You can filter on a member record field \
using an optional operator (=, !=, <, >, <=, >=) together with a value."))
		footer = CAT(A("View Recent New Members", _href=URL('new_members', vars={'back': request.url})), XML('<br>'),
			A("Export Membership Analytics", _href=URL('member_analytics')), XML('<br>'),
			A("Export Selected Records", _href=URL('members_export',
						vars=dict(query=query, left=left or '', qdesc=qdesc))))

	def member_deletable(id): #deletable if not member, never paid dues or attended recorded event, or on mailing list
		m = db.Members[id]
		emails = db(db.Emails.Member == id).select()
		ifmailings = False
		for em in emails:
			if em.Mailings and len(em.Mailings) > 0: ifmailings = True
		return not m.Membership and not m.Paiddate and not m.Access and \
				not ifmailings and db(db.AccTrans.Member == id).count()==0 and \
				db(db.AccTrans.Member == id).count()==0 and \
				db(db.Reservations.Member == id).count()==0 and not m.President

	def validate(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if not form.vars.get('id'):
			return	#adding record
		
	grid = Grid(eval(query), left=eval(left) if left else None,
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
			deletable=lambda r: write and member_deletable(r['id'])
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
	return locals()	

@action('member_analytics', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def member_analytics():
	stream=StringIO()
	content_type = "text/csv"
	filename = 'member_analytics.csv'
	writer=csv.writer(stream)
	writer.writerow(['Name', 'Matr', 'AgeBand', 'Year', 'Category'])

	acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first().id
	matr = db.Affiliations.Matr.min()
	matrrows = db(db.Affiliations.Matr!=None).select(db.Affiliations.Member, matr, groupby = db.Affiliations.Member)
	
	def output(r, startpaid, endpaid, status):
		if not endpaid:
			return
		name = r.Members.Lastname + ', ' + r.Members.Firstname
		m = matrrows.find(lambda m: m.Affiliations.Member == r.AccTrans.Member).first()
		matric = m[matr] if m else None
		year = endpaid.year-1
		while year >= max(startpaid.year, 2016):
			writer.writerow([name, str(matric) if matric else '', ageband(year, matric),
						str(year), status])
			year -= 1

	rows = db((db.AccTrans.Account==acdues)&(db.AccTrans.Amount>0)&(db.AccTrans.Member!=None)).select(
		db.AccTrans.ALL, db.Members.Lastname, db.Members.Firstname, db.Members.Paiddate, db.Members.Pay_next,
		left = db.Members.on(db.AccTrans.Member==db.Members.id),
		orderby = db.Members.Lastname|db.Members.Firstname|~db.AccTrans.Timestamp
	)

	l = None
	end = 0
	for r in rows:
		if not l or l.AccTrans.Member != r.AccTrans.Member:
			if r.Members.Pay_next: #assume next autopayment will be made
				end = datetime.date(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year+1, 1, 1)
			else:
				end = r.Members.Paiddate

		if not end:		#some historical records missing Paiddate, assume 1yr membership
			end = r.AccTrans.Timestamp.date() + datetime.timedelta(365)
		output(r, r.AccTrans.Timestamp.date(), end, r.AccTrans.Membership)
		end = r.AccTrans.Paiddate

		l = r

	return locals()

@action('member_reservations/<member_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def member_reservations(member_id):
# .../member_reservations/member_id/...
	access = session.access	#for layout.html
	header = CAT(A('back', _href=request.query.back),
				H5('Member Reservations'),
		  		H6(member_name(member_id)),
				A('Add New Reservation', _href=URL(f'add_member_reservation/{member_id}',
					vars=dict(back=request.url), scheme=True)))

	grid = Grid((db.Reservations.Member==member_id)&(db.Reservations.Host==True),
			left=db.Events.on(db.Events.id == db.Reservations.Event),
			orderby=~db.Events.DateTime,
			columns=[db.Events.DateTime,
					Column('event', lambda row: A(db.Events[row.Reservations.Event].Description,
								_href=URL(f"manage_reservation/{member_id}/{row.Reservations.Event}",
				  					vars=dict(back=request.url)),
								_style="white-space: normal")),
					Column('wait', lambda row: res_wait(member_id, row.Reservations.Event) or '', required_fields=[db.Reservations.Event]),
					Column('conf', lambda row: res_conf(member_id, row.Reservations.Event) or ''),
					Column('cost', lambda row: event_cost(row.Reservations.Event, member_id) or ''),
					Column('tbc', lambda row: event_unpaid(row.Reservations.Event, member_id) or '')],
			grid_class_style=grid_style,
			formstyle=form_style,
			details=False, editable = False, create = False, deletable = False)
	return locals()
	
@action('add_member_reservation/<member_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('write')
def add_member_reservation(member_id):
	access = session.access	#for layout.html
	back = request.query.back
	header = CAT(A('back', _href=back),
		  		H5('Add New Reservation'),
		  		H6(member_name(member_id)),
				)

	form=Form([Field('event', 'reference db.Events',
		  requires=IS_IN_DB(db, 'Events', lambda r: f"{r.DateTime.strftime(DATE_FORMAT)} {r.Description[:25]}",
						orderby = ~db.Events.DateTime,
			  			zero='Please select event for new reservation from dropdown.'))],
		formstyle=FormStyleBulma)
	
	if form.accepted:
		redirect(URL(f"manage_reservation/{member_id}/{form.vars.get('event')}",
				vars=dict(back=back)))
	return locals()

@action('affiliations/<ismember>/<member_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess(None)
def affiliations(ismember, member_id):
	access = session.access	#for layout.html
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back
	
	if ismember=='Y':
		if member_id!=session.member_id:
			raise Exception(f"invalid call to affiliations from member {session.member_id}")
		write = True
	else:
		if not session.access:
			redirect(URL('accessdenied'))
		write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	db.Affiliations.Member.default=member_id


	header = CAT(A('back', _href=back),
		  		H5('Member Affiliations'),
		  		H6(member_name(member_id)))
	footer = "Multiple affiliations are listed in order modified. The topmost one \
is used on name badges etc."

	def affiliation_modified(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(db.Affiliations.Member==member_id,
		 	orderby=db.Affiliations.Modified,
			columns=[db.Affiliations.College, db.Affiliations.Matr, db.Affiliations.Notes],
			details=not write, editable=write, create=write, deletable=write, show_id=True,
			validation=affiliation_modified, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

#switch user's primary email to newly validated email
@action('switch_email', method=['GET'])
@preferred
@checkaccess(None)
def switch_email():
	member_id = request.query.member_id
	member = db.Members[member_id]
	session.member_id = int(member_id)
	session.access = member.Access
	email_id = db.Emails.insert(Member=member_id, Email=session.email, Mailings=eval(request.query.get('mailings')))
	flash.set("Please review your mailing list subscriptions")
	notify_support(member.id, 'Email address change',
		f"New primary email address {primary_email(member.id)}")
	redirect(request.query.back)

@action('unsubscribe/<email_id:int>/<list_id:int>/<hash>', method=['POST', 'GET'])
@preferred
def unsubscribe(email_id, list_id, hash):
	email = db.Emails[email_id]
	list = db.Email_Lists[list_id]
	if not email or generate_hash(email.Email)!=hash or list.id not in email.Mailings:
		redirect(URL('my_account'))
	header = f"Please Confirm to unsubscribe '{email.Email}' from '{list.Listname}' mailing list."
	form = Form([], csrf_protection=False, submit_value='Confirm', formstyle=FormStyleBulma)

	if form.accepted:
		email.Mailings.remove(list.id)
		email.update_record(Mailings=email.Mailings, Modified=email.Modified)
			#don't update Modified, don't change primary email
		header = f"{email.Email} unsubscribed from '{list.Listname}'"
		notify_support(email.Member, 'Unsubscribe', header)
		header = "Thank you: "+header
		form = None
	return locals()

@action('emails/<ismember>/<member_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess(None)
def emails(ismember, member_id):
	access = session.access	#for layout.html
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back

	if ismember=='Y':
		if member_id!=session.member_id:
			flash.set("please login using the email address to which the Society sends email")
			redirect(URL('logout'))
		write = True
	else:
		if not session.access:
			redirect(URL('accessdenied'))
		write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	db.Emails.Member.default=member_id

	if parsed['mode'] == 'select':
		member = db.Members[member_id]
		paymentprocessor(member.Pay_source).update_email(member)
	else:
		if parsed['mode']=='new':
			db.Emails.Email.writable = True
			old_primary_email = db(db.Emails.Member == member_id).select(orderby=~db.Emails.Modified).first()
			db.Emails.Mailings.default = old_primary_email.Mailings if old_primary_email else None
			if ismember=='Y':
				db.Emails.Mailings.readable=db.Emails.Mailings.writable=False
	

	header = CAT(A('back', _href=back),
		  		H5('Member Emails'),
		  		H6(member_name(member_id)))
	if parsed['mode']=='select':	
		header = CAT(header, XML("Note, the most recently edited (topmost) email is used for messages \
directed to the individual member, and appears in the Members Directory. Notices \
are sent as specified in the Mailings Column.<br>To switch to a new email address, use <b>+New</b> button.<br>\
To change your mailing list subscritions, use the <b>Edit</b> button."))
	if parsed['mode']=="new":
		if ismember=='Y':
			flash.set("When you submit your new email address, you will be sent an email at the new address containing a confirmation link.")
	elif parsed['mode']=='select' or ismember!='Y':
		table_rows=[]
		for l in db(db.Email_Lists.id>0).select():
			table_rows.append(TR(TH(l.Listname, _style="text-align:left"), TD(XML(l.Description), _style="white-space: normal")))
		footer = CAT("The mailing lists are used as follows:",
				XML(TABLE(*table_rows).__str__()))

	def validate(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if ismember=='Y' and not form.vars.get('id'): #member adding new address
			redirect(URL('send_email_confirmation', vars=dict(email=form.vars['Email'],
				url = URL('switch_email', vars=dict(mailings=db.Emails.Mailings.default, member_id=member_id,
						back=parsed['referrer'])))))

	grid = Grid(db.Emails.Member==member_id,
		 	orderby=~db.Emails.Modified,
			columns=[db.Emails.Email, db.Emails.Mailings],
			details=not write, editable=write, create=write,
			deletable=lambda row: write and (ismember!='Y' or row['id']!=db(db.Emails.Member == member_id).select(orderby=~db.Emails.Modified).first().id),
			validation=validate, show_id=True, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style,
			)

	if ismember=='Y' and (parsed['mode']=='edit' or parsed['mode']=='details'):	#substitute user friendly form for grid form
		grid = None
		email = db.Emails[request.query.get('id')]
		header = CAT(header, email.Email)
		fields = []
		for list in db(db.Email_Lists.id>0).select():
			fields.append(Field(list.Listname.replace(' ', '_'), 'boolean', default=list.id in (email.Mailings or []),
					   comment=XML(list.Description)))
		form = Form(fields)
		if form.accepted:
			mailings = []
			for list in db(db.Email_Lists.id>0).select():
				if form.vars.get(list.Listname.replace(' ', '_')):
					mailings.append(list.id)
			email.update_record(Mailings=mailings)
			flash.set('Thank you for updating your mailing list subscriptions')
			notify_support(member_id, "Mail Subscriptions Updated",
		  		f"{email.Email} {', '.join([list.Listname for list in db(db.Email_Lists.id.belongs(mailings)).select()])}")
			redirect(URL(f"emails/Y/{member_id}", vars=dict(back=URL('my_account'))))
	return locals()
	
@action('new_members', method=['GET'])
@preferred
@checkaccess('read')
def new_members():
	access = session.access	#for layout.html
	acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first().id

	rows = db((db.AccTrans.Account==acdues) & (db.AccTrans.Member!=None) & (db.AccTrans.Amount>0)).select(orderby=~db.AccTrans.Timestamp)

	def classify(transaction):
		if not transaction.Paiddate:
			return 'New'
		if transaction.Timestamp.date() < transaction.Paiddate + datetime.timedelta(days=GRACE_PERIOD):
			return 'Renewal'
		return transaction.Paiddate.strftime(DATE_FORMAT)
	
	rows = rows.find(lambda r: classify(r) != 'Renewal')
	ids = [r.id for r in rows]
	
	header = CAT(A('back', _href= request.query.back),
		  		H5('Recent New/Reinstated Members'))

	grid = Grid(db.AccTrans.id.belongs(ids), orderby=~db.AccTrans.Timestamp,
			columns=[Column("Name", lambda row: A(member_name(row.Member), _href=URL('members',
													vars=dict(referrer=encode_url(request.url),
													mode = 'details' if access=='read' else 'edit',
													id=row.Member)),
													_style="white-space: normal")),
					Column("College", lambda row: primary_affiliation(row.Member), required_fields=[db.AccTrans.Member, db.AccTrans.Timestamp]),
					Column("Matr", lambda row: primary_matriculation(row.Member)),
					Column("Status", lambda row: db.Members[row.Member].Membership),
					Column('Date', lambda row: row.Timestamp.strftime(DATE_FORMAT)),
					Column('Previous', lambda row: classify(db.AccTrans[row.id])),
					Column("Source", lambda row: db.Members[row.Member].Source)],
			deletable=False, details=False, editable=False, create=False,
			grid_class_style=grid_style, search_queries=[],
			formstyle=form_style,
	)
	return locals()
	
@action('email_lists', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def email_lists():
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back

	header = H5('Email Lists')

	if parsed['mode']=='select':
		# Remove references in Emails.Mailings to Email_Lists records that no longer exist

		# Get all valid Email_Lists IDs
		valid_list_ids = set(r.id for r in db(db.Email_Lists).select(db.Email_Lists.id))

		# Iterate over all Emails records
		for email in db(db.Emails).select():
			if not email.Mailings:
				continue
			# Remove invalid IDs
			cleaned = [lid for lid in email.Mailings if lid in valid_list_ids]
			if cleaned != email.Mailings:
				email.update_record(Mailings=cleaned)
	else:
		if parsed['mode']=='new':
			header = CAT(A('back', _href=back), H5('New Email List'))
		else:
			list_id = request.query.get('id')
			header = CAT(A('back', _href=back), H5('Email List Record'),
						A('Make a Copy of This Email List', _href=URL(f'email_list_copy/{list_id}',
								vars=dict(referrer=request.query.referrer))))

	def validation(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(db.Email_Lists.id>0,
			details=not write, editable=write, create=write, deletable=write,
			validation=validation, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()
	
@action('email_list_copy/<list_id:int>', method=['GET'])
@preferred
@checkaccess('write')
def email_list_copy(list_id):
	email_list = db.Email_Lists[list_id]
	new_list_id = db.Email_Lists.insert(Listname='Copy of '+email_list.Listname, Member=email_list.Member,
								Description=email_list.Description)

	for e in db(db.Emails.Mailings.contains(list_id)).select():
		e.Mailings.append(new_list_id)
		e.update_record()

	flash.set("Please customize the new email list.")
	redirect(URL('email_lists',
			vars=dict(mode='edit', id=str(new_list_id), referrer=request.query.referrer)))
	
@action('events', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def events():
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.url

	header = H5('Events')

	if parsed['mode'] == 'select':
		footer = CAT(A("Export all Events as CSV file", _href=URL('events_export')), XML('<br>'),
			A("Export event analytics as CSV file", _href=URL('event_analytics')))
	else:
		if parsed['mode']=='new':
			header = CAT(A('back', _href=back), H5('New Event'))
		else:
			event_id = parsed['record_id']
			event = db.Events[event_id]
			url = URL('registration', event_id, scheme=True)
			urlpage = URL(f"event_page/{event.id}", scheme=True) if event.Details else event.Page
			header = CAT(A('back', _href=back), H5('Event Record'),
						"Booking link is ", A(url, _href=url), XML('<br>'),
						"Event page is ", A(urlpage, _href=urlpage), XML('<br>'),
						A('Table Assignment Tool', _href=URL(f'assign_tables/{event_id}', scheme=True)), XML('<br>'),
						A('Ticket Types', _href=URL(f'tickets/{event_id}',
								vars=dict(back=request.url))), XML('<br>'),
						A('Selections', _href=URL(f'selections/{event_id}',
								vars=dict(back=request.url))), XML('<br>'),
						A('Survey', _href=URL(f'survey/{event_id}',
								vars=dict(back=request.url))), XML('<br>'),
						A('Make a Copy of This Event', _href=URL(f'event_copy/{event_id}',
								vars=dict(referrer=request.query.referrer))))

	def validation(form):
		if not (form.vars.get('Page') or form.vars.get('Details')):
			form.errors['Details']="Please provide either an external Page or Details"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(db.Events.id>0,
		 	orderby=~db.Events.DateTime,
			headings=['Datetime', 'Event', 'Venue', 'Paid', 'TBC', 'Wait', 'Conf', '✔'],
			columns=[db.Events.DateTime,
					Column('event', lambda row: A(row.Description, _href=URL(f"event_reservations/{row.id}",
										vars=dict(back=request.url)),
								   _style="white-space: normal"), required_fields=[db.Events.Description]),
	   				db.Events.Venue,
					Column('Paid', lambda row: event_revenue(row.id) or ''),
					Column('TBC', lambda row: event_unpaid(row.id) or ''),
					Column('Wait', lambda row: event_wait(row.id) or ''),
					Column('Conf', lambda row: event_attend(row.id) or ''),
					Column('Checked_in', lambda row: event_checked_in(row.id) or '')],
			search_queries=[["Event", lambda value: db.Events.Description.ilike(f'%{value}%')],
							["Venue", lambda value: db.Events.Venue.ilike(f'%{value}%')],
							["Speaker", lambda value: db.Events.Speaker.ilike(f'%{value}%')],
							["Details", lambda value: db.Events.Details.ilike(f'%{value}%')]],
			details=not write, editable=write, create=write,
			deletable=lambda r: write and db(db.Reservations.Event == r['id']).count() == 0 and db(db.AccTrans.Event == r['id']).count() == 0,
			validation=validation,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

@action('event_page/<event_id:int>', method=['GET'])
@preferred
def event_page(event_id):
	access = session.access	#for layout.html
	event = db.Events[event_id]
	event.update_record(Views=event.Views+1, Modified=event.Modified)
	header = XML(markdown.markdown(str(template_expand(event.Details, locals()))))
	return locals()
	
@action('tickets/<event_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def tickets(event_id):
# .../tickets/event_id/...
	access = session.access	#for layout.html

	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back

	event=db.Events[event_id]
	db.Event_Tickets.Event.default=event_id

	header = CAT(A('back', _href=back),
		  		H5('Event Tickets'),
		  		H6(event.Description),
				"Note, be careful of modifying tickets once used in any reservations!")

	def validation(form):
		if not form.vars.get('id'):	#new ticket type
			if db((db.Event_Tickets.Event==event_id)&(db.Event_Tickets.Ticket==form.vars.get('ticket'))).count()>0:
				form.errors['ticket']="ticket type already exists"
			if db((db.Event_Tickets.Event==event_id)&\
		 		(db.Event_Tickets.Short_name==form.vars.get('short_name'))).count()>0:
				form.errors['short_name']="short_name already exists"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(db.Event_Tickets.Event==event_id,
			columns=[db.Event_Tickets.Ticket, db.Event_Tickets.Price, db.Event_Tickets.Qualify, db.Event_Tickets.Count,
				db.Event_Tickets.Waiting, Column('Sold', lambda t: tickets_sold(t.id))],
			details=not write, create=write, editable=write,
			deletable= lambda t: write and db(db.Reservations.Ticket_==t.id).count()==0,
			validation=validation, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style, show_id=True
			)
	return locals()
	
@action('selections/<event_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def selections(event_id):
# .../selections/event_id/...
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back

	event=db.Events[event_id]
	db.Event_Selections.Event.default=event_id

	header = CAT(A('back', _href=back),
		  		H5('Event Selections'),
		  		H6(event.Description),
				"Note, changes made here are not reflected in any existing reservations!")

	def validation(form):
		if not form.vars.get('id'):	#new selection
			if db((db.Event_Selections.Event==event_id)&\
		 		(db.Event_Selections.Selection==form.vars.get('selection'))).count()>0:
				form.errors['selection']="selection already exists"
			if db((db.Event_Selections.Event==event_id)&\
		 		(db.Event_Selections.Short_name==form.vars.get('short_name'))).count()>0:
				form.errors['short_name']="short_name already exists"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(db.Event_Selections.Event==event_id,
			columns=[db.Event_Selections.Selection,
				Column('selected', lambda t: db((db.Reservations.Selection_==t.id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).count())],
			details=not write, create=write, editable=write,
			deletable= lambda t: write and db(db.Reservations.Selection_==t.id).count()==0,
			validation=validation, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style, show_id=True
			)
	return locals()
	
@action('survey/<event_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def survey(event_id):
# .../survey/event_id/...
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back

	event=db.Events[event_id]
	db.Event_Survey.Event.default=event_id
	modifiable = write and db((db.Reservations.Event==event_id)&(db.Reservations.Survey_!=None)).count()==0

	header = CAT(A('back', _href=back),
		  		H5('Event Survey'),
		  		H6(event.Description),
				"Note, survey elements cannot be modified once chosen")

	def validation(form):
		if not form.vars.get('id'):	#new selection
			if db((db.Event_Survey.Event==event_id)&\
		 		(db.Event_Survey.Item==form.vars.get('item'))).count()>0:
				form.errors['item']="survey item already exists"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	def count(id):
		count = db((db.Reservations.Survey_==id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).count()
		return count if count>0 else ''
	
	grid = Grid(db.Event_Survey.Event==event_id,
			columns=[db.Event_Survey.Item,
				Column('chosen', lambda t: count(t.id))],
			details=False, create=write,
			editable=lambda t: write and db(db.Reservations.Survey_==t.id).count()==0,
			deletable=lambda t: write and db(db.Reservations.Survey_==t.id).count()==0,
			validation=validation, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style, show_id=True
			)
	return locals()

@action('event_analytics', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def event_analytics():
	stream=StringIO()
	content_type = "text/csv"
	filename = 'event_analytics.csv'

	writer=csv.writer(stream)
	writer.writerow(['Name', 'College', 'Oxbridge', 'Matr', 'AgeBand', 'PartySize', 'Event', 'EventYear'])

	rows = db((db.Reservations.Host==True) & (db.Reservations.Waitlist==False) & (db.Reservations.Provisional==False)& \
					(db.Reservations.Event == db.Events.id)).select(db.Reservations.Member, db.Reservations.Lastname,
					db.Reservations.Firstname, db.Reservations.Affiliation, db.Events.Description, db.Events.DateTime,
					db.Events.id, 
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
@preferred
@checkaccess('read')
def event_reservations(event_id):
# ...event_reservatins/event_id/...
# request.query: waitlist=True, provisional=True
	access = session.access	#for layout.html
	actkts = db(db.CoA.Name.ilike("Ticket sales")).select().first().id

	db.Reservations.id.readable=db.Reservations.Event.readable=False

	event = db.Events[event_id]

	paid = event_paid_dict(event_id)
	cost = event_ticket_dict(event_id)
	tbc = str([member for member in paid.keys() if paid[member] != (cost.get(member) or 0)])

	search_fields = [
		Field('status', 'string', default = request.query.get('status') or 'confirmed',
				requires=IS_IN_SET(['confirmed', 'tbc', 'checked_in', 'no_show', 'waitlist', 'provisional'], zero='status?'),),
	]
	if db(db.Event_Tickets.Event==event_id).count()>1:
		search_fields.append(
			Field('ticket', 'reference Event_Tickets', default = request.query.get('ticket'),
					requires=IS_EMPTY_OR(IS_IN_DB(db(db.Event_Tickets.Event==event_id), db.Event_Tickets.id,
								'%(Short_name)s', zero="ticket?"))))
	if db(db.Event_Selections.Event==event_id).count()>0:
		search_fields.append(
			Field('selection', 'reference Event_Selections', default = request.query.get('selection'),
					requires=IS_EMPTY_OR(IS_IN_DB(db(db.Event_Selections.Event==event_id), db.Event_Selections.id,
								'%(Short_name)s', zero="selection?"))))
	survey = db(db.Event_Survey.Event==event_id).select()
	if len(survey)>0:
		event_survey = [(s.id, s.Short_name) for s in survey[1:]]
		search_fields.append(Field('survey', requires=IS_EMPTY_OR(IS_IN_SET(event_survey, zero="survey?",
			error_message='Please make a selection')), default = request.query.get('survey')))

	search_form=Form(search_fields, keep_values=True, formstyle=FormStyleBulma)

	if search_form.accepted:
		vars=dict(request.query)
		vars['status'] = search_form.vars.get('status') or ''
		vars['ticket'] = search_form.vars.get('ticket') or ''
		vars['selection'] = search_form.vars.get('selection') or ''
		vars['survey'] = search_form.vars.get('survey') or ''
		redirect(URL(f"event_reservations/{event_id}", vars=vars))
	
	header = CAT(A('back', _href=request.query.back),
				H6(f"{event.DateTime}, {event.Description}"),
				XML("Click on the member name to view/edit reservation details."),
				XML('<br>'))

	query = f'(db.Reservations.Event=={event_id})'
	status = request.query.get('status') or 'confirmed'
	if status == 'tbc':
		query += f"&db.Reservations.Member.belongs({tbc})"
	#for waitlist, provisional, checked_in, no_show, include hosts with any guests meeting criteria
	elif status == 'waitlist':
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Waitlist==True)).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	elif status == 'provisional':
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Provisional==True)).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	elif status == 'checked_in':
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Checked_in==True)).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	else:	#confirmed, no show
		query += '&(db.Reservations.Waitlist==False)&(db.Reservations.Provisional==False)'
		header = CAT(header, A('Export confirmed registrations as CSV file',
			 _href=(URL(f'doorlist_export/{event_id}', scheme=True))), XML('<br>'),
			 A('Check-in Tool', _href=URL(f'check_in/{event_id}', scheme=True)), XML('<br>'),)
		
	if status == 'no_show':
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Checked_in==False)).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	if request.query.ticket:
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Ticket_=={request.query.ticket})).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	if request.query.selection:
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Selection_=={request.query.selection})).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	if request.query.survey:
		query += f"&db.Reservations.Member.belongs([r.Member for r in db((db.Reservations.Event=={event_id})&\
(db.Reservations.Survey_=={request.query.survey})).select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	query += '&(db.Reservations.Host==True)'

	header = CAT(header, A('Send Email to filtered registrations', _href=URL('composemail', vars=dict(query=query,
		left  = "[db.Emails.on(db.Emails.Member==db.Reservations.Member),db.Members.on(db.Members.id==db.Reservations.Member)]",	
		qdesc=f"{event.Description} {status}",
		back=request.url
		))))
	header = CAT(header, XML('<br>'), "Use dropdowns to filter (includes reservation if member or any guest fits filter):")

	grid = Grid(eval(query),
			left=db.Members.on(db.Members.id == db.Reservations.Member),
			orderby=db.Reservations.Created if status=='waitlist' else db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[Column('member', lambda row: A(member_name(row.Reservations.Member),
										   _href=URL(f"manage_reservation/{row.Reservations.Member}/{event_id}",
											vars=dict(back=request.url)),
										   _style='white-space: normal'), required_fields=[db.Reservations.Member]),
						db.Members.Membership, db.Members.Paiddate, db.Reservations.Affiliation, db.Reservations.Notes,
						Column('cost', lambda row: cost.get(row.Reservations.Member) or ''),
						Column('tbc', lambda row: (cost.get(row.Reservations.Member) or 0)-paid.get(row.Reservations.Member) or ''),
						Column('count', lambda row: (res_wait(row.Reservations.Member, event_id) if status=='waitlist'\
					  		else res_prov(row.Reservations.Member, event_id) if status=='provisional'\
							else res_checked_in(row.Reservations.Member, event_id, True) if status=='checked_in'\
							else res_checked_in(row.Reservations.Member, event_id, False) if status=='no_show'\
							else res_conf(row.Reservations.Member, event_id)) or'')],
			headings=['Member', 'Type', 'Until', 'College', 'Notes', 'Cost', 'Tbc', '#'],
			search_form=search_form if len(search_fields)>0 else None,
			details=False, editable = False, create = False, deletable = False,
			rows_per_page=200, grid_class_style=grid_style, formstyle=form_style)
	return locals()
		
@action('check_in/<event_id:int>', method=['POST', 'GET'])
@action.uses("check_in.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER))
@checkaccess('read')
def check_in(event_id):
	event = db.Events[event_id]
	access = session.access	#for layout.html
	search_value = request.query.get('search_value') or ''
	header = H6(f"Check-in {event.DateTime.date()}, {event.Description}")
		
	back = URL(f"check_in/{event_id}")

	if request.query.get('rsvtn_id'):
		rsvtn = db.Reservations[request.query.rsvtn_id]
		if rsvtn.Event != event_id:
			raise Exception('Invalid event id')
		rsvtn.update_record(Checked_in=not rsvtn.Checked_in)
		if res_checked_in(rsvtn.Member, event_id) != res_conf(rsvtn.Member, event_id):
			back += f"?search_value={rsvtn.Lastname[0:2]}"
		redirect(back)

	grid = Grid((db.Reservations.Event==event_id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False),
			left = db.Members.on(db.Members.id==db.Reservations.Member),
			orderby=db.Members.Lastname|db.Members.Firstname|~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[
				Column('guest', lambda row: CAT(('+ ' if not row.Host else ''),
									A(f"{row.Lastname+', '+row.Firstname}",
									_href=URL(f"manage_reservation/{row.Member}/{event_id}",
									vars=dict(back=back)), _style='white-space: normal')),
					required_fields=[db.Reservations.Host, db.Reservations.Lastname, db.Reservations.Firstname, db.Reservations.Member]),
				Column('check in', lambda row: A( "⬤"if row.Checked_in else "〇", _href=URL(f"check_in/{event_id}",
									vars=dict(rsvtn_id=row.id))), required_fields=[db.Reservations.Checked_in]),
			],
			details=False, editable=False, create=False,
			deletable=False, search_queries=[],
			grid_class_style=grid_style,rows_per_page=1000,
			formstyle=form_style)
	return locals()
		
@action('assign_tables/<event_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('write')
def assign_tables(event_id):
	event = db.Events[event_id]
	access = session.access	#for layout.html
	header = CAT(H6(f"Assign Tables {event.DateTime.date()}, {event.Description}"),
				XML("Assigning host member to table assigns entire party."),
				)
		
	back = request.url

	query = f"(db.Reservations.Event=={event_id})&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)"

	#display table counts before assignment form and detailed assignment grid
	tablecount = db.Reservations.Table.count()
	db(eval(query)).select(db.Reservations.Table, tablecount, orderby=db.Reservations.Table, groupby=db.Reservations.Table,)
	form = Grid(eval(query), orderby=db.Reservations.Table, groupby=db.Reservations.Table,
			 columns=[db.Reservations.Table,
					Column('Count', lambda row: row[tablecount] or '', required_fields=[tablecount])],
			details=False, editable=False, create=False, deletable=False, search_queries=[],
			grid_class_style=grid_style, rows_per_page=100, formstyle=form_style)

	search_form = Form([
		Field('table', 'string',
			widget=lambda field, value: INPUT(_name='table', _type='text', _value=request.query.get('table'), _placeholder="table?"),
			requires=IS_NOT_EMPTY()),
		Field('host', 'reference Members', requires=IS_IN_DB(db(
			(db.Reservations.Event==event_id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)&(db.Reservations.Host==True)),
			db.Reservations.Member, '%(Lastname)s, %(Firstname)s', zero='host member?')),],
		formstyle=FormStyleBulma, submit_value='Submit')

	if search_form.accepted:	#Assign button clicked
		select_vars = {}
		if search_form.vars.get('table'):
			select_vars['table'] = search_form.vars.get('table')
			if search_form.vars.get('host'):
				db(eval(query+"&(db.Reservations.Member==search_form.vars.get('host'))")).update(Table=search_form.vars.get('table'))
		redirect(URL(f"assign_tables/{event_id}", vars=select_vars))

	grid = Grid(eval(query), left = db.Members.on(db.Members.id==db.Reservations.Member),
			orderby=db.Reservations.Table|db.Members.Lastname|db.Members.Firstname|~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[
				Column('Guest', lambda row: CAT(('+ ' if not row.Reservations.Host else ''),
									A(f"{row.Reservations.Lastname+', '+row.Reservations.Firstname}",
									_href=URL(f"manage_reservation/{row.Reservations.Member}/{event_id}",
									vars=dict(back=back)), _style='white-space: normal')),
					required_fields=[db.Reservations.Host, db.Reservations.Lastname, db.Reservations.Firstname, db.Reservations.Member]),
				db.Members.Membership, db.Reservations.Affiliation,
				Column('Matr', lambda row: primary_matriculation(row.Reservations.Member) if row.Reservations.Host else ''),
				db.Reservations.Notes, db.Reservations.Table,
			],
			details=False, editable=False, create=False,
			deletable=False, search_form=search_form,
			grid_class_style=grid_style,rows_per_page=1000, search_button_text='Assign',
			formstyle=form_style)
	return locals()

#this controller is used by privileged users to manage event registrations.
#most of the rules governing registration, e.g. capacity constrains, membership requirements,
#are not enforced - we assume the privileged user knows what they are doing.
@action('manage_reservation/<member_id:int>/<event_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def manage_reservation(member_id, event_id):
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')
	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back
	id = int(parsed['record_id'] or 0)

	event = db.Events[event_id]
	clist = collegelist(sponsors = event.Sponsors or [])
	member = db.Members[member_id]

	all_guests = db((db.Reservations.Member==member.id)&(db.Reservations.Event==event.id)).select(orderby=~db.Reservations.Host)
	host_reservation = all_guests.first()

	if parsed['mode']=='select':
		if host_reservation and not host_reservation.Host:	#provisional reservation delete, start over
			for row in all_guests:	#delete all guests after host reservation deleted
				db(db.Reservations.id==row.id).delete()
			redirect(request.url)

	tickets = db(db.Event_Tickets.Event==event_id).select()
	event_tickets = [(t.id, f"{t.Ticket}{' (waitlisting)' if t.Waiting else ''}") for t in tickets]
	selections = db(db.Event_Selections.Event==event_id).select()
	event_selections = [(s.id, s.Selection) for s in selections]
	
	header = CAT(H5('Event Registration'), H6(member_name(member_id)),
			XML(event_confirm(event.id, member.id, event_only=True)))

	header = CAT(A('back', _href=back), header)
	if parsed['mode']=='select':
		header = CAT(header, A('send email', _href=(URL('composemail', vars=dict(
			query=f"(db.Members.id=={member_id})&(db.Members.id==db.Reservations.Member)&(db.Reservations.Event=={event_id})&(db.Reservations.Host==True)",
			qdesc=member_name(member_id), back=request.url)))),
			XML(" (use "), "[[reservation]]", XML(" to include confirmation and payment link)<br>"),
			A('view member record', _href=URL('members',
				vars=dict(referrer=encode_url(request.url), mode='edit' if write else 'details', id=member_id))),
			XML("<br>Top row is the member's own reservation, additional rows are guests.<br>\
Use Add Record to add the member, initially, then to add additional guests.<br>\
Edit rows to move on/off waitlist or first row to record a check payment.<br>\
Deleting or moving member on/off waitlist will also affect all guests."))
	
	#set up reservations form, we have both member and event id's
	db.Reservations.Member.default = member.id
	db.Reservations.Event.default=event.id
	db.Reservations.Affiliation.requires=IS_EMPTY_OR(IS_IN_SET(clist))
	db.Reservations.Event.readable=False
	db.Reservations.Provisional.writable = True
	db.Reservations.Waitlist.writable = True
	db.Reservations.Checked_in.writable = True
	db.Reservations.Member.readable = False

	if host_reservation:
		#update member's name from member record in case corrected
		host_reservation.update_record(Title=member.Title, Firstname=member.Firstname,
					Lastname=member.Lastname, Suffix=member.Suffix,
					Modified=host_reservation.Modified) 
			
	if selections:
		db.Reservations.Selection_.requires=IS_IN_SET(event_selections, zero='please make a selection')
	else:
		db.Reservations.Selection_.writable = db.Reservations.Selection_.readable = False
		
	if tickets:
		db.Reservations.Ticket_.requires=IS_EMPTY_OR(IS_IN_SET(event_tickets, zero='please select the appropriate ticket'))
	else:
		db.Reservations.Ticket_.writable = db.Reservations.Ticket_.readable = False
	

	if  parsed['mode']=='edit' or parsed['mode']=='new':	#editing or creating reservation
		if host_reservation and (parsed['mode']=='new' or host_reservation.id!=id):
			#this is a new guest reservation, or we are revising a guest reservation
			db.Reservations.Host.default=False
			db.Reservations.Firstname.writable=True
			db.Reservations.Lastname.writable=True
			db.Reservations.Provisional.default=not host_reservation.Waitlist
			db.Reservations.Waitlist.default=host_reservation.Waitlist
			db.Reservations.Table.readable=db.Reservations.Table.writable=False
			db.Reservations.Charged.readable=False
			db.Reservations.Survey_.readable=False
			db.Reservations.Checkout.readable=False
			db.Reservations.Comment.readable=False
		else:
			#creating or revising the host reservation
			db.Reservations.Title.default = member.Title
			db.Reservations.Firstname.default = member.Firstname
			db.Reservations.Lastname.default = member.Lastname
			db.Reservations.Firstname.readable=db.Reservations.Lastname.readable=False
			db.Reservations.Suffix.default = member.Suffix
			db.Reservations.Charged.writable=True
			db.Reservations.Checkout.writable=True

			affinity = db(db.Affiliations.Member==member_id).select(orderby=db.Affiliations.Modified).first()
			if affinity:
				db.Reservations.Affiliation.default = affinity.College
				db.Reservations.Affiliation.writable = False
	
	def validate(form):
		if form.vars.get('Waitlist') and form.vars.get('Provisional'):
			form.errors['Waitlist'] = "Waitlist and Provisional should not both be set"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id') and (int(form.vars.get('id')) == host_reservation.id)):
			if form.vars.get('Table') != host_reservation.Table:
				for row in all_guests:
					row.update_record(Table = form.vars.get('Table'))
			if form.vars.get('Waitlist') != host_reservation.Waitlist or form.vars.get('Provisional') != host_reservation.Provisional:
				for row in all_guests:
					if row.id != host_reservation.id and (not row.Provisional or host_reservation.Provisional):
						row.update_record(Waitlist = form.vars.get('Waitlist'), Provisional = form.vars.get('Provisional'))

	grid = Grid((db.Reservations.Member==member.id)&(db.Reservations.Event==event.id),
			orderby=~db.Reservations.Host|db.Reservations.Created,
			columns=[db.Reservations.Lastname, db.Reservations.Firstname, db.Reservations.Notes,
					Column('Selection', lambda row: res_selection(row.id),
						required_fields=[db.Reservations.Provisional, db.Reservations.Waitlist, db.Reservations.Checked_in]),
					Column('Price', lambda row: res_unitcost(row.id)),
					Column('Status', lambda r: 'waitlisted' if r.Waitlist else \
						'unconfirmed' if r.Provisional else "✔" if r.Checked_in else '')],
			headings=['Last', 'First', 'Notes', 'Selection', 'Price', 'Status'],
			deletable=write,
			details=not write, 
			editable=write, 
			create=write, search_queries=[],
			grid_class_style=grid_style, formstyle=form_style, validation=validate, show_id=True)
	return locals()

#this controller is used by members making their own event reservations	
@action('reservation', method=['POST', 'GET'])
@preferred
@checkaccess(None)
def reservation():
	access = session.access	#for layout.html
	if not session.get('member_id') or not session.get('event_id'):
		redirect(URL('my_account'))

	parsed = Grid.parse(request.query)
	id = int(parsed['record_id'] or 0)
	
	event = db.Events[session.event_id]
	clist = collegelist(sponsors = event.Sponsors or [])
	member = db.Members[session.member_id]
	affinity = db((db.Affiliations.Member==session.member_id)&db.Affiliations.College.belongs([c[0] for c in clist])).select(
						orderby=db.Affiliations.Modified).first()
	all_guests = db((db.Reservations.Member==member.id)&(db.Reservations.Event==event.id)).select(orderby=~db.Reservations.Host)
	host_reservation = all_guests.first()
	if member_good_standing(member, datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()):
		membership = member.Membership
	else:
		membership = session.get('membership')	#if joining with event registration
	#membership ==> current member in good standing
	sponsor = affinity and not affinity.College.Oxbridge

	tickets = db(db.Event_Tickets.Event==session.event_id).select()
	tickets_available = {t.id: t.Count - tickets_sold(t.id) if not t.Waiting else 0 for t in tickets if t.Count}

	header = CAT(H5('Event Registration'), H6(member_name(session.member_id)),
			XML(event_confirm(event.id, member.id, event_only=True)))

	if parsed['mode']=='select':
		if host_reservation and not host_reservation.Host:	#provisional reservation delete, start over
			for row in all_guests:	#delete all guests after host reservation deleted
				db(db.Reservations.id==row.id).delete()
			redirect(URL(f'registration/{session.event_id}'))
		
		#pre-checkout checks on capacity, payment status, etc.
		attend = event_attend(session.event_id) or 0
		provisional_ticket_cost = 0
		adding = 0
		waitlist = event.Waiting
		for row in all_guests:
			if (not tickets or row.Ticket_) and row.Provisional:
				ticket = tickets.find(lambda t: t.id==row.Ticket_).first()
				adding += 1
				if ticket:
					provisional_ticket_cost += ticket.Price
					if ticket.id in tickets_available:
						tickets_available[ticket.id] -= 1
						if tickets_available[ticket.id] == 0:
							flash.set(f"There are no further {ticket.Ticket} tickets for additional guests.")
						elif tickets_available[ticket.id] < 0:
							flash.set(f"Insufficient {ticket.Ticket} tickets available: please Edit to select a different ticket type or Checkout to add unconfirmed guests to the waitlist.")
							waitlist = True
		if datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.Booking_Closed:
			waitlist = True
			flash.set("Registration is closed, please use +New and Checkout to add new guests to the waitlist.")
		elif event.Capacity and (attend+adding>event.Capacity or event.Waiting):
			waitlist = True
			flash.set("Event is full: please use +New and Checkout to add new guests to the waitlist.")
		elif event.Capacity and attend+adding==event.Capacity:
			flash.set(f"Please note, this fills the event; if you add another guest all unconfirmed guests will be waitlisted.")
		dues_tbc = f" (including {CURRENCY_SYMBOL}{session['dues']} membership dues)" if session.get('dues') else ''
		payment = (int(session.get('dues') or 0)) + event_unpaid(session.event_id, session.member_id)
		if not waitlist:
			payment += (provisional_ticket_cost or 0)
		if not event.Guests or len(all_guests)<event.Guests:
			header = CAT(header,  XML(f"Use the '+New' button to add another guest.<br>"))
		if adding!=0:
			if waitlist:
				header = CAT(header,  XML(f"Please click 'Checkout' to join the waitlist.<br>"))
			else:
				header = CAT(header,  XML(f"Your place(s) are not allocated until you click the 'Checkout' button.<br>"))
		if payment>0 and payment>int(session.get('dues') or 0):
			header = CAT(header, XML(f"Your registration will be confirmed when your payment of {CURRENCY_SYMBOL}{payment}{dues_tbc} is received at Checkout.<br>"))
		elif session.get('dues'):
			header = CAT(header, XML(f"Checkout to pay your {CURRENCY_SYMBOL}{session.dues} membership dues, or wait to see if a space becomes available."))

		host_reservation.update_record(Checkout=str(dict(membership=session.get('membership'),
						dues=session.get('dues'))).replace('Decimal','decimal.Decimal'),
						Modified=host_reservation.Modified)

		fields = []
		if host_reservation.Provisional:
			#add questions to checkout (form2) as applicable
			survey = db(db.Event_Survey.Event==session.event_id).select()
			if len(survey)>0:
				event_survey = [(s.id, s.Item) for s in survey[1:]]
				fields.append(Field('survey', requires=IS_IN_SET(event_survey, zero=survey[0].Item,
									error_message='Please make a selection'),
									default = host_reservation.Survey_))
			if event.Comment:
				fields.append(Field('comment', 'string', comment=event.Comment,
									default = host_reservation.Comment))
		form2 = Form(fields, formstyle=FormStyleBulma, keep_values=True, submit_value='Checkout')

	elif parsed['mode']!='delete':
		#new or edit - creating or editing an individual reservation
		is_guest_reservation = host_reservation and (parsed['mode']=='new' or host_reservation.id!=id)
		if parsed['mode']=='new':
			header = CAT(header,
				f"Please enter your own details{' (you will be able to enter guests on next screen)' if (event.Guests or 2)>1 else ''}:"\
					if not host_reservation else "Please enter your guest's details:")
	
		#set up reservations form
		db.Reservations.Member.default = member.id
		db.Reservations.Event.default=event.id
		db.Reservations.Affiliation.requires=IS_EMPTY_OR(IS_IN_SET(clist))
		db.Reservations.Member.readable = False
		db.Reservations.Event.readable = False
		db.Reservations.Host.readable = False
		db.Reservations.Charged.readable = False
		db.Reservations.Checkout.readable = False
		db.Reservations.Created.readable = False
		db.Reservations.Provisional.readable = False
		db.Reservations.Modified.readable = False
		db.Reservations.Comment.readable = False
		db.Reservations.Survey_.readable = False
		db.Reservations.Provisional.default = True
		db.Reservations.Waitlist.readable = False
		db.Reservations.Checked_in.readable = False
		db.Reservations.Table.readable = False

		if host_reservation:
			#update member's name from member record in case corrected
			host_reservation.update_record(Title=member.Title, Firstname=member.Firstname,
						Lastname=member.Lastname, Suffix=member.Suffix,
						Modified=host_reservation.Modified) 
				
		selections = db(db.Event_Selections.Event==session.event_id).select()
		if selections:
			db.Reservations.Selection_.requires=IS_IN_SET([(s.id, s.Selection) for s in selections], zero='please make a selection')
		else:
			db.Reservations.Selection_.writable = db.Reservations.Selection_.readable = False

		# identify relevant ticket types
		tickets = tickets.find(lambda t: not is_guest_reservation or t.Allow_as_guest==True)
		if membership or sponsor:
			tickets = tickets.find(lambda t: not t.Ticket.lower().startswith('non-member'))
			if not is_guest_reservation:
				member_ticket = tickets.find(lambda t: membership and t.Ticket.lower().startswith(membership.lower()))
				if member_ticket:
					tickets = member_ticket
		else:
			non_member_ticket = tickets.find(lambda t: t.Ticket.lower().startswith('non-member'))
			if non_member_ticket:
				tickets = non_member_ticket
		event_tickets = [(t.id, f"{t.Ticket}{' (waitlisting)' if tickets_available.get(t.id, 1)<=0 else ''}") for t in tickets]
		if tickets:
			db.Reservations.Ticket_.requires=IS_IN_SET(event_tickets, zero='please select the appropriate ticket')
			db.Reservations.Ticket_.default = event_tickets[0][0] if len(event_tickets)==1 else None
			if is_guest_reservation:
				if tickets.find(lambda t: t.id==host_reservation.Ticket_):
					db.Reservations.Ticket_.default = host_reservation.Ticket_
		else:
			db.Reservations.Ticket_.writable = db.Reservations.Ticket_.readable = False

		if is_guest_reservation:
			#this is a new guest reservation, or we are revising a guest reservation
			db.Reservations.Host.default=False
			db.Reservations.Firstname.writable=True
			db.Reservations.Lastname.writable=True
			db.Reservations.Provisional.default=not host_reservation.Waitlist
			db.Reservations.Waitlist.default=host_reservation.Waitlist
		else:
			#creating or revising the host reservation
			db.Reservations.Title.default = member.Title
			db.Reservations.Firstname.default = member.Firstname
			db.Reservations.Lastname.default = member.Lastname
			db.Reservations.Firstname.readable=db.Reservations.Lastname.readable=False
			db.Reservations.Suffix.default = member.Suffix

			if affinity:
				db.Reservations.Affiliation.default = affinity.College
				db.Reservations.Affiliation.writable = False

			if parsed['mode']=='new' and not selections and len(event_tickets)<=1:
				#no choices needed, create the Host reservation and display checkout screen
				db.Reservations.insert(Member=session.member_id, Event=session.event_id, Host=True,
			   		Firstname=member.Firstname, Lastname=member.Lastname, Affiliation=affinity.College if affinity else None,
					Title=member.Title, Suffix=member.Suffix, Ticket_=db.Reservations.Ticket_.default)
				redirect(URL('reservation'))
	
	def validate(form):
		if form.vars.get('Waitlist') and form.vars.get('Provisional'):
			form.errors['Waitlist'] = "Waitlist and Provisional should not both be set"
		if int(form.vars.get('Ticket_')) != db.Reservations.Ticket_.default:
			ticket = tickets.find(lambda t: t.id == int(form.vars.get('Ticket_', '0'))).first()
			if ticket.Qualify and (not form.vars.get('Notes') or form.vars.get('Notes').strip()==''):
				form.errors['Notes']=ticket.Qualify	#documentation required
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid((db.Reservations.Member==member.id)&(db.Reservations.Event==event.id),
			orderby=~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[db.Reservations.Lastname, db.Reservations.Firstname, db.Reservations.Notes,
					Column('Selection', lambda row: res_selection(row.id),
						required_fields=[db.Reservations.Provisional, db.Reservations.Waitlist]),
					Column('Price', lambda row: res_unitcost(row.id)),
					Column('Status', lambda r: 'waitlisted' if r.Waitlist else 'unconfirmed' if r.Provisional else '')],
			headings=['Last', 'First', 'Notes', 'Selection', 'Price', 'Status'],
			deletable=lambda row: row.Provisional or row.Waitlist,
			details=False, 
			editable=lambda row: row.Provisional or row.Waitlist, 
			create=not event.Guests or (len(all_guests)<event.Guests), search_queries=[],
			grid_class_style=grid_style, formstyle=form_style, validation=validate)
	
	if parsed['mode']=='select':
		if len(form2.errors)>0:
			flash.set("Error(s) in form, please check")
		elif adding==0 and payment<=0:
			form2 = ''	#don't need the Checkout form
		elif form2.accepted:
			host_reservation.update_record(Survey_=form2.vars.get('survey'), Comment=form2.vars.get('comment'))
			for row in all_guests:
				if row.Provisional==True:
					if row.Ticket_:
						ticket = db.Event_Tickets[row.Ticket_]
						if ticket.id in tickets_available and tickets_available[ticket.id] < 0:
							ticket.update_record(Waiting=True)
					row.update_record(Provisional=False, Waitlist=waitlist)

			if waitlist:
				flash.set(f"{'You' if host_reservation.Waitlist==True else 'Your additional guest(s)'} have been added to the waitlist.")
				if event.Capacity and attend+adding>event.Capacity:
					event.update_record(Waiting=True)
		
			if payment<=0:	#free event or payment already covered, confirm booking
				if not waitlist:
					host_reservation.update_record(Checkout=None)
					subject = 'Registration Confirmation'
					message = msg_header(member, subject)
					message += '<b>Your registration is now confirmed:</b><br>'
					message += event_confirm(event.id, member.id)
					msg_send(member, subject, message)	
					flash.set('Thank you. Confirmation has been sent by email.')
				redirect(URL(f'reservation'))
			paymentprocessor().checkout(request.url)
	return locals()

@action('doorlist_export/<event_id:int>', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('read')
def doorlist_export(event_id):
	stream = StringIO()
	content_type = "text/csv"
	filename = 'doorlist.csv'
	writer=csv.writer(stream)
	writer.writerow(['HostLast','HostFirst','Notes','LastName','FirstName','CollegeName','Matr','Selection','Table','Ticket',
						'Email','Cell','Survey','Comment','CheckedIn'])
	event = db.Events[event_id]

	rows = db((db.Reservations.Event==event_id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).select(
			left = db.Members.on(db.Members.id==db.Reservations.Member),
			orderby=db.Members.Lastname|db.Members.Firstname|~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname)

	for row in rows:
		ticket = db.Event_Tickets[row.Reservations.Ticket_] if row.Reservations.Ticket_ else None
		ticket_name = ticket.Short_name or ticket.Ticket if ticket else ''
		selection = db.Event_Selections[row.Reservations.Selection_] if row.Reservations.Selection_ else None
		selection_name = selection.Short_name or selection.Selection if selection else ''
		survey = db.Event_Survey[row.Reservations.Survey_] if row.Reservations.Survey_ else ''
		survey_name = survey.Short_name or survey.item if survey else ''
		writer.writerow([row.Members.Lastname, row.Members.Firstname, row.Reservations.Notes or '',
							row.Reservations.Lastname, row.Reservations.Firstname, row.Reservations.Affiliation.Name if row.Reservations.Affiliation else '',
							primary_matriculation(row.Reservations.Member) or '' if row.Reservations.Host==True else '',
							selection_name, row.Reservations.Table or '', ticket_name,
							primary_email(row.Reservations.Member) if row.Reservations.Host==True else '',
							row.Members.Cellphone if row.Reservations.Host==True else '',
							survey_name, row.Reservations.Comment or '',
							'✔' if row.Reservations.Checked_in else ''])
	return locals()
	
@action('event_copy/<event_id:int>', method=['GET'])
@preferred
@checkaccess('write')
def event_copy(event_id):
	event = db.Events[event_id]
	tickets = db(db.Event_Tickets.Event==event_id).select()
	selections = db(db.Event_Selections.Event==event_id).select()
	survey = db(db.Event_Survey.Event==event_id).select()
	new_event_id = db.Events.insert(Page=event.Page, Description='Copy of '+event.Description, DateTime=event.DateTime,
				Booking_Closed=event.Booking_Closed, Details=event.Details, Members_only=event.Members_only, Hidden=event.Hidden,
				Allow_join=event.Allow_join, Guest=event.Guests, Sponsors=event.Sponsors, Venue=event.Venue,
				Capacity=event.Capacity, Speaker=event.Speaker, Notes=event.Notes, Comment=event.Comment)
	for t in tickets:
		db.Event_Tickets.insert(Event=new_event_id, Ticket=t.Ticket, Price=t.Price, Count=t.Count,
					Qualify=t.Qualify, Allow_as_guest=t.Allow_as_guest, Short_name=t.Short_name)
	for s in selections:
		db.Event_Selections.insert(Event=new_event_id, Selection=s.Selection, Short_name=s.Short_name)
	for s in survey:
		db.Event_Survey.insert(Event=new_event_id, Item=s.Item)

	flash.set("Please customize the new event.")
	redirect(URL('events', vars=dict(referrer=request.query.referrer, mode='edit', id=new_event_id)))
	
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
	
@action('pages', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def pages():
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')

	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.url
	page_id = int(parsed['record_id'] or 0)

	header = CAT(H5('Pages'), "Public Website Pages.", XML('<br>'),
			  "There may be multiple page trees, the root pages are shown first.", XML('<br>'),
			  "Order of modification controls the ordering of both grid and menus.", XML('<br>'),
			  "Tree roots appear on the Nav Bar, with their children in a dropdown menu.")

	if parsed['mode']!='select':
		if parsed['mode']=='new':
			header = CAT(A('back', _href=back), H5('New Public Page'))
		else:
			page = db.Pages[page_id]
			if page.Content:
				urlpage = "web"
				if page.Root:
					urlpage += f"/{page_name(page.Root).replace('_', ' ')}"
				if page.Parent:
					urlpage += f"/{page_name(page.Parent).replace('_', ' ')}"
				urlpage += f"/{page.Page.replace('_', ' ')}"
				urlpage = URL(urlpage, scheme=True)
			else:
				urlpage = page.Link
			header = CAT(A('back', _href=back), H5('Page Record'),
						"Public page is ", A(urlpage, _href=urlpage), XML('<br>')
			)

	def validation(form):
		if not (form.vars.get('Link') or form.vars.get('Content')):
			form.errors['Content']="Please provide either an external link or Content"
		if form.vars.get('Hide') and not form.vars.get('Root'):
			form.errors['Hide']="Root pages should not be hidden"

		if form.vars.get('Parent'):
			parent = db.Pages[form.vars.get('Parent')]
			if parent.Parent:
				form.errors['Parent']="Only 2 levels of nesting are allowed"
			if form.vars.get('Parent')==form.vars.get('Root'):
				form.errors['Parent']="Parent should not be the same as Root"
			if parent.Root != int(form.vars.get('Root')):
				form.errors['Parent']="Parent should be in the same tree as Root"
		
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		
	trees = {r.Page.lower(): [r.id]+[s.id for s in db(db.Pages.Root==r.id).select(db.Pages.id)] for r in db(db.Pages.Root==None).select(db.Pages.id, db.Pages.Page)}

	grid = Grid(db.Pages.id>0,
			orderby=db.Pages.Root|db.Pages.Modified,
			columns=[db.Pages.Page, db.Pages.Root_name, db.Pages.Parent_name, db.Pages.Hide, db.Pages.Link, db.Pages.Views],
			search_queries=[["Tree", lambda value: db.Pages.id.belongs(trees.get(value.lower(), []))],
							["Page", lambda value: db.Pages.Page.contains(value)],
							["Content", lambda value: db.Pages.Content.contains(value)]],
			details=not write, editable=write, create=write,
			deletable=lambda r: write,
			validation=validation,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

@action('web/<root>', method=['GET'])
@action('web/<root>/<branch>', method=['GET'])
@action('web/<root>/<branch>/<twig>', method=['GET'])
@preferred_public
def web(root, branch=None, twig=None):
	page = db(db.Pages.Page.ilike((twig or branch or root).replace('_', ' '))).select().first()
	if not page:
		abort(404)
	page.update_record(Views = page.Views+1, Modified=page.Modified)
	if not page.Content:
		redirect(page.Link)
	menu = pages_menu(page)	#for layout_publc.html
	content = template_expand(page.Content)
	header = XML(markdown.markdown(content))
	return locals()
	
@action('get_date_range', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def get_date_range():
# vars:	function: controller to be given the date range
#		title: heading for date range screen
	access = session.access	#for layout.html
	today = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	year_ago = today - dateutil.relativedelta.relativedelta(years=1) + datetime.timedelta(days=1)
	prev_year_begin = datetime.date(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year-1, 1, 1)
	prev_year_end = datetime.date(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year-1, 12, 31)

	header=H5(f"{request.query.function.replace('_', ' ').capitalize()}")		

	def checkform(form):
		if form.vars.start > form.vars.end:
			form.errors['end']= 'end should not be before start!'
		
	form=Form(
		[Field('start', 'date', requires=[IS_NOT_EMPTY(),IS_DATE()], label='Start Date',
			default = prev_year_begin if request.query.function=='tax_statement' else year_ago.date()),
		Field('end', 'date', requires=[IS_NOT_EMPTY(),IS_DATE()], label='End Date',
			default = prev_year_end if request.query.function=='tax_statement' else today.date())]
	)
	
	if form.accepted:
		redirect(URL(f"{request.query.function}/{form.vars.get('start')}/{form.vars.get('end')}"))
	return locals()

@action('financial_detail/<event:int>', method=['GET'])
@preferred
@checkaccess('accounting')
def financial_detail(event, title=''):
	access = session['access']	#for layout.html
	title = request.query.get('title')
	

	header = CAT(A('back', _href=request.query.back), H5(f'{request.query.title}'),
			financial_content(event if event!=0 else None, request.query.query, request.query.left))
	return locals()
	
@action('financial_statement/<start>/<end>', method=['GET'])
@preferred
@checkaccess('accounting')
def financial_statement(start, end):
	access = session.access	#for layout.html
	startdatetime = datetime.datetime.fromisoformat(start)
	enddatetime = datetime.datetime.fromisoformat(end)+datetime.timedelta(days=1)
	title = f"Financial Statement for period {start} to {end}"
	acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first().id
		
	header = CAT(H5(title), H6('Assets'))

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
		prepaidafter = (date_time + datetime.timedelta(days=365)).date()
		prepaid = 0
		refs = []

		rows = db((db.AccTrans.Account==acdues)&(db.AccTrans.Amount>0)&(db.AccTrans.Member!=None)).select(
			db.AccTrans.ALL, db.Members.Paiddate, db.Members.Pay_next, db.Members.Lastname, db.Members.Firstname,
			left = db.Members.on(db.AccTrans.Member==db.Members.id),
			orderby = db.AccTrans.Member|~db.AccTrans.Timestamp
		)

		l = None
		end = 0
		for r in rows:
			if not l or l.AccTrans.Member != r.AccTrans.Member:
				end = r.Members.Paiddate

			if not end:		#some historical records missing Paiddate, assume 1yr membership
				end = r.AccTrans.Timestamp.date() + datetime.timedelta(365)
			if end > prepaidafter and r.AccTrans.Timestamp < date_time:
				prepaid += r.AccTrans.Amount*(end - prepaidafter).days/(end - r.AccTrans.Timestamp.date()).days
				refs.append(r.AccTrans.id)
			end = r.AccTrans.Paiddate

			l = r
		return (prepaid, f"db.AccTrans.id.belongs({str(refs)})", None)
	
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
	header = CAT(header, TABLE(*rows))

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
	header = CAT(header, H6('\nLiabilities'), TABLE(*rows))
	
	transfer = db(db.CoA.Name.ilike('Transfer')).select().first().id	#ignoretransfertransactions
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
		rows.append(TR(TD(A(name, _href=URL(f'financial_detail/{e.AccTrans.Event or 0}', 
						vars=dict(title=title, query=query, left=left, back=request.url)),
						_style='white-space: normal')), 
		 				TD(date), tdnum(rev), tdnum(exp), tdnum(rev + exp)))
		totrev += rev
		totexp += exp
	rows.append(THEAD(TR(TH('Total'), TH(''), tdnum(totrev, th=True),
			  tdnum(totexp, th=True), tdnum(totrev+totexp, th=True))))
	header = CAT(header, H6('\nAdmin & Event Cash Flow'), TABLE(*rows))
	return locals()
	
@action('tax_statement/<start>/<end>', method=['GET'])
@preferred
@checkaccess('accounting')
def tax_statement(start, end):
	access = session.access	#for layout.html
	startdatetime = datetime.datetime.fromisoformat(start)
	enddatetime = datetime.datetime.fromisoformat(end)+datetime.timedelta(days=1)
	title = f"Financial Statement (cash based) for period {start} to {end}"
		
	header = CAT(H5(title), H6('Account Balances'))

	sumamt = db.AccTrans.Amount.sum()
	sumfee = db.AccTrans.Fee.sum()
	tktacct = db(db.CoA.Name.ilike('Ticket sales')).select().first().id
	sponacct = db(db.CoA.Name.ilike('Sponsorships')).select().first().id
	xferacct = db(db.CoA.Name.ilike('Transfer')).select().first().id	#ignore transfer transactions

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
	header = CAT(header, TABLE(*rows))

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

		rows.append(TR(TD(A(e.Description[0:25], _href=URL(f'financial_detail/{e.id}',
							vars=dict(title=title, query=query, left=left, back=request.url)))),
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
	header = CAT(header, H6('Events'), TABLE(*rows))

	header = CAT(header, financial_content(None, query, left))
	return locals()
		
@action('accounting', method=['POST', 'GET'])
@preferred
@checkaccess('accounting')
def accounting():
	access = session.access	#for layout.html

	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.url
	bank_id = int(parsed['record_id'] or 0)

	header = H5('Banks')

	if parsed['mode']=='select':
		header = CAT(header,
		   		A('Financial Statement', _href=URL('get_date_range', vars=dict(function='financial_statement'))), XML('<br>'),
		   		A('Tax Statement', _href=URL('get_date_range', vars=dict(function='tax_statement'))), XML('<br>'),
		   		A('All Transactions', _href=URL('transactions', vars=dict(back=back,
					query="db.AccTrans.id>0"))), XML('<br>'),
				"Use Upload to load a file you've downloaded from bank/payment processor into accounting")
	else:
		header = A('back', _href=back)
		if parsed['mode']!='new':
			header = CAT(header, XML('<br>'), A('transaction rules',
								 	_href=URL(f"bank_rules/{bank_id}", vars=dict(back=back))))
		header = CAT(header, H5('Bank Account'))		

	grid = Grid(db.Bank_Accounts.id>0,
				orderby=db.Bank_Accounts.Name,
				columns=[db.Bank_Accounts.Name,
		 			Column('Accrued', lambda row: bank_accrual(row.id)),
		 			db.Bank_Accounts.Balance,
					Column('', lambda row: A('Upload', _href=URL(f'bank_file/{row.id}'))),
					Column('', lambda row: A('Transactions', _href=URL('transactions',
								vars=dict(query=f"db.AccTrans.Bank=={row.id}",
				  					back=back)))),
				],
				deletable=False, details=False, editable=True, create=True,
				grid_class_style=grid_style, search_queries=[],
				formstyle=form_style,
	)		
	return locals()
	
@action('bank_rules/<bank_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('read')
def bank_rules(bank_id):
# .../bank_rules/bank_id/...
	access = session.access	#for layout.html
	write = ACCESS_LEVELS.index(session.access) >= ACCESS_LEVELS.index('write')

	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back

	bank=db.Bank_Accounts[bank_id]
	db.bank_rules.bank.default=bank.id
	db.bank_rules.csv_column.requires = [IS_NOT_EMPTY(), IS_IN_SET(bank.Csvheaders.split(','))]

	header = CAT(A('back', _href=back),
		  		H5('Bank Transaction Rules'),
		  		H6(bank.Name))

	def rules_validated(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

	grid = Grid(db.bank_rules.bank==bank_id,
			columns=[db.bank_rules.csv_column, db.bank_rules.pattern, db.bank_rules.account],
			details=not write, editable=write, create=write, deletable=write,
			validation=rules_validated, search_queries=[],
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

@action('bank_file/<bank_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess('accounting')
def bank_file(bank_id):
#upload and process a csv file from a bank or payment processor
#	.../bank_id		bank_id is reference to bank in Bank Accounts
	access = session.access	#for layout.html
	bank = db.Bank_Accounts[bank_id]
	rules = db(db.bank_rules.bank==bank.id).select()
	bkrecent = db((db.AccTrans.Bank==bank.id)&(db.AccTrans.Accrual!=True)).select(orderby=~db.AccTrans.Timestamp, limitby=(0,1)).first()
	unalloc = db(db.CoA.Name.ilike('Unallocated')).select().first()
	origin = 'since account start'

	header = CAT(A('back', _href=URL('accounting')),
				H5(f"Upload {bank.Name} Transactions"),
				XML(markdown.markdown(f"To download data since **{str(bkrecent.Timestamp.date()) if bkrecent else origin}**:")),
				A('Login to Society Account', _href=bank.Bankurl, _target='blank'), XML('<br>'),
				XML(f"{markdown.markdown(bank.HowTo)}"))
	
	footer = f"Current Balance = {f'{CURRENCY_SYMBOL}{bank.Balance:8.2f}'}"
	
	form = Form([Field('downloaded_file', 'upload', uploadfield = False),
				Field('override', 'boolean', comment = ' tick to accept new transactions unconditionally, e.g. for new bank')],
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
		f = StringIO(form.vars.get('downloaded_file').file.read().decode(encoding='utf-8'))
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
			
		if overlap == False and not form.vars.get('override'):
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
			for r in rules:
				value = row[r.csv_column]
				if value and r.pattern in value:	#rule applies
					account = r.account
			
			stored = stored + 1
			bank.update_record(Balance = (bank.Balance or 0) + amount + fee)

			if checknumber:		#see if there is an accrued and possibly split entry
				rows = db((db.AccTrans.Accrual==True)&(db.AccTrans.Bank==bank.id)&(db.AccTrans.CheckNumber==checknumber)).select()
				accrued=0
				for trans in rows:
					accrued+=trans.Amount
				if accrued==amount:
					for trans in rows:
						trans.update_record(Accrual=False, Timestamp=timestamp, Reference=reference)
					continue	#on to next transaction
			else:	#try to identify charges
				try:
					amount, details = paymentprocessor(bank.Name.lower()).process_charge(row, bank, reference, timestamp, amount, fee)
					if amount==0:
						continue
					if notes != details:
						notes = f"{details} {notes}"
				except Exception as e:
					pass	#if fails, leave unallocated
				#Check for matching accrued charge
				rows = db((db.AccTrans.Accrual==True)&(db.AccTrans.Bank==bank.id)).select()
				for trans in rows:
					if trans.Amount == amount:
						trans.update_record(Accrual=False, Timestamp=timestamp, Reference=reference)
						amount = 0
						break
				if amount==0:
					continue	#on to next transaction
				
			db.AccTrans.insert(Bank = bank.id, Account = account, Amount = amount,
					Fee = fee if fee!=0 else None, Timestamp = timestamp,
					CheckNumber = checknumber, Reference = reference, Accrual = False, Notes = notes)
			if account==unalloc.id: unmatched += 1
								
		flash.set(f'{stored} new transactions processed, {unmatched} to allocate, new balance = {CURRENCY_SYMBOL}{bank.Balance}')
	except Exception as e:
		flash.set(f"{str(row)}: {str(e)}")
		isok = False
	if isok:
		redirect(URL('transactions', vars=dict(query=f'db.AccTrans.Bank=={bank.id}', back=URL('accounting'))))
	return locals()

@action('transactions', method=['POST', 'GET'])
@preferred
@checkaccess('accounting')
def transactions():
	access = session.access	#for layout.html

	parsed = Grid.parse(request.query)
	back = parsed['referrer'] or request.query.back
	id = int(parsed['record_id'] or 0)

	db.AccTrans.Fee.writable = False
	db.AccTrans.Paiddate.writable = False
	db.AccTrans.Membership.writable = False
	acdues = db(db.CoA.Name.ilike("Membership Dues")).select().first().id
	actkts = db(db.CoA.Name.ilike("Ticket sales")).select().first().id
	query = request.query.query or '(db.AccTrans.id>0)'
	if request.query.get('account'):
		query += f"&(db.AccTrans.Account=={request.query.get('account')})"
	if request.query.get('member'):
		query += f"&(db.AccTrans.Member=={request.query.get('member')})"
	if request.query.get('event'):
		query += f"&(db.AccTrans.Event=={request.query.get('event')})"
	if request.query.get('notes'):
		query += f"&(db.AccTrans.Notes.ilike('%{request.query.get('notes')}%'))"
	if request.query.get('reference'):
		query += f"&(db.AccTrans.Reference.ilike('%{request.query.get('reference')}%'))"
			
	search_form=Form([
		Field('account', 'reference CoA', default=request.query.get('account'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'CoA', '%(Name)s', zero="account?"))),
		Field('member', 'reference Members', default=request.query.get('member'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Members', '%(Lastname)s, %(Firstname)s',
				orderby = db.Members.Lastname|db.Members.Firstname, zero="member?"))),
		Field('event', 'reference Events', default=request.query.get('event'),
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Events',
				lambda r: f"{r.DateTime.strftime(DATE_FORMAT)} {r.Description[:25]}",
				orderby = ~db.Events.DateTime, zero="event?"))),
		Field('notes', 'string',
		   		widget=lambda field, value: INPUT(_name='notes', _type='text', _value=request.query.get('notes'), _placeholder="notes?")),
		Field('reference', 'string',
		   		widget=lambda field, value: INPUT(_name='reference', _type='text', _value=request.query.get('reference'), _placeholder="ref?"))],
		keep_values=True, formstyle=FormStyleBulma)

	if parsed['mode']:	#viewing transactions
		bank_id_match=re.match('db.AccTrans.Bank==([0-9]+)$', query)
		session['bank_id'] = int(bank_id_match.group(1)) if bank_id_match else None
		if search_form.accepted:	#Filter button clicked
			select_vars = {}
			if search_form.vars.get('account'):
				select_vars['account'] = search_form.vars.get('account')
			if search_form.vars.get('member'):
				select_vars['member'] = search_form.vars.get('member')
			if search_form.vars.get('event'):
				select_vars['event'] = search_form.vars.get('event')
			if search_form.vars.get('notes'):
				select_vars['notes'] = search_form.vars.get('notes')
			if search_form.vars.get('reference'):
				select_vars['reference'] = search_form.vars.get('reference')
			redirect(URL('transactions', vars=select_vars))
	else:
		if parsed['mode']=='edit' or parsed['mode']=='details':	#editing/viewing AccTrans record
			db.AccTrans.Amount.comment = 'to split transaction, enter amount of a split piece'
			db.AccTrans.CheckNumber.writable = False
			db.AccTrans.CheckNumber.requires = None
			transaction = db.AccTrans[id]
			if transaction.Accrual:
				db.AccTrans.Fee.readable = db.AccTrans.Fee.writable = False
				db.AccTrans.Timestamp.writable=True
			if transaction.Amount>0:
				db.AccTrans.Amount.requires=IS_DECIMAL_IN_RANGE(0, transaction.Amount)
			else:
				db.AccTrans.Amount.requires=IS_DECIMAL_IN_RANGE(transaction.Amount, 0)
		elif parsed['mode']=='new':	#adding AccTrans accrual
			db.AccTrans.Amount.comment='enter full amount of check as a negative number; split using Edit if multiple accounts',
			db.AccTrans.Timestamp.writable=True
			db.AccTrans.Amount.requires=IS_DECIMAL_IN_RANGE(-100000, 0)
			db.AccTrans.Bank.default = session['bank_id']
	
	header = CAT(A('back', _href=back), H5('Accounting Transactions'))

	def validate(form):
		if not form.vars.get('id'): #must be creating an accrual
			return
		new_amount = decimal.Decimal(form.vars.get('Amount'))
		fee = transaction.Fee
		if form.vars.get('Account')==acdues:
			if not form.vars.get('Member'):
				form.errors['Member'] = "Please identify the member"
			elif form.vars.get('Event'):
				form.errors['Event'] = "Membership dues do not associate with an event."
			elif transaction.Account!=acdues and new_amount>0:	#e.g. recording check
				member = db.Members[form.vars.get('Member')]
				valid_dues = False
				for membership in MEMBERSHIPS:
					annual_dues = paymentprocessor().get_dues(membership.category)
					if new_amount == annual_dues*int(new_amount/annual_dues): #this membership category
						transaction.update_record(Paiddate = member.Paiddate, Membership=membership.category)
						if not member.Paiddate or member.Paiddate < datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()+datetime.timedelta(days=GRACE_PERIOD):
							#compute new paiddate & record it and membership category (in case changing Student to Full)
							member.update_record(Paiddate=newpaiddate(member.Paiddate, transaction.Timestamp, years=int(new_amount/annual_dues)),
								Membership=membership.category)
						#else assume member record updated manually when check received
						valid_dues = True
						break
				if not valid_dues:
					form.errors['Amount'] = "not a valid dues payment"
		if form.vars.get('Account')==actkts:
			if not form.vars.get('Member'):
				form.errors['Member'] = "Please identify the member"
			elif not form.vars.get('Event'):
				form.errors['Event'] = "Please identify the event"
			elif transaction.Account!=actkts and new_amount>0:	#e.g. recording check
				tbc = event_unpaid(form.vars.get('Event'), form.vars.get('Member'))
				if not tbc or tbc < new_amount:
					form.errors['Member'] = "Unexpected ticket payment"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return

		if new_amount!=transaction.Amount:	#new split
			if fee:
				fee = (fee*new_amount/transaction.Amount).quantize(decimal.Decimal('0.01'))
			db.AccTrans.insert(Timestamp=transaction.Timestamp, Bank=transaction.Bank,
								Account=transaction.Account, Event=transaction.Event, Member=transaction.Member,
								Amount=transaction.Amount-new_amount, Fee=transaction.Fee - fee if fee else None,
								CheckNumber=transaction.CheckNumber, Accrual=transaction.Accrual,
								 Reference=transaction.Reference,Notes=form.vars.get('Notes'))	#the residual piece
			db.AccTrans[form.vars.get('id')].update_record(Fee=fee)
	
	grid = Grid(eval(query), left=eval(request.query.get('left')) if request.query.get('left') else None,
			orderby=~db.AccTrans.Timestamp,
			columns=[db.AccTrans.Timestamp, db.AccTrans.Account, db.AccTrans.Event,
					Column('member', lambda row: A(member_name(row.Member), _href=URL('members',
											vars=dict(referrer=encode_url(request.url), mode='details'if access=='read' else 'edit', id=row.Member)),
											_style='white-space: normal') if row.Member else '', required_fields=[db.AccTrans.Member]),
	 				db.AccTrans.Amount, db.AccTrans.Fee, db.AccTrans.CheckNumber, db.AccTrans.Accrual],
			headings=['Timestamp', 'Account','Event','Member','Amt', 'Fee', 'Chk#', 'Acc'],
			validation=validate, show_id=True, search_form=search_form,
			deletable=lambda r: r.Accrual, details=False, editable=True, create=session.get('bank_id'),
			field_id=db.AccTrans.id, grid_class_style=grid_style, formstyle=form_style)
	return locals()

@action('composemail', method=['POST', 'GET'])
@preferred
@checkaccess('write')
def composemail():
	access = session.access	#for layout.html
	
	query = request.query.get('query')
	qdesc = request.query.get('qdesc')
	left = request.query.get('left')

	header = CAT(A('back', _href=request.query.get('back')), H5("Send Email"))
	source = society_emails(session.member_id) or [SMTP_TRANS.username]
	
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
		rows = db(eval(query)).select(left=eval(left) if left else None, distinct=True)
		query_count = len(rows)
		row = rows[0]
		header = CAT(header, XML(f'To: {qdesc} ({query_count})'))
		footer = A("Export bcc list for use in email", _href=URL('bcc_export',
						vars=dict(query=query, left=left or '')))
	else:
		fields.append(Field('to', 'list:string',
			comment='Include comma between multiple recipients',
   			requires=[IS_LIST_OF_EMAILS(), IS_NOT_EMPTY()]))
	if not query or query_count==1:
		fields.append(Field('bcc', 'list:string', requires=IS_LIST_OF_EMAILS()))
	subject_default = proto.Subject if proto else ''
	body_default = proto.Body if proto else "[[greeting]]\n\n" if query else ""
	event_id = request.query.get('event_details')
	if event_id:
		event = db.Events[event_id]
		if event.Details:
			body_default = f"[[greeting]]\n\n{event.Details}"
			subject_default = event.Description
	fields.append(Field('subject', 'string', requires=IS_NOT_EMPTY(), default=subject_default))
	fields.append(Field('body', 'text', requires=IS_NOT_EMPTY(), default=body_default,
				comment = CAT(" format using ",
				A('Markdown', _href='https://www.markdownguide.org/basic-syntax/', _target='doc'),
				" and see ",
				A('Useful Tips', _href='https://oxcamne.github.io/oxcam/send_email.html#useful-tips', _target='doc'),
				" for additional formatting.",
				XML('<br>'),
				"There are custom elements [[greeting]], [[member]], [[reservation]], [[registration_link]] ",
				"available, depending on the context.")))
	fields.append(Field('save', 'boolean', default=proto!=None, comment='store/update template'))
	fields.append(Field('attachment', 'upload', uploadfield=False))
	if proto:
		form=''
		fields.append(Field('delete', 'boolean', comment='tick to delete template; sends no message'))

	def validate(form2):
		if form2.vars.get('delete'):
			db(db.EMProtos.id == proto.id).delete()
			flash.set("Template deleted: "+ proto.Subject)
			redirect(request.query.back)
		if not IS_PRODUCTION:
			to = form2.vars.get('to')
			if to:
				for em in to:
					if not em in ALLOWED_EMAILS:
						form2.errors['to'] = f"{em} is not an allowed address in this environment"
			bcc = form2.vars.get('bcc')
			if bcc:
				for em in bcc:
					if not em in ALLOWED_EMAILS:
						form2.errors['bcc'] = f"{em} is not an allowed address in this environment"

	form2 = Form(fields, form_name="message_form", keep_values=True, validation=validate,
					submit_value = 'Send', formstyle=FormStyleBulma)
			
	if form2.accepted:
		try:
			body_expanded = template_expand(form2.vars['body'], locals())
		except Exception as e:
			flash.set(e)
			body_expanded = None

		sender = form2.vars['sender']
		if proto:
			if form2.vars['save']:
				proto.update_record(Subject=form2.vars['subject'],
					Body=form2.vars['body'])
				flash.set("Template updated: "+ form2.vars['subject'])
		else:
			if form2.vars['save']:
				db.EMProtos.insert(Subject=form2.vars['subject'], Body=form2.vars['body'])
				flash.set("Template stored: "+ form2.vars['subject'])

		bcc = form2.vars.get('bcc')

		if form2.vars.get('attachment'):
			attachment = form2.vars.get('attachment').file.read()
			attachment_filename =form2.vars.get('attachment').filename
		else:
			attachment = attachment_filename = None

		if body_expanded:
			if query:
				db.Email_Queue.insert(Subject=form2.vars['subject'], Body=form2.vars['body'], Sender=sender,
			 		Attachment=pickle.dumps(attachment), Attachment_Filename=attachment_filename,
					Bcc=str(bcc), Query=query, Left=left, Qdesc=qdesc,
					Scheme=URL('index', scheme=True).replace('index', ''))
				flash.set(f"email notice sent to '{qdesc}' ({query_count})")
			else:
				to = form2.vars['to']
				body = ''
				flash.set(f"Email sent to: {to} ({len(to)})")
				email_sender(subject=form2.vars['subject'], sender=sender, to=to, bcc=bcc,
				 	body=markdown.markdown(body_expanded), attachment=attachment, attachment_filename=attachment_filename)
			redirect(request.query.back)
	return locals()

@action('bcc_export', method=['GET'])
@action.uses("download.html", db, session, flash, Inject(response=response))
@checkaccess('write')
def bcc_export():
	stream = StringIO()
	content_type = "text/plain"
	filename = 'bcc.txt'
	query = request.query.get('query')
	left = request.query.get('left')
	select_fields = [db.Members.id]
	mailing = re.search(r"Mailings\.contains\((\d+)\)", query)
	if mailing:		#using a mailing list
		select_fields.append(db.Emails.Email)
		select_fields.append(db.Emails.id)
	rows = db(eval(query)).select(*select_fields, left=eval(left) if left else None, distinct=True)
	writer=csv.writer(stream)
	for row in rows:
		email = row.get(db.Emails.Email) or primary_email(row.get(db.Members.id))
		if email:
			writer.writerow([email])
	return locals()

#######################Member Directory linked from Society web site#########################
@action('directory', method=['GET'])
@preferred
@checkaccess(None)
def directory():
	access = session.access	#for layout.html
	if not session.member_id or not member_good_standing(db.Members[session.member_id], datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()):
		flash.set('Sorry, Member Directory is only available to members in good standing.')
		redirect(URL('accessdenied'))
			
	query = "(db.Members.Membership!=None)&(db.Members.Membership!='')"
	header = CAT(H5('Member Directory'),
		  XML(f"You can search by last name, town, state, or college/university using the boxes below; click on a name to view contact information"))

	grid = Grid(eval(query),
		columns=[Column('Name', lambda r: A(f"{member_name(r['id'])}", _href=URL(f"contact_details/{r['id']}",
								vars=dict(back=request.url)), _style="white-space: normal")),
	   			Column('Affiliations', lambda r: member_affiliations(r['id'])),
				db.Members.City, db.Members.State],
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
@preferred
@checkaccess(None)
def contact_details(member_id):
	access = session.access	#for layout.html
	member=db.Members[member_id] if session.member_id else None
	if not member or not member.Membership:
		raise Exception("hack attempt?")
	
	header = CAT(A('back', _href=request.query.back),
				H5("Member Directory - Contact Details"),
		   member_name(member_id), XML('<br>'),
		   member_affiliations(member_id), XML('<br>'))
	email = primary_email(member_id)
	if not member.Privacy and email:
		header = CAT(header, A(email, _href=f"mailto:{email}",_target='email'), XML('<br>'))
	if member.Homephone:
		header = CAT(header, f"home phone: {member.Homephone}", XML('<br>'))
	if member.Workphone:
		header = CAT(header, f"work phone: {member.Workphone}", XML('<br>'))
	header = CAT(header, XML('<br>'))

	if member.Address1:
		header = CAT(header, f"{member.Address1}", XML('<br>'))
	if member.Address2:
		header = CAT(header, f"{member.Address2}", XML('<br>'))
	header = CAT(header, f"{member.City or ''}, {member.State or ''} {member.Zip or ''}")
	return locals()

################################# New Event/Membership Registration Process  ################################
@action('registration', method=['GET', 'POST'])
@action('registration/<event_id:int>', method=['GET', 'POST'])
@preferred
@checkaccess(None)
def registration(event_id=None):	#deal with eligibility, set up member record and affiliation record as necessary
#used for both event booking and join/renewal
	access = session.access	#for layout.html
	db.Members.Created.default = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	db.Reservations.Created.default = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)
	member_id = session.member_id
	if event_id:
		event = db(db.Events.id==event_id).select().first()
		if not event or \
				(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.DateTime and \
	 				not (member_id and event_unpaid(event_id, member_id) > 0)) or \
				(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.Booking_Closed and not event_attend(event_id)):
			flash.set('Event is not open for booking.')
			redirect(URL('my_account'))
		if datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > event.Booking_Closed:
			flash.set('Booking is closed, but you may join the wait list.')
		session['event_id'] = event_id
	else:
		event = None
		if not request.query.get('join_or_renew'):
			session['event_id'] = None
	session['membership'] = None
	session['dues'] = None
			
	affinity = None
	good_standing = False
	clist = collegelist(event.Sponsors if event_id and event.Sponsors else [])
	
	if member_id:
		member = db.Members[member_id]
		good_standing = member_good_standing(member, datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date())
		affinity = db((db.Affiliations.Member==member_id)&db.Affiliations.College.belongs([c[0] for c in clist])).select(
							orderby=db.Affiliations.Modified).first()
		if affinity:
			clist = [(affinity.College, affinity.College.Name)]	#primary affiliation is only choice
		if event_id:	#event reservation
			member_reservation = db((db.Reservations.Event == event_id) & (db.Reservations.Member==member_id)\
										& (db.Reservations.Host==True)).select().first()
			sponsor = affinity and not affinity.College.Oxbridge
			if member_reservation:
				if member_reservation.Checkout:	#checked out but didn't complete payment
					checkout = eval(member_reservation.Checkout)
					if not good_standing:
						#still need dues, so signal
						session['membership'] = checkout.get('membership')
						session['dues'] = str(checkout.get('dues')) if checkout.get('dues') else None
				redirect(URL('reservation'))	#go add guests and/or checkout
			if sponsor or (affinity and affinity.Matr or member.Membership and not affinity) and \
			   		(good_standing or not event.Members_only and not event.Allow_join):
				#members of sponsor organizations, or membership eligible and member in good standing, or 
				#event open to all alums and not offering join option, then no need to gather member information
				#ALSO collect Matr if missing from affinity, and allow approved unaffiliated members
				redirect(URL('reservation', vars=dict(mode='new')))	#go create this member's reservation

		elif request.query.get('mail_lists'):
			redirect(URL(f"emails/Y/{member_id}",vars=dict(back=URL('my_account'))))
		else:		#dues payment or profile update
			if not session.get('membership') and \
					member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)+datetime.timedelta(days=GRACE_PERIOD)).date()):
				redirect(URL('profile')) #edit profile if good standing for at least grace period
			if member.Pay_subs == 'Cancelled':
				member.update_record(Pay_subs = None, Pay_next = None)
	else:
		member = None
		
	header = H5('Event Registration: Your Information' if event 
				else 'Mailing List Registration' if request.query.get('mail_lists')
				else 'Membership Application/Renewal: Your Information')
	if event:
		header = CAT(header, XML(f"Event: {event.Description}<br>When: {event.DateTime.strftime('%A %B %d, %Y %I:%M%p')}<br>Where: {event.Venue}<br><br>"),
XML(f"This event is open to \
{'all alumni of Oxford & Cambridge' if not event.Members_only else f'members of {SOCIETY_SHORT_NAME}'}\
{' and members of sponsoring organizations (list at the top of the Affiliations dropdown)' if event.Sponsors else ''}\
{' and their guests' if not event.Guests or event.Guests>1 else ''}.<br>"))
	elif not request.query.get('mail_lists'):
		header = CAT(header, XML('<br>'.join([f"<b>{m.category} Membership</b> is open to {m.description.replace('<dues>', CURRENCY_SYMBOL+str(paymentprocessor(name=None).get_dues(m.category)))}" for m in MEMBERSHIPS])))

	#gather the person's information as necessary (may have only email)
	fields=[]
	fields.append(Field('firstname', 'string', requires = [IS_NOT_EMPTY(), CLEANUP()],
					default=member.Firstname if member else ''))
	fields.append(Field('lastname', 'string', requires = [IS_NOT_EMPTY(), CLEANUP()],
					default=member.Lastname if member else ''))
	fields.append(Field('affiliation', 'reference Colleges',
			default=affinity.College if affinity else None, 
			requires=IS_IN_SET(clist, zero=None) if affinity else IS_EMPTY_OR(IS_IN_SET(clist,
						zero = 'Please select your sponsoring organization or College/University' if event and event.Sponsors else \
								'Please select your College' if not member or not member.Membership else ''))))
	if not affinity or not affinity.Matr:
		fields.append(Field('matr', 'integer', default = affinity.Matr if affinity else None,
				requires=IS_EMPTY_OR(IS_INT_IN_RANGE(datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year-100,datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).year+1)),
				comment='If Oxford or Cambridge alum, please enter your matriculation year'))

	if event:
		mustjoin = event.Members_only and not event.Sponsors
		if len(MEMBERSHIPS)>0 and (event.Members_only or event.Allow_join) and not good_standing:
			fields.append(Field('join_or_renew', 'boolean', default=mustjoin,
				comment=' this event is restricted to OxCamNE members' if mustjoin else \
					' tick if you are an Oxbridge alum and also wish to join OxCamNE or renew your membership'))
	elif not request.query.get('mail_lists') and len(MEMBERSHIPS)>0:
		fields.append(Field('membership', 'string',
						default=member.Membership if member and member.Membership else '',
						requires=IS_IN_SET([m.category for m in MEMBERSHIPS]),
						zero='please select your membership category'))
		fields.append(Field('notes', 'string'))

	if not member:
		fields.append(Field('please_indicate_how_you_heard_of_us', 'string',
			requires=IS_IN_SET([
				'Internet Search',
				'Word of Mouth',
				'Social Media',
				'University Alumni Web Site',
				'Cambridge in America/Oxford North America',
				'Other'
			])))

	def validate(form):
		if form.vars.get('affiliation') and not db.Colleges[form.vars.get('affiliation')].Oxbridge: #sponsor member
			if form.vars.get('join_or_renew'):
				form.errors['join_or_renew']="You're not eligible to join "+SOCIETY_SHORT_NAME+'!'
			return	#go ahead with sponsor registration
		if not form.vars.get('affiliation') and not (member and member.Membership): #not alum, not approved friend member
			form.errors['affiliation']='please select your affiliation from the dropdown, or contact '+SUPPORT_EMAIL
		if form.vars.get('affiliation') and (not affinity or not affinity.Matr) and not form.vars.get('matr'):
			form.errors['matr'] = 'please enter your matriculation year'
		if event and event.Members_only and form.vars.get('join_or_renew')==False:
			form.errors['join_or_renew'] = 'This event is for members only, please join/renew to attend'
		if form.vars.get('membership'):
			membership = next((m for m in MEMBERSHIPS if m.category==form.vars.get('membership')))
			if membership.qualification and not form.vars.get('notes').strip():
				form.errors['notes'] = membership.qualification
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if not member:
			rows= db(db.Members.Firstname.ilike(form.vars['firstname'].split(' ')[0]+'%')&\
					db.Members.Lastname.ilike(form.vars['lastname'].split(' ')[0]+'%')).select(
				db.Members.Firstname, db.Members.Lastname, db.Members.id, db.Emails.Email, db.users.remote_addr,
				left=(db.Emails.on(db.Emails.Member==db.Members.id),
					db.users.on(db.users.email==db.Emails.Email)
					),
				)
			if len(rows)>0:
				suggest = " or ".join([r.Emails.Email for r in rows.find(lambda r: r.users.remote_addr==request.remote_addr)])
				support = f'<a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>'
				flash.set(f"It looks as if you may have an existing record under another email. \
Please login with the email you used before{f'<em>, possibly {suggest}, </em>' if len({suggest})>0 else ''} or contact {support}.", sanitize=False)
				redirect(URL('login', vars=dict(url=request.url)))

	form = Form(fields, validation=validate, formstyle=FormStyleBulma, keep_values=True)
		
	if form.accepted:
		notes = f"{datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).strftime(DATE_FORMAT)} {form.vars.get('notes')}" if form.vars.get('notes') else ''
		if member:

			if member.Notes:
				notes = member.Notes+'\n'+notes
				
			member.update_record(Firstname = form.vars['firstname'], Notes=notes,
							Lastname = form.vars['lastname'])
		else:
			set_access = 'admin' if db(db.Members.id>0).count() == 0 else None
			member_id = db.Members.insert(Firstname = form.vars['firstname'].strip(), 
							Lastname = form.vars['lastname'].strip(), Notes=notes, Access = set_access,
							Source = form.vars.get('please_indicate_how_you_heard_of_us'))
			member = db.Members[member_id]
			session.member_id = member_id
			session.access = set_access
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
			flash.set("Please review your subscription settings below.")
			redirect(URL(f"emails/Y/{member_id}",vars=dict(back=URL('my_account'))))
				
		if request.query.get('join_or_renew') or not event:	#collecting dues with event registration, or joining/renewing
			#membership dues payment
			#get the subscription plan id (Full membership) or 1-year price (Student) from Stripe Products
			session['dues'] = str(paymentprocessor(member.Pay_source).get_dues(form.vars.get('membership')))
			session['membership'] = form.vars.get('membership')
			#ensure the default mailing list subscriptions are in place in the primary email
			email = db(db.Emails.Member==member.id).select(orderby=~db.Emails.Modified).first()
			mailings = email.Mailings or []
			for list in db(db.Email_Lists.Member==True).select():
				if list.id not in mailings:
					mailings.append(list.id)
			email.update_record(Mailings=mailings)
		
		if event:
			redirect(URL('reservation', vars=dict(mode='new')))	#go create this member's reservation
		else:	#joining or renewing
			if not member.Paiddate or member.Paiddate < (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)-datetime.timedelta(GRACE_PERIOD)).date():
				#new/reinstated member, gather additional profile information
				flash.set("Next, please review/complete your directory profile")
				redirect(URL('profile')) #gather profile info
			if session.get('event_id'):
				redirect(URL('reservation', vars=dict(mode='new')))	#go create this member's reservation
			paymentprocessor().checkout(request.url)
	return locals()
	
######################################## Join/Renew/Profile Update ######################################
@action('profile', method=['GET', 'POST'])
@preferred
@checkaccess(None)
def profile():
	access = session.access	#for layout.html
	if not session.member_id:
		redirect(URL('my_account'))

	
	member = db.Members[session.member_id]

	header = H5('Profile Information')
	if member.Paiddate:
		header = CAT(header,
		   XML(f"Your membership {'expired' if member.Paiddate < datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date() else 'expires'} on {member.Paiddate.strftime(DATE_FORMAT)}"))
	if member.Pay_next:
		header = CAT(header, XML(f" Renewal payment will be charged on {member.Pay_next.strftime(DATE_FORMAT)}."))
	header = CAT(header,
		  XML(f"{'<br><br>' if member.Paiddate else ''}The information on this form, except as noted, is included \
in our online Member Directory which is available through our home page to \
all members in good standing. Fields marked * are required.<br><br>\
You can use this screen at any time to update your information (it can be \
reached by using the join/renew link on our home page).<br>\
{A('Review or Edit your college affiliation(s)', _href=URL(f'affiliations/Y/{member.id}', vars=dict(back=request.url)))}<br>\
{A('Manage your email address(es) and mailing list subscriptions', _href=URL(f'emails/Y/{member.id}',vars=dict(back=request.url)))}<br>"))
	
	db.Members.Membership.readable = db.Members.Paiddate.readable = db.Members.Pay_cust.readable = False
	db.Members.Pay_subs.readable = db.Members.Pay_next.readable = db.Members.Charged.readable = False
	db.Members.Access.readable = db.Members.Committees.readable = db.Members.President.readable = False
	db.Members.Notes.readable = db.Members.Created.readable = db.Members.Modified.readable = False
	db.Members.Membership.writable = db.Members.Paiddate.writable = db.Members.Pay_cust.writable = False
	db.Members.Pay_subs.writable = db.Members.Pay_next.writable = db.Members.Charged.writable = False
	db.Members.Access.writable = db.Members.Committees.writable = db.Members.President.writable = False
	db.Members.Notes.writable = db.Members.Created.writable = db.Members.Modified.writable = False
	db.Members.Pay_source.writable = db.Members.Pay_source.readable = False

	db.Members.City.requires = IS_NOT_EMPTY(error_message='please enter your city/town')
	db.Members.State.requires = IS_MATCH('^[A-Z][A-Z]$', error_message='please enter 2 letter state code')
	db.Members.Zip.requires = IS_NOT_EMPTY(error_message='please enter your postal zip')

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
				redirect(URL('reservation', vars=dict(mode='new')))	#go create this member's reservation
			paymentprocessor().checkout(request.url)
		flash.set('Thank you for updating your profile information.')
		notify_support(member.id, 'Member Profile Updated', member_profile(member))
	
	return locals()
	
@action('cancel_subscription/<member_id:int>', method=['POST', 'GET'])
@preferred
@checkaccess(None)
def cancel_subscription(member_id=None):
	access = session.access	#for layout.html
	
	if not session.member_id:
		redirect(URL('my_account'))

	if member_id!=session.member_id and (not session.access or ACCESS_LEVELS.index(session.access) < ACCESS_LEVELS.index('write')):
		redirect(URL('accessdenied'))

	member = db.Members[member_id or session.member_id]
	if not (member and member_good_standing(member, (datetime.datetime.now(TIME_ZONE).replace(tzinfo=None)-datetime.timedelta(days=GRACE_PERIOD)).date())):
		raise Exception("perhaps Back button or mobile auto re-request?")
	
	header = CAT(A('back', _href=request.query.back), XML('<br>'),
			H5('Membership Cancellation'),
			H6(member_name(member.id)),
			XML(f"{'Provided the member has requested cancellation' if member_id!=session.member_id else 'We are very sorry to lose you as a member. If you must leave'}, please click the button to confirm!.<br><br>"))
	
	form = Form([], submit_value='Cancel Subscription')
	
	if form.accepted:
		paymentprocessor(member.Pay_source).cancel_subscription(member)
		member.update_record(Pay_subs = 'Cancelled', Pay_next=None)
		#if we simply cleared Pay_subs then the daily backup daemon might issue membership reminders!
		if not member.Paiddate:	#just joined but changed their mind?
			member.update_record(Membership=None, Charged=None)

		effective = max(member.Paiddate or datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date(), datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()).strftime(DATE_FORMAT)
		notification(member, 'Membership Cancelled', f'Your membership is cancelled effective {effective}.<br>Thank you for your past support of the Society.')
		flash.set(f"{member_name(member.id) if member_id else 'your'} membership is cancelled effective {effective}.")
		redirect(request.query.back)
	return locals()
