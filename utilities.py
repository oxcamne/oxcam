"""
This file contains functions shared by multiple controllers
"""
from py4web import URL, request
from .common import db
from .settings import TIME_ZONE, SUPPORT_EMAIL, LETTERHEAD, GRACE_PERIOD,\
	SOCIETY_SHORT_NAME, MEMBERSHIPS, SMTP_TRANS, PAGE_BANNER
from .models import primary_email, event_cost, member_name, res_selection,\
	res_unitcost, event_revenue, page_name
from .website import about_content, history_content, upcoming_events	#called to construct page content
from yatl.helpers import A, TABLE, TH, THEAD, H6, TR, TD, CAT, HTML, XML
import datetime, re, smtplib, markdown, base64, decimal, locale
from email.message import EmailMessage

#check if member is in good standing at a particular date
#if no paid membership categories always return False
def member_good_standing(member, date):
	return member and (MEMBERSHIPS and (member.Membership and ((not member.Paiddate or member.Paiddate>=date)\
			or member.Charged or (member.Pay_subs and member.Pay_subs != 'Cancelled'))))

def ageband(year, matr):
	if matr:
		age = year - matr + 19
		if age >= 65:
			ageband = '65+'
		elif age >= 55:
			ageband = '55-64'
		elif age >= 45:
			ageband = '45-54'
		elif age >= 35:
			ageband = '35-44'
		elif age >= 25:
			ageband = '25-35'
		else:
			ageband = '-25'
	else:
		ageband = 'unknown'
	return ageband

def email_sender(
	connection = None,	#SMTP server connection if made by caller
	host = SMTP_TRANS,	#specifies server and account to use if connection unspecified
	subject = None,
	sender = None,
	to = None,
	bcc = None,
	body = None,
	attachment = None,
	attachment_filename = None,
	list_unsubscribe = None,
	list_unsubscribe_post = None
):
	if not connection:
		server = smtplib.SMTP(host.server, host.port)
		server.starttls()
		server.login(host.username, host.password)
	else:
		server = connection

	message = EmailMessage()
	message['Subject'] = subject
	message['From'] = sender
	message['Reply-To'] = sender
	message['To'] = to
	if bcc:
		message['Bcc'] = bcc
	if list_unsubscribe:
		message['List-Unsubscribe'] = list_unsubscribe
	if list_unsubscribe_post:
		message['List-Unsubscribe-Post'] = list_unsubscribe_post
	message.set_content(HTML(XML(LETTERHEAD.replace("base_url", get_context('base_url'))+body)).__str__(), subtype='html')
	if attachment:
		message.add_attachment(attachment, maintype='application', subtype='octet-stream', filename=attachment_filename)
	server.send_message(message)
	if not connection:
		server.quit()
		server.close()

def notify_support(member_id, subject, body):
	message = f"{member_name(member_id)} id {member_id}<br>{body}"
	db.commit()
	email_sender(to=SUPPORT_EMAIL, sender=SUPPORT_EMAIL, subject=subject, body=message)

#notifications to Member & Support_Email of member actions
def notification(member, subject, body):
	# build and send email update member, and to SUPPORT_EMAIL if production environment
	message = f"{member_greeting(member)}<br><br>{body}"
	msg_send(member, subject, message)

def newpaiddate(paiddate, timestamp=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), graceperiod=GRACE_PERIOD, years=1):
#within graceperiod days of expiration is treated as renewal if renewed by check, or if student subscription.
#auto subscription will start from actual date
	basedate = timestamp.date() if not paiddate or paiddate<datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()-datetime.timedelta(days=graceperiod) else paiddate
	if basedate.month==2 and basedate.day==29: basedate -= datetime.timedelta(days=1)
	return datetime.date(basedate.year+years, basedate.month, basedate.day)
			
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
	nums = f'{locale.currency(value, grouping=True)}'
	numsq = A(nums, _href=URL('transactions', vars=dict(query=query, left=left, back=request.url))) if query else nums
	return TH(numsq, _style=f'text-align:right{"; color:Red" if value <0 else ""}') if th==True else TD(numsq, _style=f'text-align:right{"; color:Red" if value <0 else ""}')

def financial_content(event, query, left):
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
							vars=dict(query=f"{query}&(db.AccTrans.Account=={acct.CoA.id})&(db.Events.id=={event})", left=left, back=request.url)))),
						tdnum(acct[sumamt])))
			totrev += acct[sumamt]
			cardfees -= acct[sumfee] or 0
	rows.append(THEAD(TR(TH('Total'), tdnum(totrev, th=True))))
	message = CAT(message, H6('\nRevenue'), TABLE(*rows))

	rows = [THEAD(TR(TH('Account'), TH('Amount')))]
	for acct in accts:
		if acct[sumamt] < 0:
			rows.append(TR(TD(A(acct.CoA.Name[0:25], _href=URL('transactions',
							vars=dict(query=f"{query}&(db.AccTrans.Account=={acct.CoA.id})&(db.Events.id=={event})", left=left, back=request.url)))),
						tdnum(-acct[sumamt])))
			totexp -= acct[sumamt]
			cardfees -= acct[sumfee] or 0
	rows.append(TR(TD('Card Fees'), tdnum(cardfees)))
	rows.append(THEAD(TR(TH('Total'), tdnum(totexp + cardfees, th=True))))
	rows.append(THEAD(TR(TH('Net Revenue'), tdnum(totrev - totexp - cardfees, th=True))))
	return CAT(message, H6('\nExpense'), TABLE(*rows))

def bank_balance(bank_id, timestamp=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), balance=0):
	amt = db.AccTrans.Amount.sum()
	fee = db.AccTrans.Fee.sum()
	r = db((db.AccTrans.Bank==bank_id)&(db.AccTrans.Accrual==False)&(db.AccTrans.Timestamp>=timestamp)).select(amt, fee).first()
	return balance-(r[amt] or 0)-(r[fee] or 0)

def template_expand(text, context={}):
	# Expand all occurrences of [[something]] in the text
	pattern = re.compile(r'\[\[(.*?)\]\]')
	member_id = context.get('row').get('Member') or context.get('row').get('Members.id') or context.get('row').get('id') if context.get('row') else None

	# Function to replace each match with the result of eval(some_function)
	def replace_match(match):
		func = match.group(1)
		if func=='greeting' or func=='member' or func=='reservation':
			if not context.get('query') or func=='reservation' and not ('Reservations.Event' in context.get('query')):
				raise Exception(f"[[{func}]] can't be used in this context")
		if func=='greeting':
			result = member_greeting(db.Members[member_id])
		elif func=='member':
			result = member_profile(db.Members[member_id])
		elif func=='reservation':
			result = event_confirm(context.get('row').get('Reservations.Event'), member_id)
		elif func.startswith('upcoming_events'):
			result = upcoming_events()
		elif func.startswith('history_content'):
			result = history_content()
		elif func.startswith('about_content'):	#will be called with committee names
			result = eval(func)
		elif func=='registration_link' or func=='calendar_link':
			event_id_match=re.search(r'db\.Reservations\.Event==(\d+)', context.get('left') or '')
			event_id = context.get('event_id') or (event_id_match.group(1) if event_id_match else None)
			if not event_id:
				raise Exception(f"[[{func}]] can't be used in this context")
			if func=='registration_link':
				result = f"{get_context('base_url')}/registration/{event_id}"
			else:
				result = f"{get_context('base_url')}/add_to_calendar/{event_id}"
		else:
			raise Exception(f"unknown content [[{func}]]")
		return str(result)

	# Replace all matches in the text
	return pattern.sub(replace_match, text)
	
#display member profile
def member_profile(member):
	rows=[TR(TH('Name:', _style="text-align:left"), TD( f"{member.Lastname}, {member.Title or ''} {member.Firstname} {member.Suffix or ''}"))]
	affiliations = db(db.Affiliations.Member == member.id).select(orderby = db.Affiliations.Modified)
	first = True
	for aff in affiliations:
		rows.append(TR(TH('Affiliation:'if first else '', _style="text-align:left"), TD(aff.College.Name + ' ' + str(aff.Matr or ''))))
		first = False
	rows.append(TR(TH('Address line 1:', _style="text-align:left"), TD(member.Address1 or '')))
	rows.append(TR(TH('Address line 2:', _style="text-align:left"), TR(member.Address2 or '')))
	rows.append(TR(TH('Town/City:', _style="text-align:left"), TD(member.City or '')))
	rows.append(TR(TH('State:', _style="text-align:left"), TD(member.State or '')))
	rows.append(TR(TH('Zip:', _style="text-align:left"), TD(member.Zip or '')))
	rows.append(TR(TH('Home phone:', _style="text-align:left"), TD(member.Homephone or '')))
	rows.append(TR(TH('Work phone:', _style="text-align:left"), TD(member.Workphone or '')))
	rows.append(TR(TH('Mobile:', _style="text-align:left"), TD((member.Cellphone or '')+' (not in directory)')))
	rows.append(TR(TH('Email:', _style="text-align:left"), TD((primary_email(member.id) or '') + (' (not in directory)' if member.Privacy==True else ''))))
	return TABLE(*rows).__str__()

#Create the header for a member message, such as a confirmation
def msg_header(member, subject):
	body = f"\n\n<p>{datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).strftime("%x")}<br>"
	body += f"{(member.Title or '')+' '}{member.Firstname} {member.Lastname} {member.Suffix or ''}<br>"
	if member.Address1:
		body += f"{member.Address1}<br>"
	if member.Address2:
		body += f"{member.Address2}<br>"
	body += f"{member.City or ''} {member.State or ''} {member.Zip or ''}<br></p>"
	return body
	
#send invoice or confirm
def msg_send(member,subject, message):
	email = primary_email(member.id)
	if not email:
		return
	db.commit()
	email_sender(to=email, sender=SUPPORT_EMAIL, bcc=SUPPORT_EMAIL, subject=subject, body=message)
	
#create confirmation of event
def event_confirm(event_id, member_id=None, dues=0, event_only=False):
	event = db.Events[event_id]
	rows=[TR(TH('Event:', _style="text-align:left"), TD(event.Description or ''))]
	rows.append(TR(TH('Venue:', _style="text-align:left"), TD(event.Venue or '')))
	rows.append(TR(TH('Date:', _style="text-align:left"), TD(event.DateTime.strftime("%A %B %d, %Y"))))
	if event.EndTime:
		time_str = f"{event.DateTime.strftime('%I:%M%p')} - {event.EndTime.strftime('%I:%M%p')}"
	else:
		time_str = event.DateTime.strftime('%I:%M%p')
	rows.append(TR(TH('Time:', _style="text-align:left"), TD(time_str)))
	body = TABLE(*rows).__str__()
	if event_only:
		return body
	
	resvtns = db((db.Reservations.Event==event_id)&(db.Reservations.Member==member_id)).select(
					orderby=~db.Reservations.Host|db.Reservations.Created)
	cost = event_cost(event_id, member_id)		#ticket cost
	paid = event_revenue(event_id, member_id)	#ticket payments
	dues_unpaid = decimal.Decimal(eval(resvtns[0].Checkout).get('dues') or 0) if resvtns[0].Checkout else 0
	dues += dues_unpaid
	tbc = cost - paid							#tickets unpaid
	rows=[TR(TH('Name', TH('Affiliation'), TH('Selection'), TH('Ticket Cost'), TH('')))]
	for t in resvtns:
		price = res_unitcost(t.id)
		rows.append(TR(TD(f"{t.Lastname}, {t.Firstname}",
						TD(t.Affiliation.Name if t.Affiliation else ''),
						TD(res_selection(t.id)),
						TD(f'{locale.currency(price, grouping=True)}', _style="text-align:right"),
						TH(f'waitlisted' if t.Waitlist else 'no checkout' if t.Provisional else 'confirmed' if paid>=price else 'unpaid')
		)))
		paid -= price
	if dues>0:
		rows.append(TR(TH('Membership Dues', _style="text-align:left"), TD(''), TD(''), TH(f'{locale.currency(dues, grouping=True)}', _style="text-align:right")))
	rows.append(TR(TH('Total Cost', _style="text-align:left"), TD(''), TD(''), TH(f'{locale.currency(cost + dues, grouping=True)}', _style="text-align:right")))
	rows.append(TR(TH('Paid', _style="text-align:left"), TD(''), TD(''),
				TH(f'{locale.currency(event_revenue(event_id, member_id)+dues-dues_unpaid, grouping=True)}', _style="text-align:right")))
	if tbc + dues_unpaid>0:
		rows.append(TR(TH('Net amount due', _style="text-align:left"), TD(''), TD(''), TH(f'{locale.currency(tbc+dues_unpaid, grouping=True)}', _style="text-align:right")))
	body += TABLE(*rows).__str__()
	host_reservation = resvtns[0]
	if host_reservation.Notes:
		body += f"<b>Notes:</b> {host_reservation.Notes}<br>"
	if tbc + dues_unpaid>0:
		body += f"To pay online please visit {get_context('base_url')}/registration/{event_id}<br>"
						#scheme=True doesn't pick up the domain in the email_daemon!
	else:
		calendar_url = f'{get_context('base_url')}/add_to_calendar/{event.id}'
		body += f'<a href="{calendar_url}">Add to calendar</a>'
		if event.Notes and not resvtns[0].Waitlist and not resvtns[0].Provisional:
			body += markdown.markdown(event.Notes)
	return body

def add_page(menu, page, url):
	menu += f"<li><a href={URL(url)}>{page.Page}"
	#subpages:
	subpages = db((db.Pages.Parent==page.id)&(db.Pages.Hide!=True)).select(db.Pages.id, db.Pages.Page, db.Pages.Hide, orderby=db.Pages.Modified)
	if subpages:
		menu += '<ul>'
		for subpage in subpages:
			menu = add_page(menu, subpage, f"{url}/{subpage.Page.replace(' ','_')}")
		menu += '</ul>'
	menu += '</li>'
	return menu

def pages_menu(forpage):
	#build menu of pages for layout_public
	#appropriate root level pages:
	root = forpage.Root or forpage.id
	pages = db((db.Pages.Parent==None) & (db.Pages.Hide==False)).select(db.Pages.id, db.Pages.Page, db.Pages.Root, orderby=db.Pages.Root|db.Pages.Modified)
	menu = ''
	for page in pages:
		if (page.id == root):	
			menu = add_page(menu, page, f"web/{page.Page.replace(' ','_')}")
		elif page.Root == root:
			menu = add_page(menu, page, f"web/{page_name(page.Root).replace(' ','_')}/{page.Page.replace(' ','_')}")
	return menu

def member_greeting(member):
	if member.Title:
		title = member.Title[4:] if member.Title.startswith('The ') else member.Title
		greeting = f"<p>Dear {title} {member.Firstname if title.find('Sir')>=0 else member.Lastname},</p>"
	else:
		greeting = f"<p>Dear {member.Firstname.partition(' ')[0]},</p>"
	return greeting

import hashlib
def generate_hash(email):
    return hashlib.sha1((email + PAGE_BANNER).encode()).hexdigest()

def get_list(list, index):
	try:
		return list[index]
	except IndexError:
		return None
	
#encode something, usually a URL, for use in another URL, e.g. as referrer
def encode_url(url):
	return base64.b16encode(url.encode("utf8")).decode("utf8")

#decode encoded something, usually URL, from a referrer parameter
def decode_url(code):
	return base64.b16decode(code.encode("utf8")).decode("utf8")

def store_context(name, value):
	c = db(db.context.name==name).select().first()
	if c:
		c.update_record(value=value)
	else:
		db.context.insert(name=name, value=value)
	db.commit()

def get_context(name):
	c = db(db.context.name==name).select().first()
	return c.value if c else None