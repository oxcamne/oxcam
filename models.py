"""
This file defines the database models
"""

from .common import db, Field
from .settings import MEMBERSHIPS, ACCESS_LEVELS, TIME_ZONE, DATE_FORMAT
from pydal.validators import IS_IN_DB, IS_EMPTY_OR, IS_IN_SET, IS_NOT_EMPTY, IS_DATE,CLEANUP,\
	IS_NOT_IN_DB, IS_MATCH, IS_EMAIL, IS_DECIMAL_IN_RANGE, IS_DATETIME, IS_INT_IN_RANGE
from yatl.helpers import CAT, A, XML
import datetime, decimal

### Define your table below
#
# db.define_table('thing', Field('name'))
#
## always commit your models to avoid problems later
#
# db.commit()
#

db.define_table('users', 
	Field('email', 'string'),
	Field('tokens', 'list:integer'),
	Field('remote_addr', 'string'),
	Field('when_issued', 'datetime'),
	Field('trusted', 'boolean'))
db.users.email.requires = IS_NOT_IN_DB(db, db.users.email)

#include OxBridge colleges, explicit sponsors; excludes Cambridge/Oxford University
def collegelist(sponsors=[]):
	return [(c.id, c.Name) for c in db((db.Colleges.Oxbridge==True)|(db.Colleges.id.belongs(sponsors))).select(
		orderby=db.Colleges.Oxbridge|db.Colleges.Name)]
	
db.define_table('Colleges',	#contains the individual colleges and other Oxbridge institutions, plus
	Field('Name', 'string'),	#organizations with whom we co-sponsor events.
	Field('Oxbridge', 'boolean', default=True, comment=" (Non-Oxbridge organizations may be event co-sponsors)"),
	format='%(Name)s')
db.Colleges.Name.requires=[IS_NOT_EMPTY(), IS_NOT_IN_DB(db, 'Colleges.Name')]
	
def email_lists(id):
	email = db.Emails[id]
	lists = db(db.Email_Lists.id.belongs(email.Mailings)).select()
	return ', '.join([l.Listname for l in lists])
	
db.define_table('Email_Lists',
	Field('Listname', 'string'),
	Field('Member', 'boolean', default=False, comment=" if true joining Society joins this list"),
	Field('Daemon', 'datetime'),	#on first list, records start time of current Email Daemon
	Field('Description', 'text'),	#HTML allowed
	format='%(Listname)s')
db.Email_Lists.Listname.requires=[IS_NOT_EMPTY(), IS_NOT_IN_DB(db, 'Email_Lists.Listname')]

def primary_affiliation(id):
	aff = db(db.Affiliations.Member == id).select(orderby=db.Affiliations.Modified).first()
	return aff.College.Name if aff else ''

def primary_matriculation(id):
	aff = db(db.Affiliations.Member == id).select(orderby=db.Affiliations.Modified).first()
	return aff.Matr if aff else None

def member_affiliations(id):
	affiliations = db((db.Affiliations.Member== id)&(db.Affiliations.College==db.Colleges.id)).select(
					db.Colleges.Name, db.Affiliations.Matr, orderby=db.Affiliations.Modified)
	return '; '.join([a.Colleges.Name+(' '+str(a.Affiliations.Matr) if a.Affiliations.Matr else '') for a in affiliations])
	
def member_emails(id):
	emails = db(db.Emails.Member == id).select(orderby=~db.Emails.Modified)
	return ', '.join([e.Email.lower() for e in emails])

def primary_email(id):
	em = db(db.Emails.Member == id).select(orderby=~db.Emails.Modified).first()
	return em.Email.lower() if em else None

def member_name(id):
	member = db.Members[id]
	return f"{member.Lastname}, {member.Title or ''} {member.Firstname} {member.Suffix or ''}"
	
db.define_table('Members',
	Field('Title', 'string'),
	Field('Firstname', 'string', requires = [IS_NOT_EMPTY(), CLEANUP()], comment='*'),
	Field('Lastname', 'string', requires = [IS_NOT_EMPTY(), CLEANUP()], comment='*'),
	Field('Suffix', 'string'),
	Field('Membership', 'string', requires=IS_EMPTY_OR(IS_IN_SET([m.category for m in MEMBERSHIPS]))),
	Field('Paiddate', 'date', requires = IS_EMPTY_OR(IS_DATE())),
	Field('Pay_source'),	#payments source, e.g. 'stripe'
	Field('Pay_cust'),	#Customer id on payment system
	Field('Pay_subs'),	#Subscription id or 'Cancelled'
	Field('Pay_next', 'date'),	#Next subscription payment date
	Field('Charged', 'decimal(6,2)'),	#initial payment made, not yet downloaded from Stripe
	Field('Privacy', 'boolean', default=False, comment=' Exclude email address from member directory'),
	Field('Access', 'string', requires = IS_EMPTY_OR(IS_IN_SET(ACCESS_LEVELS)), comment=' Set for advisory committee'),
	Field('Committees', 'string'),
	Field('President', 'string', comment='yyyy-yyyy; years Society President'),
	Field('Notes', 'text'),
	Field('Address1', 'string'),
	Field('Address2', 'string'),
	Field('City', 'string', comment='* city or town'),
	Field('State', 'string', comment='*'),
	Field('Zip', 'string', comment='* zip or postcode'),
	Field('Homephone', 'string'),
	Field('Workphone', 'string'),
	Field('Cellphone', 'string', comment='Cellphone for Society use only, will not be published in Directory'),
	Field('Source', 'string', writable=False),
	Field('Created', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	plural="Members", singular="Member",
	format=lambda r: f"{r.Lastname}, {r.Title or ''} {r.Firstname} {r.Suffix or ''}")
	
db.define_table('Emails',
	Field('Member', 'reference Members', writable=False),
	Field('Email', 'string', requires=IS_EMAIL(), writable=False),
	Field('Mailings', 'list:reference Email_Lists', #widget=ListRefCheckboxWidget,
			comment='On desktop Ctrl-click on list name in list above to toggle selection'),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	singular="Email", plural="Emails", format='%(Email)s')

#returns a dictionary to look up host member_id and get confirmed ticket cost for an event
def event_ticket_dict(event_id):
	price = db.Event_Tickets.Price.sum()
	return {r.Reservations.Member: r[price] for r in db((db.Reservations.Event==event_id)&(db.Reservations.Waitlist==False)\
							&(db.Reservations.Provisional==False)&(db.Event_Tickets.Price!=None)).select(
			db.Reservations.Member, price, left = db.Event_Tickets.on(db.Event_Tickets.id==db.Reservations.Ticket_),
			orderby = db.Reservations.Member, groupby = db.Reservations.Member)}

#returns a dictionary to look up host member_id and get amount paid for an event including pending charges
#includes all reservations for an event regardless of status
def event_paid_dict(event_id):
	actkts = db(db.CoA.Name.ilike("Ticket sales")).select().first().id
	amount = db.AccTrans.Amount.sum()
	paid = {r.AccTrans.Member: r[amount] for r in db((db.AccTrans.Event==event_id)&(db.AccTrans.Account==actkts)).select(
		db.AccTrans.Member, amount, orderby = db.AccTrans.Member, groupby = db.AccTrans.Member)}
	return {r.Member: (r.Charged or 0) + paid.get(r.Member, 0) for r in 
		 	db((db.Reservations.Event==event_id)&(db.Reservations.Host==True)).select(db.Reservations.Member, db.Reservations.Charged)}
	
def event_revenue(event_id, member_id=None):	#revenue from confirmed tickets
	paid = event_paid_dict(event_id)
	if member_id:
		return paid.get(member_id, 0)
	return sum(paid.values())

def event_cost(event_id, member_id=None):
	tickets = event_ticket_dict(event_id)
	if member_id:
		return tickets.get(member_id, 0)
	return sum(tickets.values())

def event_unpaid(event_id, member_id=None):	#unpaid from confirmed reservations
	return event_cost(event_id, member_id) - event_revenue(event_id, member_id)

def event_wait(event_id):
	wait = db((db.Reservations.Event==event_id)&(db.Reservations.Waitlist==True)).count()
	return wait

def event_attend(event_id):
	attend = db((db.Reservations.Event==event_id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).count()
	return attend

markdown_comment = CAT(" (optional) create page using ",
			   A('Markdown', _href='https://www.markdownguide.org/basic-syntax/', _target='doc'),
			   " and ",
			   A('HTML', _href='https://oxcamne.github.io/oxcam/send_email.html#embedding-images-in-email', _target='doc'),
			   " for additional formatting ")
			
db.define_table('Events',
	Field('Page', 'string', comment=" (optional) Link to external event page"),
	Field('Description', 'string', requires=IS_NOT_EMPTY(), comment=" Shown on website, confirmations, and financials"),
	Field('DateTime', 'datetime', requires=[IS_NOT_EMPTY(), IS_DATETIME()], comment=" Event Date and Time, use 24-hour clock"),
	Field('Booking_Closed', 'datetime'),
	Field('Details', 'text', comment=markdown_comment),
	Field('Members_only', 'boolean', default=True, comment=" members and their guests only"),
	Field('AdCom_only', 'boolean', default=False, comment=" advisory committee and guests only"),
	Field('Allow_join', 'boolean', default=True, comment=" offer join option in registration"),
	Field('Guests', 'integer', comment=" limit total guests (including member) allowed"),
	Field('Sponsors', 'list:reference Colleges',
			requires=IS_EMPTY_OR(IS_IN_DB(db(db.Colleges.Oxbridge!=True), db.Colleges.id, '%(Name)s', multiple=True)),
			comment=' Select co-sponsors to allow members to register.Members. Use ctrl-click to select multiple, e.g. for AUABN'),
	Field('Venue', 'string', requires=IS_NOT_EMPTY()),
	Field('Capacity', 'integer', requires=IS_EMPTY_OR(IS_INT_IN_RANGE(1))),
	Field('Waiting', 'boolean', comment="set once overall capacity limit breached"),
	Field('Speaker', 'string'),
	Field('Notes', 'text', comment=CAT("included on registration confirmation, supports ", A('Markdown', _href='https://www.markdownguide.org/basic-syntax/', _target='Markdown'), " format")),
	Field('Comment', 'string', comment="open ended question at Checkout."),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	singular="Event", plural="Events", format=lambda r: f"{r.DateTime.strftime(DATE_FORMAT)} {r.Description[:25]}")

def tickets_sold(ticket_id):
	return db((db.Reservations.Ticket_==ticket_id)&(db.Reservations.Provisional==False)&(db.Reservations.Waitlist==False)).count()

db.define_table('Event_Tickets',
	Field('Event', 'reference Events', writable=False),
	Field('Ticket', 'string', requires=IS_NOT_EMPTY(),
	   comment="can specify membership, e.g. full/student/non-member"),
	Field('Short_name', 'string', comment="short name for doorlist"),	#short name for use in doorlist
	Field('Price', 'decimal(5,2)', requires=IS_DECIMAL_IN_RANGE(0)),
	Field('Count', 'integer', requires=IS_EMPTY_OR(IS_INT_IN_RANGE(1)),
	   comment="to limit number of tickets at this price"),
	Field('Waiting', 'boolean', comment="set when limit for this ticket type breached"),
	Field('Qualify', 'string',
	   comment="use if qualification required in notes"),
	Field('Allow_as_guest', 'boolean', default=True,
	   comment="clear if ticket can't apply to a guest"),
	format='%(Short_name)s'
)

db.define_table('Event_Selections',
	Field('Event', 'reference Events', writable=False),
	Field('Selection', 'string', requires=IS_NOT_EMPTY(), comment="for form dropdown"),
	Field('Short_name', 'string', requires=IS_NOT_EMPTY(), comment="for doorlist"),
	format='%(Short_name)s'
)

db.define_table('Event_Survey',
	Field('Event', 'reference Events', writable=False),
	Field('Item', 'string', requires=IS_NOT_EMPTY(),
	   comment="first is question, remainder answer choices"),
	Field('Short_name', 'string', requires=IS_NOT_EMPTY(), comment="for doorlist"),
	format='%(Short_name)s'
)

def page_name(page_id):
	return db.Pages[page_id].Page if page_id else ''

db.define_table('Pages',
	Field('Page', 'string', requires=IS_NOT_EMPTY()),
	Field('Root', 'reference Pages',
	   requires=IS_EMPTY_OR(IS_IN_SET(lambda: {r.id: r.Page for r in db(db.Pages.Root==None).select()})),
	   comment="select root page, e.g. 'Home' or 'Help'"),
	Field.Virtual('Root_name', lambda r: page_name(r.Root)),
	Field('Parent', 'reference Pages',
	   requires=IS_EMPTY_OR(IS_IN_SET(lambda: {r.id: r.Page for r in db(db.Pages.id>0).select()})),
	   comment="select parent page if in submenu"),
	Field.Virtual('Parent_name', lambda r: page_name(r.Parent)),
	Field('Link', 'string', comment="use external Link (leave Content empty)"),
	Field('Content', 'text', 
	   comment=CAT(markdown_comment, ", [[function_name]] for dynamic content")),
	Field('Created', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	format='%(Page)s')

db.define_table('Affiliations',
	Field('Member', 'reference Members', writable=False),
	Field('College', 'reference Colleges'),
	Field('Matr', 'integer', requires=IS_INT_IN_RANGE(1900,datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date().year+1),
			comment='Please enter your matriculation year, not graduation year'),
	Field('Notes', 'string', default=''),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	singular="Affiliation", plural="Affiliations")

def res_wait(member_id, event_id):
	wait = db((db.Reservations.Member==member_id)&(db.Reservations.Event==event_id)&(db.Reservations.Waitlist==True)).count()
	return wait

def res_prov(member_id, event_id):
	prov = db((db.Reservations.Member==member_id)&(db.Reservations.Event==event_id)&(db.Reservations.Provisional==True)).count()
	return prov

def res_conf(member_id, event_id):
	conf = db((db.Reservations.Member==member_id)& (db.Reservations.Waitlist==False) &\
			(db.Reservations.Event==event_id)&(db.Reservations.Provisional==False)).count()
	return conf

def res_unitcost(reservation_id):
	r= db.Reservations[reservation_id]
	return db.Event_Tickets[r.Ticket_].Price if r.Ticket_ else 0

def res_selection(reservation_id):
	r= db.Reservations[reservation_id]
	return db.Event_Selections[r.Selection_].Selection if r.Selection_ else ''

#table includes primary reservation records plus guest records for each guest.
#Member(host) must have record in Members.
#Primary reservation record has Host==True
db.define_table('Reservations',
	Field('Member', 'reference Members', writable=False),
	Field('Event', 'reference Events', writable=False),
	Field('Host', 'boolean', default=True, writable=False), #indicates primary (member's) reservation
	Field('Title', 'string', default='', readable=False, writable=False),
	Field('Firstname', 'string', default='', requires = IS_NOT_EMPTY(), writable=False),
	Field('Lastname', 'string', default='', requires = IS_NOT_EMPTY(), writable=False),
	Field('Suffix', 'string', default='', readable=False, writable=False),
	Field('Affiliation', 'reference Colleges', writable=True, default=None,	#primary affiliation
			requires=IS_EMPTY_OR(IS_IN_DB(db, db.Colleges.id, '%(Name)s', orderby=db.Colleges.Name))),
	Field('Ticket_', 'reference Event_Tickets'),
	Field('Selection_', 'reference Event_Selections'),
	Field('Survey_', 'reference Event_Survey', writable=False),
	Field('Notes', 'string'),	#host name specified, or justifying ticket selection
	Field('Comment', 'string', writable=False),	#answer to open ended question
	Field('Provisional', 'boolean', default=False, writable=False),
													#incomplete reservation: checkout not started, places not allocated
	Field('Waitlist', 'boolean', default=False, writable=False),	#now meaningfull in each individual reservation
	
	#following fields meaningfull only on the member's own reservation (Host==True)
	Field('Charged', 'decimal(6,2)', writable=False),	#payment made, not yet downloaded from Stripe
	Field('Checkout', 'string', writable=False),	#session.vars of incomplete checkout

	Field('Created', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	singular="Reservation", plural="Reservations")

db.define_table('EMProtos',
	Field('Subject', 'string', requires=IS_NOT_EMPTY()),
	Field('Body', 'text', requires=IS_NOT_EMPTY()),
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False))

db.define_table('Email_Queue',	#used for notices or messages targetted via membership database
	Field('Subject'),
	Field('Body', 'text'),			#unexpanded body
	Field('Attachment', 'blob'),	#pickled Mailer.Attachment
	Field('Attachment_Filename'),
	Field('Sender'),
	Field('Bcc'),
	Field('Query', 'text'),	#query used to locate targets
	Field('Left'),	#goes with query
	Field('Qdesc'),	#description of target list
	Field('Scheme'),	#base url 
	Field('Modified', 'datetime', default=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None),
       			update=lambda: datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False))
	
db.define_table('CoA',
	Field('Name', 'string'),
	Field('Notes', 'string'),
	format='%(Name)s')
db.CoA.Name.requires = [IS_NOT_EMPTY(), IS_NOT_IN_DB(db, 'CoA.Name')]

def bank_accrual(bank_id):
	amt = db.AccTrans.Amount.sum()
	r = db((db.AccTrans.Bank==bank_id)&(db.AccTrans.Accrual==True)).select(amt).first()
	return r[amt] or 0
	
db.define_table('Bank_Accounts',
	Field('Name', 'string'),
	Field('Balance', 'decimal(9,2)',
				requires=IS_EMPTY_OR(IS_DECIMAL_IN_RANGE(0, 100000))),	#used to maintain PayPal, Stripe and Bank balances
	Field('Bankurl', 'string', comment=" URL for the bank's login page"),
	Field('Csvheaders', 'string', length=2048, comment=" List of column headings in downloaded CSV file (copy first line of file)"),
	Field('Reference', 'string', comment=" List of columns forming a unique ID for each transaction"),
	Field('Date', 'string', comment=" Column containg date or date and time"),
	Field('Datefmt', 'string', comment=" Python strftime() format string for Date column"),
	Field('Time', 'string', comment=" Column name containing time (if separate from date)"),
	Field('Timefmt', 'string', comment=" Python strftime() format string for Time column"),
	Field('CheckNumber', 'string', comment=" Column name containing check # for checks written"),
	Field('Amount', 'string', comment=" Column name containing credit or debit total amount"),
	Field('Fee', 'string', comment=" Column name containing fee (e.g. on Stripe, PayPal), preceded by '-' if fee is reported as a positive amount"),
	Field('Type', 'string', comment=" Column name containing transaction type (Stripe)"),
	Field('Source', 'string', comment=" Column name containing transaction source (Stripe)"),	
	Field('Notes', 'string', comment=" List of column names to be recorded in Notes of AccTrans record"),
	Field('HowTo', 'text', comment=CAT(" Instructions for downloading file, in ", A('Markdown', _href='https://www.markdownguide.org/basic-syntax/', _target='Markdown'), " format")),
	singular="Bank_Account", plural="Banks", format='%(Name)s')
db.Bank_Accounts.Name.requires = [IS_NOT_EMPTY(), IS_NOT_IN_DB(db, 'Bank_Accounts.Name')]

db.define_table('bank_rules',
	Field('bank', 'reference Bank_Accounts', writable=False),
	Field('csv_column', 'string', comment='select column to test'),
	Field('pattern', 'string', comment='string to match within column content'),
	Field('account', 'reference CoA', comment='select account to assign',
	   			requires=IS_IN_DB(db, 'CoA.id', '%(Name)s'))
)

db.define_table('AccTrans',
	Field('Timestamp', 'datetime', default=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), writable=False),
	Field('Bank', 'reference Bank_Accounts', writable=False,
				requires=IS_IN_DB(db, 'Bank_Accounts.id', '%(Name)s')),	#e.g. PayPal, Cambridge Trust, ...
	Field('Account', 'reference CoA', requires=IS_IN_DB(db, 'CoA.id', '%(Name)s')),
	Field('Event', 'reference Events',
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Events.id', lambda r: f"{r.DateTime.strftime(DATE_FORMAT)} {r.Description[:25]}",
				orderby=~db.Events.DateTime)), comment='leave blank if not applicable'),
	Field('Member', 'reference Members',
				requires=IS_EMPTY_OR(IS_IN_DB(db, 'Members.id', lambda r: f"{r.Lastname}, {r.Firstname}",
				orderby=db.Members.Lastname|db.Members.Firstname)), comment='leave blank if not applicable'),
	Field('Paiddate', 'date', comment="On dues payment, record pre-existing paid date"),
	Field('Membership', comment="On dues payment, record new membership status"),
	Field('Amount', 'decimal(8,2)',
				requires=IS_DECIMAL_IN_RANGE(-100000, 100000)),	# >=0 for asset/revenue, <0 for liability/expense
	Field('Fee', 'decimal(6,2)', requires=IS_EMPTY_OR(IS_DECIMAL_IN_RANGE(-1000,1000))),	# e.g. PayPal transaction fee, <0 (unless refunded)
	Field('CheckNumber', 'integer'),
	Field('Accrual', 'boolean', default=True, writable=False),
	Field('Reference', 'string', writable=False),
	Field('Notes', 'text'),
	singular='Transaction', plural='Transaction_List')
db.AccTrans.CheckNumber.requires=IS_EMPTY_OR(IS_NOT_IN_DB(db, 'AccTrans.CheckNumber'))

db.commit()