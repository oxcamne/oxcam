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

from py4web import action, request, response, abort, redirect, URL, Field, DAL
from yatl.helpers import *
from .common import db, session, T, cache, auth, logger, authenticated, unauthenticated, flash
from .settings_private import *
from .models import *
from py4web.utils.grid import Grid, GridClassStyleBulma, Column, GridClassStyleBootstrap5, GridClassStyle
from py4web.utils.form import Form, FormStyleBulma, FormStyleBootstrap4, FormStyleDefault
from pydal.validators import *
from py4web.utils.factories import Inject
import datetime, random, re, markmin, stripe, csv, decimal, io
from io import StringIO

grid_style = GridClassStyleBootstrap5
form_style = FormStyleBootstrap4

class GridActionButton:
    def __init__(
        self,
        url,
        text=None,
        icon=None,
        additional_classes="",
        message="",
        append_id=False,
        ignore_attribute_plugin=False,
    ):
        self.url = url
        self.text = text
        self.icon = icon
        self.additional_classes = additional_classes
        self.message = message
        self.append_id = append_id
        self.ignore_attribute_plugin = ignore_attribute_plugin
	
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
			session['url_prev'] = session.get('url')
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
	left = None #only used if mailing list with excluded event attendees
	qdesc = ""
	errors = ''
	header = DIV(H5('Member Records'))
	back = URL('members/select', scheme=True)

	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	admin = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('admin')
	if not admin:
		db.Members.Access.writable = False
	db.Members.City.requires=db.Members.State.requires=db.Members.Zip.requires=None
	db.Members.Name.readable = False
	db.Members.Affiliations.readable = False

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
		db.Members.Name.readable = True
		db.Members.Affiliations.readable = True
		if len(search_form.vars) == 0:
			search_form.vars = session.get('member_filter') or {}
		else:
			member_filter=dict(mailing_list=search_form.vars.get('mailing_list'),
						event=search_form.vars.get('event'),
						field=search_form.vars.get('field'),
						value=search_form.vars.get('value')) if len(search_form.vars)>0 else {}
			if search_form.vars.get('good_standing'):
				member_filter['good_standing'] = 'On'
			session['member_filter'] = member_filter
		header = CAT(header, A("Send Email to Specific Address(es)", _href=URL('composemail', vars=dict(back=back))), XML('<br>'))
	elif path:
		back = session.get('back') or back
		header = CAT(A('back', _href=back), H5('Member Record'))
		if path.startswith('edit'):
			header= CAT(header,
	       			A('Member reservations', _href=URL('member_reservations', path[5:])), XML('<br>'),
					A('OxCam affiliation(s)', _href=URL('affiliations', path[5:])), XML('<br>'),
					A('Email addresses and subscriptions', _href=URL('emails', path[5:])), XML('<br>'),
					A('Dues payments', _href=URL('dues', path[5:])), XML('<br>'),
					A('Send Email to Member', _href=URL('composemail',
					 	vars=dict(query=f"db.Members.id=={path[5:]}", left='',
		 					qdesc=member_name(path[5:]),
		   					back=URL(f'members/edit/{path[5:]}', scheme=True)))))
	else:
		session['back'] = None
		session['member_filter'] = None
		redirect(URL('members/select'))

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
	
	if path=='select':
		if qdesc:
			header = CAT(header,
				A(f"Send Notice to {qdesc}", _href=URL('composemail',
					vars=dict(query=query, left=left or '', qdesc=qdesc, back=back))), XML('<br>'))
		header = CAT(header,
	       XML("Use filter to select a mailing list or apply other filters.<br>Selecting an event selects \
(or excludes from a mailing list) attendees.<br>You can filter on a member record field \
using an optional operator (=, <, >, <=, >=) together with a value."))
		footer = A("Export selected records as CSV file", _href=URL('members_export',
						vars=dict(query=query, left=left or '', qdesc=qdesc)))

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
		
		db.Members[form.vars.get('id')].update_record(Modified = datetime.datetime.now())
		if form.vars.get('Paiddate'):
			dues = db(db.Dues.Member == form.vars.get('id')).select(orderby=~db.Dues.Date).first()
			if dues:
				dues.update_record(Nowpaid = form.vars.get('Paiddate'))

	grid = Grid(path, eval(query), left=eval(left) if left else None,
	     	orderby=db.Members.Lastname|db.Members.Firstname,
			columns=[db.Members.Name,
	    			db.Members.Membership, db.Members.Paiddate,
					db.Members.Affiliations,
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

@action('member_reservations/<member_id:int>', method=['POST', 'GET'])
@action('member_reservations/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def member_reservations(member_id, path=None):
# .../member_reservations/member_id/...
	db.Reservations.Member.readable=False

	header = CAT(A('back', _href=URL(f'members/edit/{member_id}', scheme=True)),
				H5('Member Reservations'),
	      		H6(member_name(member_id)),
				A('Add New Reservation', _href=URL(f'add_member_reservation/{member_id}', scheme=True)))

	pre_action_buttons = [GridActionButton(lambda row: URL(f"reservation/{member_id}/{row.Reservations.Event}"), text='Edit', append_id=False)]

	grid = Grid(path, (db.Reservations.Member==member_id)&(db.Reservations.Host==True),
			left=db.Events.on(db.Events.id == db.Reservations.Event),
			orderby=~db.Events.DateTime,
			pre_action_buttons=pre_action_buttons,
			columns=[db.Reservations.Member, db.Events.DateTime, db.Reservations.Event, db.Reservations.Wait,
					db.Reservations.Conf, db.Reservations.Cost,
					db.Reservations.Paid, db.Reservations.Charged, db.Reservations.TBC],
			grid_class_style=grid_style,
			formstyle=form_style,
			details=False, editable = False, create = False, deletable = False)
	return locals()
	
@action('add_member_reservation/<member_id:int>', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess('write')
def add_member_reservation(member_id):
	header = CAT(A('back', _href=URL(f'members/edit/{member_id}', scheme=True)),
	      		H5('Add New Reservation'),
	      		H6(member_name(member_id)),
				)

	form=Form([Field('event', 'reference db.Events',
		  requires=IS_IN_DB(db, 'Events', '%(Description)s', orderby = ~db.Events.DateTime,
		      				zero='Please select event for new reservation from dropdown.'))],
		formstyle=FormStyleBulma)
	
	if form.accepted:
		redirect(URL(f"reservation/{member_id}/{form.vars.get('event')}"))
	return locals()

@action('affiliations/<member_id:int>', method=['POST', 'GET'])
@action('affiliations/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def affiliations(member_id, path=None):
# .../affiliations/member_id/...
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	db.Affiliations.Member.default=member_id

	header = CAT(A('back', _href=URL(f'members/edit/{member_id}', scheme=True)),
	      		H5('Member Affiliations'),
	      		H6(member_name(member_id)))
	footer = "Multiple affiliations are listed in order modified. The topmost one \
is used on name badges etc."

	def affiliation_modified(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id')):
			db.Affiliations[form.vars.get('id')].update_record(Modified = datetime.datetime.now())

	grid = Grid(path, db.Affiliations.Member==member_id,
	     	orderby=db.Affiliations.Modified,
			columns=[db.Affiliations.College, db.Affiliations.Matr, db.Affiliations.Notes],
			details=not write, editable=write, create=write, deletable=write,
			validation=affiliation_modified,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()
	
#update Stripe Customer Record with current primary email
def update_Stripe_email(member):
	if member.Stripe_id:
		pk = STRIPE_PKEY	#use the public key on the client side	
		stripe.api_key = STRIPE_SKEY
		try:	#check customer still exists on Stripe
			cus = stripe.Customer.retrieve(member.Stripe_id)
			stripe.Customer.modify(member.Stripe_id, email=primary_email(member.id))
		except Exception as e:
			member.update_record(Stripe_id=None, Stripe_subscription=None, Stripe_next=None)
	
@action('emails/<member_id:int>', method=['POST', 'GET'])
@action('emails/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def emails(member_id, path=None):
# .../emails/member_id/...
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	db.Emails.Member.default=member_id

	header = CAT(A('back', _href=URL(f'members/edit/{member_id}', scheme=True)),
	      		H5('Member Emails'),
	      		H6(member_name(member_id)))
	footer = "Note, the most recently edited (topmost) email is used for messages \
directed to the individual member, and appears in the Members Directory. Notices \
are sent as specified in the Mailings Column."

	def email_modified(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id')):
			db.Emails[form.vars.get('id')].update_record(Modified = datetime.datetime.now())
			update_Stripe_email(db.Members[form.vars.get('id')])

	grid = Grid(path, db.Emails.Member==member_id,
	     	orderby=~db.Emails.Modified,
			columns=[db.Emails.Email, db.Emails.Mailings],
			details=not write, editable=write, create=write, deletable=write,
			validation=email_modified,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()

def newpaiddate(paiddate, timestamp=datetime.datetime.now(), graceperiod=GRACE_PERIOD):
#within graceperiod days of expiration is treated as renewal if renewed by check, or if student subscription.
#auto subscription will start from actual date
	basedate = timestamp.date() if not paiddate or paiddate<datetime.datetime.now().date()-datetime.timedelta(days=graceperiod) else paiddate
	if basedate.month==2 and basedate.day==29: basedate -= datetime.timedelta(days=1)
	return datetime.date(basedate.year+1, basedate.month, basedate.day)
	
@action('dues/<member_id:int>', method=['POST', 'GET'])
@action('dues/<member_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def dues(member_id, path=None):
# .../dues/member_id/...
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	db.Dues.Member.default=member_id

	member=db.Members[member_id]
	db.Dues.Member.default=member.id
	db.Dues.Status.default=member.Membership
	db.Dues.Prevpaid.default = member.Paiddate
	db.Dues.Nowpaid.default = newpaiddate(member.Paiddate)

	header = CAT(A('back', _href=URL(f'members/edit/{member_id}', scheme=True)),
	      		H5('Member Dues'),
	      		H6(member_name(member_id)))

	def dues_validated(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (not form.vars.get('id')): 	#adding dues record
			member.update_record(Membership=form.vars.get('Status'), Paiddate=form.vars.get('Nowpaid'), Modified=datetime.datetime.now(),
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
	
@action('events', method=['POST', 'GET'])
@action('events/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def events(path=None):
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	back = URL('events/select', scheme=True)

	header = H5('Events')

	if not path:
		session['back'] = None
	elif path=='select':
		footer = A("Export all Events as CSV file", _href=URL('events_export')) 
		db.Events.Paid.readable = db.Events.Unpaid.readable = True
		db.Events.Prvsnl.readable = db.Events.Wait.readable = db.Events.Attend.readable = True
	elif path=='new':
		header = CAT(A('back', _href=back), H5('New Event'))
	else:
		url = URL('register', path[5:], scheme=True)
		header = CAT(A('back', _href=back), H5('Event Record'),
	       			"Booking link is ", A(url, _href=url), XML('<br>'),
	       			A('Make a Copy of This Event', _href=URL('event_copy', path[5:])))
	       		
	pre_action_buttons = [GridActionButton(text='Rsvtns', url=URL('event_reservations'), append_id=True)]

	def checktickets(form):
		for t in form.vars['Tickets']:
			if t!='' and not re.match(r'[^\$]*\$[0-9]+\.?[0-9]{0,2}$', t):
				form.errors['Tickets'] = f"{t} is not a good ticket definition"
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id')):
			db.Events[form.vars.get('id')].update_record(Modified = datetime.datetime.now())

	grid = Grid(path, db.Events.id>0,
	     	orderby=~db.Events.DateTime,
		    headings=['Datetime', 'Event', 'Venue','Speaker','TBC', 'Conf', 'Wait'],
			fields=[db.Events.DateTime, db.Events.Description, db.Events.Venue, db.Events.Speaker,
	    			db.Events.Unpaid, db.Events.Attend, db.Events.Wait],
			search_queries=[["Event", lambda value: db.Events.Description.like(f'%{value}%')],
		    				["Venue", lambda value: db.Events.Venue.like(f'%{value}%')],
						    ["Speaker", lambda value: db.Events.Speaker.like(f'%{value}%')]],
			pre_action_buttons=pre_action_buttons,
			details=not write, editable=write, create=write,
			deletable=lambda r: write and db(db.Reservations.Event == r['id']).count() == 0 and db(db.AccTrans.Event == r['id']).count() == 0,
			validation=checktickets,
			grid_class_style=grid_style,
			formstyle=form_style,
			)
	return locals()
		
@action('event_reservations/<event_id:int>', method=['POST', 'GET'])
@action('event_reservations/<event_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def event_reservations(event_id, path=None):
# ...event_reservatins/event_id/...
# request.query: waitlist=True, provisional=True
	db.Reservations.id.readable=db.Reservations.Event.readable=False
	if path=='select':
		db.Reservations.Cost.readable=True
		db.Reservations.TBC.readable=True
		db.Reservations.Conf.readable=True
		db.Reservations.Wait.readable=True
		db.Reservations.Prov.readable=True
	back=URL(f'event_reservations/{event_id}/select', vars=request.query, scheme=True)

	event = db.Events[event_id]
	header = CAT(A('back', _href=URL('events/select')),
	      		H5('Provisional Reservations' if request.query.get('provisional') else 'Waitlist' if request.query.get('waitlist') else 'Reservations'),
				H6(f"{event.DateTime}, {event.Description}"),
				XML("Use the 'Edit' buttons to drill down on a reservation and view detail or edit individual reservations."), XML('<br>'))
	query = f'(db.Reservations.Event=={event_id})'
	#for waitlist or provisional, have to include hosts with waitlisted or provisional guests
	if request.query.get('waitlist') or request.query.get('provisional'):
		query += f"&db.Reservations.Member.belongs([r.Member for r in \
db((db.Reservations.Event=={event_id})&{'(db.Reservations.Waitlist==True)' if request.query.get('waitlist') else '(db.Reservations.Provisional==True)'}).\
select(db.Reservations.Member, orderby=db.Reservations.Member, distinct=True)])"
	else:
		query += '&(db.Reservations.Waitlist==False)&(db.Reservations.Provisional==False)'
		header = CAT(header, A('Export Doorlist as CSV file',
			 _href=(URL(f'doorlist_export/{event_id}', vars=dict(back=back), scheme=True))), XML('<br>'))
	query += '&(db.Reservations.Host==True)'

	if not request.query.get('provisional'):
		header = CAT(header, A('Send Email Notice', _href=URL('composemail', vars=dict(query=query,
			left  = "[db.Emails.on(db.Emails.Member==db.Reservations.Member),db.Members.on(db.Members.id==db.Reservations.Member)]",	
			qdesc=f"{event.Description} {'Waitlist' if request.query.get('waitlist') else 'Attendees'}",
			back=back))), XML('<br>'))
	header = CAT(header, XML('Display: '))
	if request.query.get('waitlist') or request.query.get('provisional'):
		header = CAT(header, A('reservations', _href=URL(f'event_reservations/{event_id}')), ' or ')
	if not request.query.get('waitlist'):
		header = CAT(header, A('waitlist', _href=URL(f'event_reservations/{event_id}/select', vars=dict(waitlist=True))), ' or ')
		
	if not request.query.get('provisional'):
		header = CAT(header, A('provisional', _href=URL(f'event_reservations/{event_id}/select', vars=dict(provisional=True))), XML(' (not checked out)'))

	pre_action_buttons = [GridActionButton(lambda row: URL(f"reservation/{row.Reservations.Member}/{event_id}"),
							text='Edit', append_id=False)]

	grid = Grid(path, eval(query),
			left=db.Members.on(db.Members.id == db.Reservations.Member),
			orderby=db.Reservations.Created if request.query.get('waitlist') else db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[db.Reservations.Member,db.Members.Membership, db.Members.Paiddate,
						db.Reservations.Affiliation, db.Reservations.Notes, db.Reservations.TBC,
						db.Reservations.Wait if request.query.get('waitlist') else db.Reservations.Prov if request.query.get('provisional') else db.Reservations.Conf],
			headings=['Member', 'Type', 'Until', 'College', 'Notes', 'Tbc', '#'],
			pre_action_buttons=pre_action_buttons,
			details=False, editable = False, create = False, deletable = False,
			rows_per_page=200, grid_class_style=grid_style, formstyle=form_style)
	return locals()

def collegelist(sponsors=[]):
	colleges = db().select(db.Colleges.ALL, orderby=db.Colleges.Oxbridge|db.Colleges.Name).find(lambda c: c.Oxbridge==True or c.id in sponsors)
	return [(c.id, c.Name) for c in colleges if c.Name != 'Cambridge University' and c.Name != 'Oxford University']
	
@action('reservation/<member_id:int>/<event_id:int>', method=['POST', 'GET'])
@action('reservation/<member_id:int>/<event_id:int>/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('read')
def reservation(member_id, event_id, path=None):
# ...reservation/member_id/event_id/...
#this controller is for dealing with the addition/modification of an expanded reservation
	write = ACCESS_LEVELS.index(session['access']) >= ACCESS_LEVELS.index('write')
	member = db.Members[member_id]
	event = db.Events[event_id]
	all_guests = db((db.Reservations.Member==member.id)&(db.Reservations.Event==event.id)).select(orderby=~db.Reservations.Host)
	host_reservation =all_guests.first()
	
	if not path:
		back = session.get('url_prev')
		session['back'] = back
	elif path=='select':
		back = session.get('back')
	else:
		back = URL('reservation', f'{member_id}/{event_id}/select')

	if path:
		header = CAT(A('back', _href=back), H5('Member Reservation'),
	      		H6(member_name(member_id)),
	      		XML(markmin.markmin2html(event_confirm(event.id, member.id, event_only=path != 'select'))))
	if path and path=='select':
		header = CAT(header, A('send email', _href=(URL('composemail', vars=dict(
			query=f"(db.Members.id=={member_id})&(db.Members.id==db.Reservations.Member)&(db.Reservations.Event=={event_id})",
			qdesc=member_name(member_id), left="db.Emails.on(db.Emails.Member==db.Members.id)", back=session['url'])))),
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
		db.Reservations.Selection.requires=IS_IN_SET(event.Selections, zero='please select from dropdown list')
	else:
		db.Reservations.Selection.writable = db.Reservations.Selection.readable = False
		
	if len(event.Tickets)>0:
		db.Reservations.Ticket.requires=IS_EMPTY_OR(IS_IN_SET(event.Tickets))
		db.Reservations.Ticket.default = event.Tickets[0]
	else:
		db.Reservations.Ticket.writable = db.Reservations.Ticket.readable = False
	
	db.Reservations.Unitcost.writable=db.Reservations.Unitcost.readable=False
	db.Reservations.Event.writable=db.Reservations.Event.readable=False
	db.Reservations.Provisional.writable = db.Reservations.Provisional.readable = True
	db.Reservations.Member.readable = False

	if path and path != 'select' and not path.startswith('delete'):	#editing or creating reservation
		db.Reservations.Survey.readable = True
		db.Reservations.Comment.readable = True
		if host_reservation and (path=='new' or host_reservation.id!=int(path[5:])):
			#this is a new guest reservation, or we are revising a guest reservation
			db.Reservations.Host.default=False
			db.Reservations.Firstname.writable=True
			db.Reservations.Lastname.writable=True
		else:
			#creating or revising the host reservation
			db.Reservations.Title.default = member.Title
			db.Reservations.Firstname.default = member.Firstname
			db.Reservations.Lastname.default = member.Lastname
			db.Reservations.Suffix.default = member.Suffix
			db.Reservations.Paid.writable=db.Reservations.Paid.readable=True
			db.Reservations.Charged.writable=db.Reservations.Charged.readable=True
			db.Reservations.Checkout.writable=db.Reservations.Checkout.readable=True
			db.Reservations.Firstname.readable=db.Reservations.Lastname.readable=False
			if event.Tickets:
				for t in event.Tickets:
					if t.startswith(member.Membership or '~'): db.Reservations.Ticket.default = t
			aff = db(db.Colleges.Name == primary_affiliation(member_id)).select().first()
			if aff: db.Reservations.Affiliation.default = aff.id

	for row in all_guests:
		if row.Ticket:
			row.update_record(Unitcost=decimal.Decimal(re.match('.*[^0-9.]([0-9]+\.?[0-9]{0,2})$', row.Ticket).group(1)))
	
	def validate(form):
		if form.vars.get('Waitlist') and form.vars.get('Provisional'):
			form.errors['Waitlist'] = "Waitlist and Provisional should not both be set"
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
					db.Reservations.Notes, db.Reservations.Status],
			headings=['Last', 'First', 'Notes', 'Status'],
			deletable=lambda r: write and (len(all_guests)==1 or r.id != host_reservation.id),
			details=not write, editable=write, grid_class_style=grid_style,
			formstyle=form_style, create=write, validation=validate,show_id=True)
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
	return locals()
	
@action('event_copy/<event_id:int>', method=['GET'])
@action.uses(db, session, flash)
@checkaccess('write')
def event_copy(event_id):
	event = db.Events[event_id]
	db.Events.insert(Page=event.Page, Description='Copy of '+event.Description, DateTime=event.DateTime,
				Booking_Closed=event.Booking_Closed, Members_only=event.Members_only, Allow_join=event.Allow_join,
				Online=event.Online, Sponsors=event.Sponsors, Venue=event.Venue, Capacity=event.Capacity,
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
@action.uses("form.html", db, session, flash)
@checkaccess('read')
def get_date_range():
# vars:	function: controller to be given the date range
#		title: heading for date range screen
#		range: ytd - year to date
#				 taxyear - prior full calendar year
#		otherwise one full year ending now
	today = datetime.datetime.now().date()
	year_ago = (datetime.datetime.now() - datetime.timedelta(days=365) + datetime.timedelta(days=1)).date()
	year_begin = datetime.date(datetime.datetime.now().year, 1, 1)	#start of current calendar 
	prev_year_begin = datetime.date(datetime.datetime.now().year-1, 1, 1)
	prev_year_end = datetime.date(datetime.datetime.now().year-1, 12, 31)

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
			
def get_banks(startdatetime, enddatetime):
	assets = {}
	rows = db(db.Bank_Accounts.id>0).select(db.Bank_Accounts.id, db.Bank_Accounts.Name, db.Bank_Accounts.Balance)
	for r in rows:
		d = [(bank_balance(r.id, startdatetime, balance=r.Balance), None, None),
				(bank_balance(r.id, enddatetime, balance=r.Balance), None, None),
				r.Name + f'{r.Name} balance']
		assets[r.Name] = d
	return assets

def tdnum(value, query=None, left=None, th=False):
	#return number as TD or TH
	nums = f'${value:,.2f}' if value >= 0 else f'(${-value:,.2f})'
	numsq = A(nums, _href=URL('transactions', vars=dict(query=query,left=left))) if query else nums
	return TH(numsq, _style=f'text-align:right{"; color:Red" if value <0 else ""}') if th==True else TD(numsq, _style=f'text-align:right{"; color:Red" if value <0 else ""}')

def financial_content(event, query=None, left=None):
#shared by financial_statement and tax_statement
	if event:
		event_record = db.Events[event]

	message = H6(f'\n{event_record.Description if event else "Administrative Revenue/Expense"}')
	sumamt = db.AccTrans.Amount.sum()
	sumfee = db.AccTrans.Fee.sum()

	accts = db(eval(f"{query}&(db.AccTrans.Event=={event})")).select(db.CoA.id, db.CoA.Name, db.AccTrans.id,
				db.AccTrans.Event, db.Events.Description, sumamt, sumfee, groupby=db.AccTrans.Account,
				left=eval(f'[db.CoA.on(db.CoA.id == db.AccTrans.Account), {left}]'))
	accts = accts.sort(lambda r: r.CoA.Name)
	
	totrev = totexp = cardfees = 0
	rows = [THEAD(TR(TH('Account'), TH('Amount')))]
	for acct in accts:
		if acct[sumamt] >= 0:
			rows.append(TR(TD(A(acct.CoA.Name[0:25], _href=URL('transactions',
							vars=dict(query=f"{query}&(db.AccTrans.Account=={acct.CoA.id})&(db.Events.id=={event})",  left=left)))),
						tdnum(acct[sumamt])))
			totrev += acct[sumamt]
			cardfees -= acct[sumfee] or 0
	rows.append(THEAD(TR(TH('Total'), tdnum(totrev, th=True))))
	message = CAT(message, H6('\nRevenue'), TABLE(*rows))

	rows = [THEAD(TR(TH('Account'), TH('Amount')))]
	for acct in accts:
		if acct[sumamt] < 0:
			rows.append(TR(TD(A(acct.CoA.Name[0:25], _href=URL('transactions',
							vars=dict(query=f"{query}&(db.AccTrans.Account=={acct.CoA.id})&(db.Events.id=={event})",  left=left)))),
						tdnum(-acct[sumamt])))
			totexp -= acct[sumamt]
			cardfees -= acct[sumfee] or 0
	rows.append(TR(TD('Card Fees'), tdnum(cardfees)))
	rows.append(THEAD(TR(TH('Total'), tdnum(totexp + cardfees, th=True))))
	rows.append(THEAD(TR(TH('Net Revenue'), tdnum(totrev - totexp - cardfees, th=True))))
	return CAT(message, H6('\nRevenue'), TABLE(*rows))

@action('financial_detail/<event:int>', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess('accounting')
def financial_detail(event, query=None, left=None, title=''):
	source = session.get('url_prev')
	if 'transactions' not in source:
		back = session.get('url_prev')
		session['back'] = back
	query = session.get('query')
	left = session.get('left')
	title = request.query.get('title')

	message = CAT(A('back', _href=session.get('back')), H5(f'{title}'),
			financial_content(event if event!=0 else None, query, left))
	return locals()
	
@action('financial_statement', method=['GET'])
@action.uses("message.html", db, session, flash)
@checkaccess('accounting')
def financial_statement():
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
	
	transfer = db(db.CoA.Name=='Transfer').select().first().id	#ignore transfer transactions
	session['query'] = f"(((db.AccTrans.Event != None) & (db.Events.DateTime >= '{startdatetime}') & (db.Events.DateTime < '{enddatetime}')) | \
((db.AccTrans.Event == None) & (db.AccTrans.Account != {transfer}) & \
(db.AccTrans.Timestamp >= '{startdatetime}') & (db.AccTrans.Timestamp < '{enddatetime}')))"
	session['left'] = 'db.Events.on(db.Events.id == db.AccTrans.Event)'

	events = db(eval(session.get('query'))).select(db.AccTrans.Event, db.Events.Description, db.Events.DateTime,
					left = eval(session.get('left')), orderby = db.Events.DateTime, groupby = db.Events.DateTime)

	rows = [THEAD(TR(TH('Event'), TH('Date'), TH('Revenue'), TH('Expense'), TH('Net Revenue')))]
	totrev = totexp = 0
	for e in events:
		name = 'Admin' if e.AccTrans.Event == None else e.Events.Description
		date = '' if e.AccTrans.Event == None else e.Events.DateTime.date()
		rev = exp = 0
		accounts = db(eval(session.get('query')+'&(db.AccTrans.Event==e.AccTrans.Event)')).select(sumamt, sumfee,
					left = eval(session.get('left')), orderby = db.AccTrans.Account, groupby = db.AccTrans.Account)
		for a in accounts:
			if a[sumamt] >= 0:
				rev += a[sumamt]
			else:
				exp += a[sumamt]
			exp += a[sumfee] or 0
		rows.append(TR(TD(A(name[0:25], _href=URL(f'financial_detail/{e.AccTrans.Event or 0}', vars=dict(title=title)))), 
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
	start = request.query.get('start')
	end = request.query.get('end')
	startdatetime = datetime.datetime.fromisoformat(start)
	enddatetime = datetime.datetime.fromisoformat(end)+datetime.timedelta(days=1)
	startdate = datetime.date.fromisoformat(start)
	enddate = datetime.date.fromisoformat(end)
	title = f"Financial Statement (cash based) for period {start} to {end}"

	if not start or not end:
		redirect(URL('get_date_range', vars=dict(function='financial_statement',title='Financial Statement')))
		
	message = CAT(H5(title), H6('Account Balances'))

	sumamt = db.AccTrans.Amount.sum()
	sumfee = db.AccTrans.Fee.sum()
	tktacct = db(db.CoA.Name=='Ticket sales').select().first().id
	sponacct = db(db.CoA.Name=='Sponsorships').select().first().id
	xferacct = db(db.CoA.Name=='Transfer').select().first().id	#ignore transfer transactions

	session['query'] = f"((db.AccTrans.Timestamp>='{startdatetime}')&(db.AccTrans.Timestamp < '{enddatetime}') & (db.AccTrans.Accrual!=True))"
	session['left'] = 'db.Events.on(db.Events.id == db.AccTrans.Event)'
	
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
	allrevexp = db(eval(f"{session.get('query')}&(db.AccTrans.Account!={xferacct})")).select(sumamt, sumfee,
					orderby=db.AccTrans.Account, groupby=db.AccTrans.Account)
	for t in allrevexp:
		if t[sumamt] >= 0:
			allrev += t[sumamt]
		else:
			allexp += t[sumamt]
		allexp += (t[sumfee] or 0)

	events = db(eval(f"{session.get('query')}&(db.AccTrans.Event!=None)")).select(db.Events.DateTime, db.Events.Description,
					db.Events.id, left = eval(session.get('left')), orderby = db.Events.DateTime, groupby = db.Events.DateTime)
	rows =[THEAD(TR(TH('Event'), TH('Ticket Sales'), TH('Sponsorships'), TH('Revenue'), TH('Expense'), TH('Notes')))]
	for e in events:
		trans = db(eval(f"{session.get('query')}&(db.AccTrans.Event=={e.id})")).select(db.AccTrans.Account, sumamt, sumfee,
					left = eval(session.get('left')), orderby = db.AccTrans.Account, groupby = db.AccTrans.Account)
		tkt = trans.find(lambda t: t.AccTrans.Account == tktacct).first()
		spon = trans.find(lambda t: t.AccTrans.Account == sponacct).first()
		revenue = expense = 0
		for a in trans:
			if a[sumamt] >= 0:
				revenue += (a[sumamt] or 0)
			else:
				expense += (a[sumamt] or 0)
			expense += (a[sumfee] or 0)

		rows.append(TR(TD(A(e.Description[0:25], _href=URL('financial_detail', vars=dict(event=e.id, title=title)))),
					tdnum(tkt[sumamt] if tkt else 0), tdnum(spon[sumamt] if spon else 0),
					tdnum(revenue), tdnum(expense), TD(e.DateTime.date())))
		if spon:
			spontr = db(eval(f"{session.get('query')}&(db.AccTrans.Event=={e.id})&(db.AccTrans.Account=={sponacct})")).select(
					db.AccTrans.Amount, db.AccTrans.Notes, left = eval(session.get('left')))
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

	message = CAT(message, financial_content(None))
	return locals()
		
@action('accounting', method=['POST', 'GET'])
@action('accounting/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('accounting')
def accounting(path=None):

	if path and path=='select':
		header = CAT(H5('Banks'),
	       		A('Financial Statement', _href=URL('get_date_range', vars=dict(
					function='financial_statement', title='Financial Statement'))), XML('<br>'),
	       		A('Tax Statement', _href=URL('get_date_range', vars=dict(
					function='tax_statement', title='Tax Statement', range='taxyear'))), XML('<br>'),
				"Use Upload to load a file you've downloaded from bank/payment processor into accounting")
	else:
		header = CAT(A('back', _href=URL('accounting')) , H5('Banks'))
	
	pre_action_buttons = [GridActionButton(URL('bank_file'), text='Upload', append_id=True),
		GridActionButton(lambda r: URL('transactions', vars=dict(query=f"db.AccTrans.Bank=={r['id']}")),
							text='Transactions', append_id=False)
	]

	grid = Grid(path, db.Bank_Accounts.id>0,
				orderby=db.Bank_Accounts.Name,
				columns=[db.Bank_Accounts.Name, db.Bank_Accounts.Accrued, db.Bank_Accounts.Balance],
				pre_action_buttons=pre_action_buttons,
				deletable=False, details=False, editable=True, create=True,
				grid_class_style=grid_style,
				formstyle=form_style,
	)		
	return locals()

@action('bank_file/<bank_id:int>', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess('accounting')
def bank_file(bank_id):
#upload and process a csv file from a bank or payment processor
#	.../bank_id		bank_id is reference to bank in Bank Accounts
	bank = db.Bank_Accounts[bank_id]
	bkrecent = db((db.AccTrans.Bank==bank.id)&(db.AccTrans.Accrual!=True)).select(orderby=~db.AccTrans.Timestamp, limitby=(0,1)).first()
	unalloc = db(db.CoA.Name == 'Unallocated').select().first()
	acdues = db(db.CoA.Name == "Membership Dues").select().first()
	actkts = db(db.CoA.Name == "Ticket sales").select().first()
	origin = 'since account start'

	header = CAT(A('back', _href=URL('accounting')),
				H5(f"{bank.Name} Transactions"),
				XML(f"To download data since {markmin.markmin2html(f'``**{str(bkrecent.Timestamp.date()) if bkrecent else origin}**``:red')}:"), XML('<br>'),
				A('Login to Society Account', _href={bank.Bankurl}, _target='blank'), XML('<br>'),
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
	lastrow = None
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
			lastrow = row
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
		flash.set(f"{str(lastrow)}: {str(e)}")
		isok = False
	if isok:
		redirect(URL('transactions', vars=dict(query=f'db.AccTrans.Bank=={bank.id}')))
	return locals()

@action('transactions', method=['POST', 'GET'])
@action('transactions/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('accounting')
def transactions(path=None):
	db.AccTrans.Fee.writable = False

	back = URL('transactions/select', scheme=True)
	if not path:
		if request.query.get('query'):
			session['query'] = request.query.get('query')
		if request.query.get('left'):
			session['left'] = request.query.get('left')
		back = session.get('url_prev')
		session['bank_back'] = back
	elif path=='select':
		back = session.get('bank_back')
	elif path.startswith('edit'):	#editing AccTrans record
		db.AccTrans.Amount.comment = 'to split transaction, enter amount of a split piece'
		db.AccTrans.CheckNumber.writable = False
		db.AccTrans.CheckNumber.requires = None
		transaction = db.AccTrans[path[5:]]
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

	query = session.get('query')
	left = session.get('left')

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
		["Account", lambda value: db.AccTrans.Account.belongs([r.id for r in db(db.CoA.Name.like(f'%{value}%')).select(db.CoA.id)])],
		["Event", lambda value: db.AccTrans.Event.belongs([r.id for r in db(db.Events.Description.like(f'%{value}%')).select(db.Events.id)])],
		["Notes", lambda value: db.AccTrans.Notes.like(f'%{value}%')],
	]
	
	grid = Grid(path, eval(query), left=eval(left) if left else None,
			orderby=~db.AccTrans.Timestamp,
			columns=[db.AccTrans.Timestamp, db.AccTrans.Bank, db.AccTrans.Account, db.AccTrans.Event,
	 				db.AccTrans.Amount, db.AccTrans.Fee, db.AccTrans.CheckNumber, db.AccTrans.Accrual,
					db.AccTrans.Notes],
			headings=['Timestamp', 'Bank', 'Account','Event','Amt', 'Fee', 'Chk#', 'Accr', 'Notes'],
			validation=validate, search_queries=search_queries, show_id=True,
			deletable=lambda r: r.Accrual, details=False, editable=True, create=bank_id!=None,
			field_id=db.AccTrans.id, grid_class_style=grid_style, formstyle=form_style)
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
			if not query or m.group(2)=='reservation' and not ('Reservations.Event' in query):
				raise Exception(f"<{m.group(2)}> can't be used in this context")
			func=m.group(2)
		else:	#metadata?
			text = eval(m.group(2).upper()).replace('<subject>', subject)
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
def event_confirm(event_id, member_id, justpaid=0, event_only=False):
	event = db.Events[event_id]
	resvtns = db((db.Reservations.Event==event_id)&(db.Reservations.Member==member_id)).select(
					orderby=~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname)
	body = '------------------------\n'
	body += '**Event:**|' + (event.Description or '') + '\n'
	body += '**Venue:**|' + (event.Venue or '') + '\n'
	body += '**Date:**|' + event.DateTime.strftime("%A %B %d, %Y") + '\n'
	body += '**Time:**|' + event.DateTime.strftime("%I:%M%p") + '\n'
	body += '------------------------\n'
	if event_only or not resvtns: return body
	tbc = res_tbc(member_id, event_id) or 0
	tbcdues = res_tbc(member_id, event_id, True) or 0
	cost = res_totalcost(member_id, event_id) or 0
	body += '------------------------\n'
	body += '**Name**|**Affiliation**|**Selection**|**Ticket Cost**\n'
	for t in resvtns:
		body += '%s, %s %s %s|'%(t.Lastname, t.Title or '', t.Firstname, t.Suffix or '')
		body += (t.Affiliation.Name if t.Affiliation else '') +'|'
		body += (t.Selection or '') + '|'
		body += '$%6.2f'%(t.Unitcost or 0.00) + '|'
		body += f'``**{res_status(t.id)}**``:red\n' if t.Waitlist or t.Provisional else '\n'
	if tbcdues > tbc:
		body += 'Membership Dues|||$%6.2f\n'%(tbcdues - tbc)
	body += '**Total cost**|||**$%6.2f**\n'%(cost + tbcdues - tbc)
	body += '**Paid**|||**$%6.2f**\n'%((resvtns.first().Paid or 0)+(resvtns.first().Charged or 0)+justpaid)
	if tbcdues>justpaid:
		body += '**Net amount due**|||**$%6.2f**\n'%(tbcdues-justpaid)
	body += '------------------------\n'
	if (tbcdues)>justpaid:
		body += 'To pay online please visit '+URL(f'register/{event_id}', scheme=True)
	elif event.Notes and not resvtns[0].Waitlist and not resvtns[0].Provisional:
		body += '\n\n%s\n'%event.Notes
	return body

#apply markmin format except in HTML sections
def msgformat(b):
	m = re.match(r"^(.*)\{\{(.*)\}\}(.*)$", b, flags=re.DOTALL)
	if m:
		return msgformat(m.group(1)) + m.group(2) + msgformat(m.group(3))
	return markmin.markmin2html(b)

@action('composemail', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess('write')
def composemail():
	query = request.query.get('query')
	qdesc = request.query.get('qdesc')
	left = request.query.get('left')

	header = CAT(A('back', _href=request.query.get('back')), H5("Send Email"))
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
		header = CAT(header, XML(f'To: {qdesc}'))
		footer = A("Export bcc list for use in email", _href=URL('bcc_export',
						vars=dict(query=query, left=left or '', back=request.query.get('back'))))
	else:
		fields.append(Field('to', 'string',
			comment='Include spaces between multiple recipients',
   			requires=[IS_NOT_EMPTY(), IS_LIST_OF_EMAILS()]))
	fields.append(Field('bcc', 'string', requires=IS_LIST_OF_EMAILS(), default=''))
	fields.append(Field('subject', 'string', requires=IS_NOT_EMPTY(), default=proto.Subject if proto else ''))
	fields.append(Field('body', 'text', requires=IS_NOT_EMPTY(), default=proto.Body if proto else "<Letterhead>\n<greeting>\n\n" if query else "<Letterhead>\n\n",
				comment=CAT("You can use <subject>, <greeting>, <member>, <reservation>, <email>, or <metadata> ",
				"where metadata is 'Letterhead', 'Membership Secretary' or  'Reservations', etc.  ",
				"You can also include html content thus: {{content}}. Email is formatted using ",
					A('Markmin', _href='http://www.web2py.com/examples/static/markmin.html', _target='Markmin'), '.')))
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
				bodyparts.append((f"\n\n''{VISIT_WEBSITE_INSTRUCTIONS}''", None))
				rows = db(eval(query)).select(*select_fields, left=eval(left) if left!=None else None, distinct=True)
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
							body += event_confirm(row.get(db.Reservations.Event), member.id)
					message = HTML(XML(msgformat(body)))
					auth.sender.send(to=to, subject=form2.vars['subject'], bcc=bcc, body=message)
				flash.set(f"{len(rows)} emails sent to {qdesc}")
			else:
				to = re.compile('[^,;\s]+').findall(form2.vars['to'])
				body = ''
				for part in bodyparts:
					body += part[0]		
				flash.set(f"Email sent to: {to}")
				message = HTML(XML(msgformat(body)))
				auth.sender.send(to=to, subject=form2.vars['subject'], bcc=bcc, body=message)
			redirect(request.query.get('back'))
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
		id = 0
		for row in rows:
			if mailing_list or row.Members.id != id:	#allow only primary email
				writer.writerow([row.Emails.Email])
			id = row.Members.id
	except Exception as e:
		flash.set(e)
	return locals()

@action('login', method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
def login():
	form = Form([Field('email', 'string',
				requires=[IS_NOT_EMPTY(), IS_EMAIL()], default = session.get('email'))],
				formstyle=FormStyleBulma)
	header = P("Please specify your email to login, you will receive a verification email there.")
 
	if form.accepted:
		user = db(db.users.email==form.vars['email'].lower()).select().first()
		token = str(random.randint(10000,999999))
		if user:
			id = user.id
			user.update_record(tokens= [token]+(user.tokens or []),
				remote_addr = request.remote_addr, when_issued = datetime.datetime.now())
		else:
			id = db.users.insert(email = form.vars['email'].lower(),
				tokens= [token], remote_addr = request.remote_addr,
				when_issued = datetime.datetime.now(),
				url = session['url'])
		log = 'login '+request.remote_addr+' '+form.vars['email']+' '+request.environ['HTTP_USER_AGENT']+' '+(session.get('url') or '')
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

		header = DIV(P('Please click the link sent to your email to continue.'),
					P('This link is valid for 15 minutes. You may close this window.'))
	return locals()

@action('validate/<id:int>/<token:int>', method=['POST', 'GET'])
@action.uses("message.html", db, session)
def validate(id, token):
	user = db(db.users.id == id).select().first()
	if not user or not int(token) in user.tokens or \
			datetime.datetime.now() > user.when_issued + datetime.timedelta(minutes = 15) or \
			user.remote_addr != request.remote_addr:
		redirect(URL('index'))
	session['logged_in'] = True
	session['id'] = user.id
	session['email'] = user.email
	session['member_filter'] = None
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
		P(A('Go back', _href=session.get('urll_prev'))))
	return locals()

@action('logout')
@action.uses(session)
def logout():
	session['logged_in'] = False
	redirect(URL('index'))

@action('db_tool', method=['POST', 'GET'])
@action('db_tool/<path:path>', method=['POST', 'GET'])
@action.uses("grid.html", db, session, flash)
@checkaccess('admin')
def db_tool(path=None):
	form = Form([Field('query'),
	      		Field('do_update', 'boolean'),
			    Field('field_update')],
				keep_values=True, formstyle=FormStyleDefault)
	
	header = "The \"query\" is a condition like \"db.table1.field1=='value'\". Something like \"db.table1.field1==db.table2.field2\" results in a SQL JOIN.\
Use (...)&(...) for AND, (...)|(...) for OR, and ~(...) for NOT to build more complex queries.\
\"field_update\" is an optional expression like \"field1='newvalue'\". You cannot update the results of a JOIN"

	if form.accepted:
		try:
			grid = Grid(path, eval(form.vars.get('query')),
					details=False, editable=False, create=False, deletable=False,
					grid_class_style=GridClassStyle, formstyle=form_style, show_id=True,
					)
			if form.vars.get('do_update'):
				rows = db(eval(form.vars.get('query'))).select()
				for row in rows:
					update_string = 'row.update_record('+form.vars.get('field_update')+')'
					eval(update_string)
				flash.set(f"{len(rows)} records updated, Submit again to see results")
				form.vars['do_update']=False
		except Exception as e:
			flash.set(e)
	return locals()

@action("db_restore", method=['POST', 'GET'])
@action.uses("form.html", db, session, flash)
@checkaccess('admin')
def db_restore():
	form = Form([Field('filespec', 'string', requires=IS_NOT_EMPTY(),
					   default='db_backup.csv')], formstyle=FormStyleBulma)
	header = P(SOCIETY_DOMAIN+" database will be restored from this file in app base directory. Click Submit to proceed")
	
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

