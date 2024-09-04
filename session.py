"""
This file contains controllers used to manage the user's session
"""
from py4web import URL, request, redirect, action, Field
from .common import db, session, flash, logger
from .settings import SUPPORT_EMAIL, TIME_ZONE, LETTERHEAD, SOCIETY_SHORT_NAME, PAGE_BANNER, HOME_URL, HELP_URL, DATE_FORMAT
from .models import ACCESS_LEVELS, member_name, CAT
from .utilities import email_sender
from yatl.helpers import A, H6, XML, P, DIV
from py4web.utils.form import Form, FormStyleBulma
from pydal.validators import IS_IN_SET, IS_EMAIL, ANY_OF
from py4web.utils.factories import Inject
import datetime, random

preferred = action.uses("gridform.html", db, session, flash, Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL))

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
			if db(db.Colleges.id>0).count()==0 and not session.logged_in:
				redirect(URL('login', vars=dict(url=URL('db_restore'))))
			member_id = session.member_id
			if member_id:
				member = db(db.Members.id == member_id).select(db.Members.Access).first()
				if member:
					session.access = member.Access
				else:
					redirect(URL('login', vars=dict(url=request.url)))
			if not(session.logged_in and (not member_id or member)):    #not logged in, or member deleted
				redirect(URL('login', vars=dict(url=request.url)))

			#check access
			if requiredaccess != None:
				require = ACCESS_LEVELS.index(requiredaccess)
				have = -1
				if member_id and member.Access:
					have = ACCESS_LEVELS.index(member.Access)
				if have < require and db(db.Members.id>0).count()>0:
					redirect(URL('accessdenied'))
			return f(*args, **kwds)
		return wrapped_f
	return wrap

@action('login', method=['POST', 'GET'])
@preferred
def login():
	session['logged_in'] = False
	possible_emails = [r.users.email for r in db(db.users.remote_addr==request.remote_addr).select(orderby=~db.Emails.id|~db.users.when_issued,
			left=db.Emails.on(db.Emails.Email==db.users.email))]
			#not currently used
	form = Form([Field('email', 'string',
					requires=IS_EMAIL())
				],
				formstyle=FormStyleBulma)
	header = P(XML(f"Please specify your email to login.<br />If you have signed in previously, please use the \
same email as this identifies your record.<br />You can change your email after logging in via 'My account'.<br />If \
you no longer have access to your old email, please contact {A(SUPPORT_EMAIL, _href='mailto:'+SUPPORT_EMAIL)}."))
 
	if form.accepted:
		redirect(URL('send_email_confirmation', vars=dict(email=form.vars['email'], url=request.query.url,
						timestamp=datetime.datetime.now(TIME_ZONE).replace(tzinfo=None))))
	return locals()

#send email confirmation message
@action('send_email_confirmation', method=['GET'])
@preferred
def send_email_confirmation():
	access = None	#for layout.html
	timestamp = request.query.get('timestamp')
	if timestamp and datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) < datetime.datetime.fromisoformat(timestamp) + datetime.timedelta(seconds=1):
		#generate email unless this is a stale re-request from a browser
		email = (request.query.get('email') or '').lower()
		if not email:	#shouldn't happen, but can be generated perhaps by safelink mechanisms?
			redirect(URL('login'))
		user = db(db.users.email==email).select().first()
		if user:
			user.update_record(remote_addr = request.remote_addr)
			if datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > user.when_issued + datetime.timedelta(minutes = 15):
				user.update_record(tokens=None)	#clear old expired tokens
		else:
			user = db.users[db.users.insert(email=email, remote_addr = request.remote_addr)]
		token = str(random.randint(10000,999999))
		user.update_record(tokens= [token]+(user.tokens or []),
				email = email, when_issued = datetime.datetime.now(TIME_ZONE).replace(tzinfo=None))
		link = URL('validate', user.id, token, scheme=True, vars=dict(url=request.query.url))
		message = f"{LETTERHEAD.replace('&lt;subject&gt;', ' ')}<br><br>\
Please click {A(link, _href=link)} to continue to {SOCIETY_SHORT_NAME}.<br><br>\
If the link doesn't work, please try copy & pasting it to your browser's address bar.<br><br>\
If you are unable to login or have other questions, please contact {A(SUPPORT_EMAIL, _href='mailto:'+SUPPORT_EMAIL)}."
		email_sender(to=email, sender=SUPPORT_EMAIL, subject='Please Confirm Email', body=message)
	header = DIV(P("Please click the link sent to your email to continue. If you don't see the validation message, please check your spam folder."),
				P('This link is valid for 15 minutes. You may close this window.'))
	return locals()

@action('validate/<id:int>/<token:int>', method=['GET', 'POST'])
@preferred
def validate(id, token):
	user = db(db.users.id == id).select().first()
	if not user or not int(token) in user.tokens or \
			datetime.datetime.now(TIME_ZONE).replace(tzinfo=None) > user.when_issued + datetime.timedelta(minutes = 15):
			#user.remote_addr != request.remote_addr:	#this check may be too strong,
			#there may be configurations where the IP switches between browser and email??
		redirect(URL('index'))
	rows = db((db.Members.id == db.Emails.Member) & db.Emails.Email.ilike(user.email)).select(
				db.Members.ALL, distinct=True)
	header = H6("Please select which of you is signing in:")
	members = [(row.id, member_name(row.id)+(' '+row.Membership+' member until '+(row.Paiddate.strftime(DATE_FORMAT) if row.Paiddate else '')  if row.Membership else '')) for row in rows]
	form = Form([Field('member', 'integer', requires=IS_IN_SET(members))],
	     formstyle=FormStyleBulma, csrf_protection=False)
	if len(rows)<=1 or 'switch_email' in request.query.url:
		member_id = rows.first().id if len(rows)==1 else None
	elif form.accepted:
		member_id = form.vars.get('member')
	else:
		return locals()	#display form
	
	session['logged_in'] = True
	session.email = user.email
	session.access = None
	session.member_id = None
	if member_id:
		session.member_id = int(member_id)
		session.access = db.Members[member_id].Access
	log =f"login verified {request.remote_addr} {user.email} {request.query.url or ''} {request.environ.get('HTTP_USER_AGENT')}"
	logger.info(log)
	redirect(request.query.url)

@action('accessdenied')
@preferred
def accessdenied():
	access = session.access	#for layout.html
	header = CAT(
			"You do not have permission for that, please contact ",
			A(SUPPORT_EMAIL, _href=f'mailto:{SUPPORT_EMAIL}'),
			" if you think this is wrong."
			)
	form = Form([], submit_value='OK')
	if form.accepted:
		redirect(URL('browser_back'))
	return locals()

@action('browser_back')
@action.uses("back.html", Inject(PAGE_BANNER=PAGE_BANNER, HOME_URL=HOME_URL, HELP_URL=HELP_URL))
def browser_back():
	return locals()

@action('logout')
@action.uses(session)
def logout():
	session['logged_in'] = False
	redirect(URL('index'))
