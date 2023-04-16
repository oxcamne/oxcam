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
from .models import primary_email, res_tbc, member_name, member_affiliations, primary_matriculation, \
			member_emails, event_revenue, event_unpaid, res_totalcost, primary_affiliation
from py4web.utils.grid import Grid, GridClassStyleBulma, Column
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import *
from py4web.utils.factories import Inject
import datetime, random, re, markmin, stripe, csv, decimal, io
from io import StringIO

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
	header = H5('Member Records')
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
		header = CAT(header, A("Send Email to Specific Address(es)", _href=URL('composemail', vars=dict(back=back))))
	elif path:
		back = session.get('back') or back
		header = CAT(A('back', _href=back), H5('Member Record'))
		if path.startswith('edit'):
			header= CAT(header,
	       			P(A('Member reservations', _href=URL('member_reservations', path[5:])), XML('<br>'),
					A('OxCam affiliation(s)', _href=URL('affiliations', path[5:])), XML('<br>'),
					A('Email addresses and subscriptions', _href=URL('emails', path[5:])), XML('<br>'),
					A('Dues payments', _href=URL('dues', path[5:])), XML('<br>'),
					A('Send Email to Member', _href=URL('composemail',
					 	vars=dict(query=f"db.Members.id=={path[5:]}", left='',
		 					qdesc=member_name(path[5:]),
		   					back=URL(f'members/edit/{path[5:]}', scheme=True)))))
	       			)
	else:
		session['back'] = None

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
				P(A("Send Notice to "+qdesc, _href=URL('composemail',
					vars=dict(query=query, left=left or '', qdesc=qdesc, back=back)))))
		header = CAT(header,
	       P("Use filter to select a mailing list or apply other filters. Selecting an event selects \
(or excludes from a mailing list) attendees. You can filter on a member record field \
using an optional operator (=, <, >, <=, >=) together with a value."))
		footer = A("Export selected records as CSV file", _href=URL('members_export',
						vars=dict(query=query, left=left or '', qdesc=qdesc)))

	def mod_member(form):
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id')):
			db.Members[form.vars.get('id')].update_record(Modified = datetime.datetime.now())
		if form.vars.get('Paiddate'):
			dues = db(db.Dues.Member == form.vars.get('id')).select(orderby=~db.Dues.Date).first()
			if dues:
				dues.update_record(Nowpaid = form.vars.get('Paiddate'))

	def member_deletable(id): #deletable if not member, never paid dues or attended recorded event, or on mailing list
		m = db.Members[id]
		emails = db(db.Emails.Member == id).select()
		ifmailings = False
		for em in emails:
			if em.Mailings and len(em.Mailings) > 0: ifmailings = True
		return not m.Membership and not m.Paiddate and not m.Access and \
				not ifmailings and db(db.Dues.Member == id).count()==0 and \
				db(db.Reservations.Member == id).count()==0 and not m.President

	grid = Grid(path, eval(query), left=eval(left) if left else None,
	     	orderby=db.Members.Lastname|db.Members.Firstname,
			columns=[db.Members.Name,
	    			db.Members.Membership, db.Members.Paiddate,
					db.Members.Affiliations,
					db.Members.Access, db.Members.Notes],
			headings=['Name', 'Status', 'Until', 'College', 'Access', 'Notes'],
			details=not write, editable=write, create=write, show_id=True,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
			search_form=search_form,
			validation=mod_member,
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
		if (form.vars.get('id')):
			db.Affiliations[form.vars.get('id')].update_record(Modified = datetime.datetime.now())

	grid = Grid(path, db.Affiliations.Member==member_id,
	     	orderby=db.Affiliations.Modified,
			columns=[db.Affiliations.College, db.Affiliations.Matr, db.Affiliations.Notes],
			details=not write, editable=write, create=write, deletable=write,
			validation=affiliation_modified,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
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
		if (form.vars.get('id')):
			db.Emails[form.vars.get('id')].update_record(Modified = datetime.datetime.now())
			update_Stripe_email(db.Members[form.vars.get('id')])

	grid = Grid(path, db.Emails.Member==member_id,
	     	orderby=~db.Emails.Modified,
			columns=[db.Emails.Email, db.Emails.Mailings],
			details=not write, editable=write, create=write, deletable=write,
			validation=email_modified,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
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
		if (not form.vars.get('id')): 	#adding dues record
			member.update_record(Membership=form.vars.get('Status'), Paiddate=form.vars.get('Nowpaid'), Modified=datetime.datetime.now(),
								Charged=None)

	grid = Grid(path, db.Dues.Member==member_id,
	     	orderby=~db.Dues.Date,
			columns=[db.Dues.Amount, db.Dues.Date, db.Dues.Notes, db.Dues.Prevpaid, db.Dues.Nowpaid],
			details=not write, editable=write, create=write, deletable=write,
			validation=dues_validated,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
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
		#problem - a single ticket specifier comes back as a string, not a list!!!
		if isinstance(form.vars['Tickets'], str):
				form.vars['Tickets'] = [form.vars['Tickets']]
		for t in form.vars['Tickets']:
			if t!='' and not re.match(r'[^\$]*\$[0-9]+\.?[0-9]{0,2}$', t):
				form.errors['Tickets'] = "'%s' is not a good ticket definition"%(t)
		if len(form.errors)>0:
			flash.set("Error(s) in form, please check")
			return
		if (form.vars.get('id')):
			db.Events[form.vars.get('id')].update_record(Modified = datetime.datetime.now())

	grid = Grid(path, db.Events.id>0,
	     	orderby=~db.Events.DateTime,
		    headings=['Datetime', 'Description', 'Venue','Speaker', 'Paid','TBC', 'Conf', 'Wait'],
			fields=[db.Events.DateTime, db.Events.Description, db.Events.Venue, db.Events.Speaker,
	    			db.Events.Paid, db.Events.Unpaid, db.Events.Attend, db.Events.Wait],
			search_queries=[["Description", lambda value: db.Events.Description.like('%'+value+'%')],
		    				["Venue", lambda value: db.Events.Venue.like('%'+value+'%')],
						    ["Speaker", lambda value: db.Events.Speaker.like('%'+value+'%')]],
			pre_action_buttons=pre_action_buttons,
			details=not write, editable=write, create=write,
			deletable=lambda r: write and db(db.Reservations.Event == r['id']).count() == 0 and db(db.AccTrans.Event == r['id']).count() == 0,
			validation=checktickets,
			grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma,
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
	back=URL(f'event_reservations/{event_id}/select', vars=request.query, scheme=True)

	event = db.Events[event_id]
	header = CAT(A('back', _href=URL('events/select')),
	      		H5('Provisional Reservations' if request.query.get('provisional') else 'Waitlist' if request.query.get('waitlist') else 'Reservations'),
				H6(f"{event.DateTime}, {event.Description}"),
				"Use the 'Edit' buttons to drill down on a reservation and view detail or edit individual reservations.", XML('<br>'))
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
	header = CAT(header, 'Display: ')
	if request.query.get('waitlist') or request.query.get('provisional'):
		header = CAT(header, A('reservations', _href=URL(f'event_reservations{event_id}')), ' or ')
	if not request.query.get('waitlist'):
		header = CAT(header, A('waitlist', _href=URL(f'event_reservations/{event_id}/select', vars=dict(waitlist=True))), ' or ')
	if not request.query.get('provisional'):
		header = CAT(header, A('provisional', _href=URL(f'event_reservations/{event_id}/select', vars=dict(provisional=True))), ' (not checked out)')

	pre_action_buttons = [GridActionButton(lambda row: URL(f"reservation/{row.Reservations.Member}/{event_id}"),
							text='Edit', append_id=False)]

	grid = Grid(path, eval(query),
			left=db.Members.on(db.Members.id == db.Reservations.Member),
			orderby=db.Reservations.Created if request.query.get('waitlist') else db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[db.Reservations.Member,db.Members.Membership, db.Members.Paiddate,
						db.Reservations.Affiliation, db.Reservations.Notes,
						db.Reservations.Cost, db.Reservations.TBC, db.Reservations.Conf,
						db.Reservations.Wait],
			headings=['Member', 'Type', 'Until', 'College', 'Notes', 'Paid', 'Tbc', 'Conf', 'Wait'],
			pre_action_buttons=pre_action_buttons,
			details=False, editable = False, create = False, deletable = False,
			rows_per_page=200, grid_class_style=GridClassStyleBulma, formstyle=FormStyleBulma)
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

	header = CAT(A('back', _href=back), H5('Member Reservation'),
	      		H6(member_name(member_id)),
	      		XML(markmin.markmin2html(evtconfirm(event.id, member.id, event_only=True))))
	if path and path=='select':
		header = CAT(header, A('send email', _href=(URL('composemail', vars=dict(
			query=f"(db.Members.id=={member_id})&(db.Members.id==db.Reservations.Member)&(db.Reservations.Event=={event_id})",
			qdesc=member_name(member_id), left="db.Emails.on(db.Emails.Member==db.Members.id)", back=session['url'])))),
			XML(" (use ")+"<reservation>",
			XML(" to include confirmation and payment link)<br>"),	
XML("Top row is the member's own reservation, additional rows are guests.<br>\
Use Add Record to add the member, initially, then to add additional guests.<br>\
Edit rows to move on/off waitlist or first row to record a check payment."))

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
			if event.Tickets:
				for t in event.Tickets:
					if t.startswith(member.Membership or '~'): db.Reservations.Ticket.default = t
			aff = db(db.Colleges.Name == primary_affiliation(member_id)).select().first()
			if aff: db.Reservations.Affiliation.default = aff.id

	for row in all_guests:
		if row.Ticket:
			row.update_record(Unitcost=decimal.Decimal(re.match('.*[^0-9.]([0-9]+\.?[0-9]{0,2})$', row.Ticket).group(1)))

	def validate(form):
		if (form.vars.get('id')):
			db.Reservations[form.vars.get('id')].update_record(Modified = datetime.datetime.now())

	grid = Grid(path, (db.Reservations.Member==member.id)&(db.Reservations.Event==event.id),
			orderby=~db.Reservations.Host|db.Reservations.Lastname|db.Reservations.Firstname,
			columns=[db.Reservations.Lastname, db.Reservations.Firstname, db.Reservations.Affiliation, 
					db.Reservations.Notes, db.Reservations.Selection, db.Reservations.Ticket,
					db.Reservations.Provisional, db.Reservations.Waitlist],
			headings=['Last', 'First', 'College', 'Notes', 'Menu', 'Ticket', 'Prvsnl', 'Waitlist'],
			deletable=lambda r: write and (len(all_guests)==1 or r.id != host_reservation.id),
			details=not write, editable=write, grid_class_style=GridClassStyleBulma,
			formstyle=FormStyleBulma, create=write, validation=validate,show_id=True)
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
def evtconfirm(event_id, member_id, justpaid=0, event_only=False):
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
		if t.Waitlist:
			body += '%s\n'%('``**waitlisted**``:red')
		elif t.Provisional:
			body += '%s\n'%('``**unconfirmed**``:red')
		else:
			body += '\n'
	if tbcdues > tbc:
		body += 'Membership Dues|||$%6.2f\n'%(tbcdues - tbc)
	body += '**Total cost**|||**$%6.2f**\n'%(cost + tbcdues - tbc)
	body += '**Paid**|||**$%6.2f**\n'%((resvtns.first().Paid or 0)+(resvtns.first().Charged or 0)+justpaid)
	if tbcdues>justpaid:
		body += '**Net amount due**|||**$%6.2f**\n'%(tbcdues-justpaid)
	body += '------------------------\n'
	if (tbcdues)>justpaid:
		body += 'To pay online please visit '+URL('member', 'registration', args=[event.id], scheme=True, host=SOCIETY_SUBDOMAIN)
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
		header = CAT(header, P(f'To: {qdesc}'))
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
							body += evtconfirm(row.get(db.Reservations.Event), member.id)
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

