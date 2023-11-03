"""
This file contains functions shared by multiple controllers
"""
from py4web import URL
from .common import db, auth
from .settings import TIME_ZONE, SUPPORT_EMAIL, LETTERHEAD, GRACE_PERIOD,\
	DB_URL, SOCIETY_SHORT_NAME, PUBLIC_URL, SOCIETY_NAME
from .models import primary_email, res_tbc, res_totalcost, res_status, member_name
from yatl.helpers import A, TABLE, TH, THEAD, H6, TR, TD, CAT, HTML, XML
import datetime, re, markmin

#check if member is in good standing at a particular date
def member_good_standing(member, date=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()):
	return member and member.Membership and ((not member.Paiddate or member.Paiddate>=date)\
			or member.Charged or (member.Pay_subs and member.Pay_subs != 'Cancelled'))

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

def notify_support(member, subject, body):
	message = f"{member_name(member.id)} id {member.id}<br>{body}"
	message = HTML(XML(message))
	auth.sender.send(to=SUPPORT_EMAIL, sender=SUPPORT_EMAIL, subject=subject, body=message)

#notifications to Member & Support_Email of member actions
def notification(member, subject, body):
	# build and send email update member, and to SUPPORT_EMAIL if production environment
	message = LETTERHEAD.replace('&lt;subject&gt;', subject)
	message += member_greeting(member)
	message += body
	msg_send(member, subject, message)

def newpaiddate(paiddate, timestamp=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None), graceperiod=GRACE_PERIOD):
#within graceperiod days of expiration is treated as renewal if renewed by check, or if student subscription.
#auto subscription will start from actual date
	basedate = timestamp.date() if not paiddate or paiddate<datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).date()-datetime.timedelta(days=graceperiod) else paiddate
	if basedate.month==2 and basedate.day==29: basedate -= datetime.timedelta(days=1)
	return datetime.date(basedate.year+1, basedate.month, basedate.day)

def collegelist(sponsors=[]):
	colleges = db().select(db.Colleges.ALL, orderby=db.Colleges.Oxbridge|db.Colleges.Name).find(lambda c: c.Oxbridge==True or c.id in sponsors)
	return [(c.id, c.Name) for c in colleges if c.Name != 'Cambridge University' and c.Name != 'Oxford University']
			
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
							vars=dict(query=f"{query}&(db.AccTrans.Account=={acct.CoA.id})&(db.Events.id=={event})", left=left)))),
						tdnum(acct[sumamt])))
			totrev += acct[sumamt]
			cardfees -= acct[sumfee] or 0
	rows.append(THEAD(TR(TH('Total'), tdnum(totrev, th=True))))
	message = CAT(message, H6('\nRevenue'), TABLE(*rows))

	rows = [THEAD(TR(TH('Account'), TH('Amount')))]
	for acct in accts:
		if acct[sumamt] < 0:
			rows.append(TR(TD(A(acct.CoA.Name[0:25], _href=URL('transactions',
							vars=dict(query=f"{query}&(db.AccTrans.Account=={acct.CoA.id})&(db.Events.id=={event})", left=left)))),
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

def emailparse(body, subject, query=None):
#parse email body from composemail form into a list of tuples:
#	(text, function)
#	where function will build html format from the results of the query,
#	text (or {{html_content}}) will be inserted directly into the output
	m = re.match(r"^(.*)\{\{(.*)\}\}(.*)$", body, flags=re.DOTALL)
	if m:			#{{html content}} is simply stored. it will be sanitized later with XML()
		bodyparts = [(m.group(2), None)]
		if m.group(1)!='':
			bodyparts = emailparse(m.group(1), subject, query)+bodyparts
		if m.group(3)!='':
			bodyparts = bodyparts+emailparse(m.group(3), subject, query)
		return bodyparts

	m = re.match(r"^(.*)<(.*)>(.*)$", body, flags=re.DOTALL)
	if m:			#found something to expand
		text = func = None
		if m.group(2)=='subject':
			text = subject
		elif m.group(2)=='greeting' or m.group(2)=='email' or m.group(2)=='member' or m.group(2)=='reservation':
			if not query or m.group(2)=='reservation' and not ('Reservations.Event' in query):
				raise Exception(f"<{m.group(2)}> can't be used in this context")
			func=m.group(2) #will be generated individually for each target later
		#should be <name> where name is defined in settings_private, for example <letterhead>
		elif m.group(2)=='letterhead':	#use template and insert subject
			text = eval(m.group(2).upper()).replace('&lt;subject&gt;', subject)
		else: #assume it an UPPER_CASE defined value from settings_private.py
			text = eval(m.group(2).upper())
		bodyparts = [(text, func)]
		if m.group(1)!='':
			bodyparts = emailparse(m.group(1), subject, query)+bodyparts
		if m.group(3)!='':
			bodyparts = bodyparts+emailparse(m.group(3), subject, query)
		return bodyparts
	return [(body.replace('\r\n', '<br>'), None)]
	
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
	body += '------------------------\n'
	return markmin.markmin2html(body)

#Create the header for a member message, such as a confirmation
def msg_header(member, subject):
	body = f"\n\n-------------\n{datetime.datetime.now(TIME_ZONE).replace(tzinfo=None).strftime('%m/%d/%y')}||\n"
	body += f"{(member.Title or '')+' '}{member.Firstname} {member.Lastname} {member.Suffix or ''}||\n"
	if member.Address1:
		body += f"{member.Address1}||\n"
	if member.Address2:
		body += f"{member.Address2}||\n"
	body += f"{member.City or ''} {member.State or ''} {member.Zip or ''}||\n"
	body += '-------------' 
	return LETTERHEAD.replace('&lt;subject&gt;', subject)+markmin.markmin2html(body)
	
#sanitize and send invoice or confirm
def msg_send(member,subject, message):
	email = primary_email(member.id)
	if not email:
		return
	message = HTML(XML(message))
	auth.sender.send(to=email, sender=SUPPORT_EMAIL, bcc=SUPPORT_EMAIL, subject=subject, body=message)
	
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
	if event_only or not resvtns: return markmin.markmin2html(body)
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
	if tbcdues>justpaid:
		body += f"To pay online please visit {DB_URL}/registration/{event_id}"
						#scheme=True doesn't pick up the domain in the email_daemon!
	elif event.Notes and not resvtns[0].Waitlist and not resvtns[0].Provisional:
		body += '\n\n%s\n'%event.Notes
	return markmin.markmin2html(body)

def society_emails(member_id):
	return [row['Email'] for row in db((db.Emails.Member == member_id) & \
	   (db.Emails.Email.contains(SOCIETY_SHORT_NAME.lower()))).select(
			db.Emails.Email, orderby=~db.Emails.Modified)]

def member_greeting(member):
	if member.Title:
		title = member.Title[4:] if member.Title.startswith('The ') else member.Title
		greeting = f"Dear {title} {member.Firstname if title.find('Sir')>=0 else member.Lastname},<br>"
	else:
		greeting = f"Dear {member.Firstname.partition(' ')[0]},<br>"
	return greeting
